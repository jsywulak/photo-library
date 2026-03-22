#!/usr/bin/env python3
"""Delete DB records for photos whose S3 object no longer exists.

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

# Safety floors — abort if S3 listing looks unexpectedly small.
S3_COUNT_MINIMUM = 2000
INBOX_COUNT_MINIMUM = 400


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


def clean_orphans_for_bucket(conn, bucket: str, s3_keys: set[str]) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT s3_key FROM photos WHERE bucket = %s", (bucket,))
        db_keys = {row[0] for row in cur.fetchall()}

    orphans = sorted(db_keys - s3_keys)

    if not orphans:
        print(f"  No orphaned DB records for s3://{bucket}")
        return 0

    print(f"  Found {len(orphans)} orphaned DB records for s3://{bucket}:")
    for key in orphans:
        print(f"    {key}")

    print(f"  Deleting {len(orphans)} records ...", flush=True)
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM photos WHERE bucket = %s AND s3_key = ANY(%s)",
            (bucket, orphans),
        )
        deleted = cur.rowcount
    conn.commit()
    print(f"  Deleted {deleted} photos.")
    return deleted


def main():
    print(f"Listing S3 objects in s3://{S3_BUCKET} ...", flush=True)
    photos_keys = list_s3_keys(S3_BUCKET)
    if len(photos_keys) < S3_COUNT_MINIMUM:
        raise SystemExit(
            f"Safety check failed: only {len(photos_keys)} images in s3://{S3_BUCKET} "
            f"(expected at least {S3_COUNT_MINIMUM}). Aborting."
        )

    print(f"Listing S3 objects in s3://{INBOX_BUCKET} ...", flush=True)
    inbox_keys = list_s3_keys(INBOX_BUCKET)
    if len(inbox_keys) < INBOX_COUNT_MINIMUM:
        raise SystemExit(
            f"Safety check failed: only {len(inbox_keys)} images in s3://{INBOX_BUCKET} "
            f"(expected at least {INBOX_COUNT_MINIMUM}). Aborting."
        )

    print("Querying DB ...\n", flush=True)
    conn = psycopg2.connect(NEON_DATABASE_URL)
    try:
        total = 0
        total += clean_orphans_for_bucket(conn, S3_BUCKET, photos_keys)
        print()
        total += clean_orphans_for_bucket(conn, INBOX_BUCKET, inbox_keys)
    finally:
        conn.close()

    if total:
        print(f"\nTotal deleted: {total}. Run neon-clean-tags to remove any orphaned tags.")
    else:
        print("\nNo orphans found.")


if __name__ == "__main__":
    main()
