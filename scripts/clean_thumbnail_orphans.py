#!/usr/bin/env python3
"""Delete thumbnails in S3 that have no corresponding photo in the DB."""

import os
from pathlib import Path

import boto3
import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

NEON_DATABASE_URL = os.environ["NEON_DATABASE_URL"]
THUMBNAIL_BUCKET = os.environ["THUMBNAIL_BUCKET"]


def list_thumbnail_keys(bucket: str) -> set[str]:
    s3 = boto3.client("s3")
    keys = set()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="thumbnails/"):
        for obj in page.get("Contents", []):
            keys.add(obj["Key"])
    return keys


def main():
    print(f"Listing thumbnails in s3://{THUMBNAIL_BUCKET} ...", flush=True)
    existing_thumbs = list_thumbnail_keys(THUMBNAIL_BUCKET)

    print("Querying DB ...", flush=True)
    conn = psycopg2.connect(NEON_DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT s3_key FROM photos")
            known_stems = {Path(row[0]).stem for row in cur.fetchall()}
    finally:
        conn.close()

    orphaned = sorted(
        key for key in existing_thumbs
        if Path(key).stem not in known_stems
    )

    if not orphaned:
        print("No orphaned thumbnails found.")
        return

    print(f"\nFound {len(orphaned)} orphaned thumbnails:")
    for key in orphaned:
        print(f"  {key}")

    s3 = boto3.client("s3")
    print(f"\nDeleting {len(orphaned)} thumbnails ...", flush=True)
    # S3 delete_objects accepts up to 1000 keys per call
    for i in range(0, len(orphaned), 1000):
        batch = [{"Key": key} for key in orphaned[i:i + 1000]]
        s3.delete_objects(Bucket=THUMBNAIL_BUCKET, Delete={"Objects": batch})

    print(f"Deleted {len(orphaned)} thumbnails.")


if __name__ == "__main__":
    main()
