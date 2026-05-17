#!/usr/bin/env python3
"""Reconcile S3 buckets against the photos table and emit orphan events.

For each managed bucket (photos + inbox):
  - List S3 keys.
  - Fetch (s3_key) tuples from `photos` for that bucket.
  - For each S3 key with no DB row: emit a `photo_events` row with
    event_type='orphan_s3_only', actor='reconciler'.
  - For each DB row with no S3 object: emit `orphan_db_only`.

Dedup guard: a row is written only if no `(s3_key, bucket, event_type)`
event already exists. Safe to run repeatedly without spamming the audit log;
each new orphan produces exactly one event.

Run via `make neon-reconcile`.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from helpers import db_connection, is_valid_image, list_s3_keys

load_dotenv(Path(__file__).parents[1] / ".env")

NEON_DATABASE_URL = os.environ["NEON_DATABASE_URL"]
PHOTOS_BUCKET = os.environ["S3_BUCKET"]
INBOX_BUCKET = os.environ["INBOX_BUCKET"]


def list_db_rows(conn, bucket: str) -> dict[str, int]:
    """Return {s3_key: photo_id} for all photos rows in the given bucket."""
    with conn.cursor() as cur:
        cur.execute("SELECT s3_key, id FROM photos WHERE bucket = %s", (bucket,))
        return {row[0]: row[1] for row in cur.fetchall()}


def emit_orphan_event(conn, s3_key: str, bucket: str, event_type: str,
                      photo_id: int | None, details: dict) -> bool:
    """INSERT an orphan event only if no row with the same (s3_key, bucket, event_type)
    already exists. Returns True if a new row was inserted.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO photo_events (photo_id, s3_key, bucket, event_type, actor, details)
            SELECT %s, %s, %s, %s, 'reconciler', %s::jsonb
            WHERE NOT EXISTS (
                SELECT 1 FROM photo_events
                WHERE s3_key = %s AND bucket = %s AND event_type = %s
            )
            RETURNING id
            """,
            (photo_id, s3_key, bucket, event_type, json.dumps(details),
             s3_key, bucket, event_type),
        )
        return cur.fetchone() is not None


def reconcile_bucket(conn, bucket: str) -> tuple[int, int]:
    """Emit orphan events for one bucket. Returns (new_s3_only, new_db_only)."""
    s3_keys = list_s3_keys(bucket, filter_fn=is_valid_image)
    db_rows = list_db_rows(conn, bucket)
    db_keys = set(db_rows.keys())

    now_iso = datetime.now(timezone.utc).isoformat()

    new_s3_only = 0
    for key in s3_keys - db_keys:
        if emit_orphan_event(
            conn, key, bucket, "orphan_s3_only",
            photo_id=None, details={"first_seen": now_iso},
        ):
            new_s3_only += 1

    new_db_only = 0
    for key in db_keys - s3_keys:
        if emit_orphan_event(
            conn, key, bucket, "orphan_db_only",
            photo_id=db_rows[key], details={"first_seen": now_iso, "photo_id": db_rows[key]},
        ):
            new_db_only += 1

    return new_s3_only, new_db_only


def main():
    print("Reconciling pipeline state...", flush=True)
    with db_connection(NEON_DATABASE_URL) as conn:
        totals = {}
        for bucket in (PHOTOS_BUCKET, INBOX_BUCKET):
            print(f"  scanning s3://{bucket} ...", flush=True)
            s3_only, db_only = reconcile_bucket(conn, bucket)
            totals[bucket] = (s3_only, db_only)
        conn.commit()

    print()
    print("New orphan events written:")
    for bucket, (s3_only, db_only) in totals.items():
        print(f"  {bucket}: orphan_s3_only={s3_only}  orphan_db_only={db_only}")


if __name__ == "__main__":
    main()
