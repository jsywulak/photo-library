#!/usr/bin/env python3
"""Compare S3 object listings vs DB photos table and report discrepancies.

Checks both the photos bucket and the inbox bucket separately.
"""

import os
from pathlib import Path

import boto3
import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

S3_BUCKET = os.environ["S3_BUCKET"]
INBOX_BUCKET = os.environ["INBOX_BUCKET"]
NEON_DATABASE_URL = os.environ["NEON_DATABASE_URL"]

def _is_valid_image(key: str) -> bool:
    p = Path(key)
    return p.name[:2] != "._" and p.suffix.lower() in (".jpg", ".jpeg")


def list_s3_keys(bucket: str) -> set[str]:
    s3 = boto3.client("s3")
    keys = set()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if _is_valid_image(key):
                keys.add(key)
    return keys


def list_db_photos(conn, bucket: str) -> dict[str, dict]:
    """Return {s3_key: {processed_at, last_error}} for all rows in the given bucket."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s3_key, processed_at, last_error FROM photos WHERE bucket = %s",
            (bucket,),
        )
        return {
            row[0]: {"processed_at": row[1], "last_error": row[2]}
            for row in cur.fetchall()
        }


def report(label: str, s3_bucket: str, s3_keys: set[str], db_photos: dict[str, dict]):
    db_keys = set(db_photos.keys())
    in_s3_not_db = sorted(s3_keys - db_keys)
    in_db_not_s3 = sorted(db_keys - s3_keys)

    processed_ok = sum(1 for v in db_photos.values() if v["processed_at"] and not v["last_error"])
    errored = sum(1 for v in db_photos.values() if v["last_error"])
    stuck = sum(1 for v in db_photos.values() if not v["processed_at"] and not v["last_error"])

    print(f"{'=' * 60}")
    print(f"{label}  (s3://{s3_bucket})")
    print(f"{'=' * 60}")
    print(f"  S3 images:           {len(s3_keys):>6}")
    print(f"  DB records:          {len(db_keys):>6}")
    if label == "PHOTOS BUCKET":
        print(f"    processed OK:      {processed_ok:>6}")
        print(f"    errored:           {errored:>6}")
        print(f"    stuck (no status): {stuck:>6}")
    else:
        print(f"    tracked:           {len(db_keys) - errored:>6}")
        print(f"    errored:           {errored:>6}")
    print()

    if in_s3_not_db:
        print(f"  IN S3 BUT NOT IN DB ({len(in_s3_not_db)}) — not yet tracked:")
        for key in in_s3_not_db:
            print(f"    {key}")
        print()
    else:
        print("  IN S3 BUT NOT IN DB: none")
        print()

    if in_db_not_s3:
        print(f"  IN DB BUT NOT IN S3 ({len(in_db_not_s3)}) — orphaned DB records:")
        for key in in_db_not_s3:
            meta = db_photos[key]
            status = "error" if meta["last_error"] else ("ok" if meta["processed_at"] else "stuck")
            print(f"    [{status}] {key}")
        print()
    else:
        print("  IN DB BUT NOT IN S3: none")
        print()


def main():
    print(f"Listing S3 objects in s3://{S3_BUCKET} ...", flush=True)
    photos_s3 = list_s3_keys(S3_BUCKET)

    print(f"Listing S3 objects in s3://{INBOX_BUCKET} ...", flush=True)
    inbox_s3 = list_s3_keys(INBOX_BUCKET)

    print("Querying DB ...", flush=True)
    conn = psycopg2.connect(NEON_DATABASE_URL)
    try:
        photos_db = list_db_photos(conn, S3_BUCKET)
        inbox_db = list_db_photos(conn, INBOX_BUCKET)
    finally:
        conn.close()

    print()
    report("PHOTOS BUCKET", S3_BUCKET, photos_s3, photos_db)
    report("INBOX BUCKET", INBOX_BUCKET, inbox_s3, inbox_db)


if __name__ == "__main__":
    main()
