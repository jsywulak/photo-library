#!/usr/bin/env python3
"""Delete DB records for photos whose S3 object no longer exists."""

import os
from pathlib import Path

import boto3
import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

S3_BUCKET = os.environ["S3_BUCKET"]
NEON_DATABASE_URL = os.environ["NEON_DATABASE_URL"]

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".JPG", ".JPEG"}


def list_s3_keys(bucket: str) -> set[str]:
    s3 = boto3.client("s3")
    keys = set()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if Path(key).suffix in IMAGE_EXTENSIONS:
                keys.add(key)
    return keys


def main():
    # TODO (revisit ~2026-03-27): raise this floor once the photo count stabilises.
    S3_COUNT_MINIMUM = 1000

    print(f"Listing S3 objects in s3://{S3_BUCKET} ...", flush=True)
    s3_keys = list_s3_keys(S3_BUCKET)

    if len(s3_keys) < S3_COUNT_MINIMUM:
        raise SystemExit(
            f"Safety check failed: only {len(s3_keys)} images found in S3 "
            f"(expected at least {S3_COUNT_MINIMUM}). "
            "This may indicate an incomplete listing. Aborting."
        )

    print("Querying DB ...", flush=True)
    conn = psycopg2.connect(NEON_DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT s3_key FROM photos")
            db_keys = {row[0] for row in cur.fetchall()}

        orphans = sorted(db_keys - s3_keys)

        if not orphans:
            print("No orphaned DB records found.")
            return

        print(f"\nFound {len(orphans)} orphaned DB records:")
        for key in orphans:
            print(f"  {key}")

        print(f"\nDeleting {len(orphans)} records (photo_tags cascade automatically) ...", flush=True)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM photos WHERE s3_key = ANY(%s)", (orphans,))
            deleted = cur.rowcount
        conn.commit()
        print(f"Deleted {deleted} photos. Run neon-clean-tags to remove any orphaned tags.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
