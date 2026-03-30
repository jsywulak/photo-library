#!/usr/bin/env python3
"""Migrate photos to use SHA-256 content hashes as S3 keys.

Phase 4 of the hash migration. Run AFTER deploying the updated processor
and searcher Lambdas (Phases 2 and 3).

Step 1 — Photos bucket: rename {old_key} → {hash}.jpg
  - Non-suspect photos: update DB record in place, copy S3, delete old key.
    Tags and processed_at are preserved.
  - Suspect photos (S3 LastModified >> processed_at): copy S3, re-invoke
    processor Lambda to re-tag with correct content, delete old key and
    stale DB record.

Step 2 — Inbox bucket: populate content_hash + original_filename
  - Keys stay as filenames; only the DB columns are backfilled.

Step 3 — Apply migration 009 (UNIQUE(content_hash, bucket)) via make neon-migrate.
  This script prints a reminder; you run it separately.

Idempotent: re-running skips already-migrated photos.
"""

import argparse
import hashlib
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta, timezone
from pathlib import Path

import boto3
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from helpers import db_connection, invoke_lambda, is_valid_image, make_s3_event

load_dotenv(Path(__file__).parents[1] / ".env")

PHOTOS_BUCKET         = os.environ["S3_BUCKET"]
INBOX_BUCKET          = os.environ["INBOX_BUCKET"]
NEON_DATABASE_URL     = os.environ["NEON_DATABASE_URL"]
PROCESSOR_LAMBDA_NAME = os.environ["PROCESSOR_LAMBDA_NAME"]
BUFFER_MINUTES        = 10
SUSPECT_CONCURRENCY   = 2

_s3 = boto3.client("s3")
_lam = boto3.client("lambda")


# ---------------------------------------------------------------------------
# Suspect detection
# ---------------------------------------------------------------------------

def _list_s3_objects(bucket: str) -> dict[str, object]:
    """Return {key: last_modified} for all objects in bucket."""
    result = {}
    paginator = _s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            result[obj["Key"]] = obj["LastModified"]
    return result


def _build_suspect_set(s3_objects: dict, db_photos: dict) -> set[str]:
    """Return the set of s3_keys whose S3 object was modified after processing."""
    buffer = timedelta(minutes=BUFFER_MINUTES)
    suspects = set()
    for s3_key, last_modified in s3_objects.items():
        processed_at = db_photos.get(s3_key)
        if processed_at is None:
            continue
        if processed_at.tzinfo is None:
            processed_at = processed_at.replace(tzinfo=timezone.utc)
        if last_modified > processed_at + buffer:
            suspects.add(s3_key)
    return suspects


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_hash_key(s3_key: str) -> bool:
    """Return True if s3_key looks like {64-char hex}.jpg."""
    p = Path(s3_key)
    return p.suffix.lower() == ".jpg" and len(p.stem) == 64 and p.stem.isalnum()


def _sha256_of_s3_object(bucket: str, key: str) -> tuple[str, bytes]:
    """Download S3 object and return (hex_hash, bytes)."""
    body = _s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    return hashlib.sha256(body).hexdigest(), body


# ---------------------------------------------------------------------------
# Step 1 — Photos bucket
# ---------------------------------------------------------------------------

def _migrate_photos_bucket(conn, limit: int | None = None) -> dict:
    print(f"\n=== Step 1: Photos bucket s3://{PHOTOS_BUCKET} ===", flush=True)

    print("  Listing S3 objects ...", flush=True)
    s3_objects = _list_s3_objects(PHOTOS_BUCKET)

    print("  Querying DB ...", flush=True)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s3_key, processed_at, content_hash FROM photos WHERE bucket = %s",
            (PHOTOS_BUCKET,),
        )
        db_rows = {row[0]: {"processed_at": row[1], "content_hash": row[2]} for row in cur.fetchall()}

    suspect_keys = _build_suspect_set(s3_objects, {k: v["processed_at"] for k, v in db_rows.items()})
    print(f"  {len(s3_objects)} S3 objects, {len(db_rows)} DB rows, {len(suspect_keys)} suspects", flush=True)

    # Track dest_keys we've already processed to catch same-hash duplicates
    migrated_dest_keys: set[str] = set()
    lock = threading.Lock()
    counts = {"renamed": 0, "retagged": 0, "skipped": 0, "errors": 0}

    def _process_non_suspect(s3_key: str):
        # Open a fresh connection per photo — the shared conn can time out during
        # long S3 downloads on Neon's serverless tier.
        hash_hex, _ = _sha256_of_s3_object(PHOTOS_BUCKET, s3_key)
        dest_key = f"{hash_hex}.jpg"

        with lock:
            if dest_key in migrated_dest_keys:
                # Duplicate content — delete the stale DB record and skip S3 rename
                with db_connection(NEON_DATABASE_URL) as tconn:
                    with tconn.cursor() as cur:
                        cur.execute(
                            "DELETE FROM photos WHERE s3_key = %s AND bucket = %s",
                            (s3_key, PHOTOS_BUCKET),
                        )
                    tconn.commit()
                print(f"  [dup-skipped] {s3_key} (same hash as already-migrated photo)", flush=True)
                counts["skipped"] += 1
                return
            migrated_dest_keys.add(dest_key)

        # Update DB first so EventBridge sees existing record and skips re-tagging
        with db_connection(NEON_DATABASE_URL) as tconn:
            with tconn.cursor() as cur:
                cur.execute(
                    "UPDATE photos SET s3_key = %s, content_hash = %s, original_filename = %s"
                    " WHERE s3_key = %s AND bucket = %s",
                    (dest_key, hash_hex, s3_key, s3_key, PHOTOS_BUCKET),
                )
            tconn.commit()

        if dest_key == s3_key:
            # Key is already the correct hash-based name — DB updated, no S3 work needed.
            print(f"  [db-backfilled] {s3_key}", flush=True)
        else:
            _s3.copy_object(
                CopySource={"Bucket": PHOTOS_BUCKET, "Key": s3_key},
                Bucket=PHOTOS_BUCKET,
                Key=dest_key,
            )
            _s3.delete_object(Bucket=PHOTOS_BUCKET, Key=s3_key)
            print(f"  [renamed] {s3_key} → {dest_key}", flush=True)
        with lock:
            counts["renamed"] += 1

    def _process_suspect(s3_key: str):
        # Each thread opens its own connection — psycopg2 is not thread-safe.
        hash_hex, _ = _sha256_of_s3_object(PHOTOS_BUCKET, s3_key)
        dest_key = f"{hash_hex}.jpg"

        with lock:
            if dest_key in migrated_dest_keys:
                with db_connection(NEON_DATABASE_URL) as tconn:
                    with tconn.cursor() as cur:
                        cur.execute(
                            "DELETE FROM photos WHERE s3_key = %s AND bucket = %s",
                            (s3_key, PHOTOS_BUCKET),
                        )
                    tconn.commit()
                print(f"  [dup-skipped] {s3_key} (suspect, same hash as already-migrated photo)", flush=True)
                counts["skipped"] += 1
                return
            migrated_dest_keys.add(dest_key)

        if dest_key == s3_key:
            # Already at the correct hash key — just ensure content_hash is in DB.
            with db_connection(NEON_DATABASE_URL) as tconn:
                with tconn.cursor() as cur:
                    cur.execute(
                        "UPDATE photos SET content_hash = %s WHERE s3_key = %s AND bucket = %s AND content_hash IS NULL",
                        (dest_key.removesuffix(".jpg"), s3_key, PHOTOS_BUCKET),
                    )
                tconn.commit()
            print(f"  [db-backfilled-suspect] {s3_key}", flush=True)
            with lock:
                counts["retagged"] += 1
            return

        # Copy to hash key — EventBridge may fire async, but processor uses ON CONFLICT DO NOTHING
        _s3.copy_object(
            CopySource={"Bucket": PHOTOS_BUCKET, "Key": s3_key},
            Bucket=PHOTOS_BUCKET,
            Key=dest_key,
        )

        # Directly invoke processor synchronously to re-tag with correct content
        result = invoke_lambda(_lam, PROCESSOR_LAMBDA_NAME, make_s3_event(PHOTOS_BUCKET, dest_key))
        status = result.get("status") if result else "unknown"

        _s3.delete_object(Bucket=PHOTOS_BUCKET, Key=s3_key)

        # Delete stale DB record — CASCADE removes its photo_tags
        with db_connection(NEON_DATABASE_URL) as tconn:
            with tconn.cursor() as cur:
                cur.execute(
                    "DELETE FROM photos WHERE s3_key = %s AND bucket = %s",
                    (s3_key, PHOTOS_BUCKET),
                )
            tconn.commit()

        print(f"  [retagged/{status}] {s3_key} → {dest_key}", flush=True)
        with lock:
            counts["retagged"] += 1

    # Non-suspects: sequential (fast, no API rate-limit concerns)
    non_suspects = [
        k for k in s3_objects
        if k not in suspect_keys and not (
            _is_hash_key(k) and db_rows.get(k, {}).get("content_hash") is not None
        )
    ]
    already_done = [
        k for k in s3_objects
        if _is_hash_key(k) and db_rows.get(k, {}).get("content_hash") is not None
    ]
    already_done_set = set(already_done)
    # Exclude already-migrated photos from suspects: after renaming, a photo's
    # S3 LastModified = copy time >> original processed_at, so it would otherwise
    # be re-classified as a suspect on every subsequent run.
    suspects = [k for k in s3_objects if k in suspect_keys and k not in already_done_set]

    # Register all already-done keys so duplicate-dest-key detection works correctly.
    for k in already_done:
        migrated_dest_keys.add(k)

    if limit is not None:
        non_suspects = non_suspects[:limit]
        suspects = suspects[:limit]
        print(f"  (--limit {limit} per category: {len(non_suspects)} non-suspects, {len(suspects)} suspects)", flush=True)
    else:
        # Only print already-migrated lines in unlimited mode to avoid flooding limited runs.
        for k in already_done:
            print(f"  [already-migrated] {k}", flush=True)
            with lock:
                counts["skipped"] += 1

    print(f"\n  Processing {len(non_suspects)} non-suspect photos ...", flush=True)
    for s3_key in non_suspects:
        try:
            _process_non_suspect(s3_key)
        except Exception as e:
            print(f"  [error] {s3_key}: {e}", flush=True)
            with lock:
                counts["errors"] += 1

    print(f"\n  Processing {len(suspects)} suspect photos (concurrency={SUSPECT_CONCURRENCY}) ...", flush=True)
    with ThreadPoolExecutor(max_workers=SUSPECT_CONCURRENCY) as executor:
        futures = {executor.submit(_process_suspect, k): k for k in suspects}
        for future in as_completed(futures):
            s3_key = futures[future]
            exc = future.exception()
            if exc:
                print(f"  [error] {s3_key}: {exc}", flush=True)
                with lock:
                    counts["errors"] += 1

    return counts


# ---------------------------------------------------------------------------
# Step 2 — Inbox bucket
# ---------------------------------------------------------------------------

def _backfill_inbox(conn, limit: int | None = None) -> dict:
    print(f"\n=== Step 2: Inbox bucket s3://{INBOX_BUCKET} ===", flush=True)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT s3_key FROM photos WHERE bucket = %s AND content_hash IS NULL",
            (INBOX_BUCKET,),
        )
        rows = [r[0] for r in cur.fetchall()]

    total = len(rows)
    if limit is not None:
        rows = rows[:limit]
        print(f"  {total} inbox rows need backfill, processing {len(rows)} (--limit)", flush=True)
    else:
        print(f"  {total} inbox rows need content_hash backfill", flush=True)
    counts = {"backfilled": 0, "errors": 0}

    for s3_key in rows:
        try:
            body = _s3.get_object(Bucket=INBOX_BUCKET, Key=s3_key)["Body"].read()
            hash_hex = hashlib.sha256(body).hexdigest()
            with db_connection(NEON_DATABASE_URL) as tconn:
                with tconn.cursor() as cur:
                    cur.execute(
                        "UPDATE photos SET content_hash = %s, original_filename = COALESCE(original_filename, %s)"
                        " WHERE s3_key = %s AND bucket = %s AND content_hash IS NULL",
                        (hash_hex, s3_key, s3_key, INBOX_BUCKET),
                    )
                tconn.commit()
            print(f"  [backfilled] {s3_key}", flush=True)
            counts["backfilled"] += 1
        except Exception as e:
            print(f"  [error] {s3_key}: {e}", flush=True)
            counts["errors"] += 1

    return counts


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Migrate photos to SHA-256 hash keys.")
    parser.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="Process at most N photos from the photos bucket (for test runs). Inbox backfill is unaffected.",
    )
    args = parser.parse_args()

    print("migrate_to_hashes.py — Phase 4 of SHA-256 key migration")
    if args.limit is not None:
        print(f"  LIMITED MODE: capping photos bucket to {args.limit} per category (not a full run)")
    print("=" * 60)

    with db_connection(NEON_DATABASE_URL) as conn:
        photos_counts = _migrate_photos_bucket(conn, limit=args.limit)
        inbox_counts = _backfill_inbox(conn, limit=args.limit)

    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Photos bucket: renamed={photos_counts['renamed']}, retagged={photos_counts['retagged']}, "
          f"skipped={photos_counts['skipped']}, errors={photos_counts['errors']}")
    print(f"  Inbox bucket:  backfilled={inbox_counts['backfilled']}, errors={inbox_counts['errors']}")

    total_errors = photos_counts["errors"] + inbox_counts["errors"]
    if total_errors:
        print(f"\n  WARNING: {total_errors} error(s) occurred. Re-run to retry failed photos.")
    elif args.limit is not None:
        print(f"\n  Limited run complete. Verify the results, then run without --limit for the full migration.")
    else:
        print("\n  All photos migrated successfully.")
        print("\nNext step: apply the UNIQUE constraint migration:")
        print("  make neon-migrate")
        print("  make local-migrate")


if __name__ == "__main__":
    main()
