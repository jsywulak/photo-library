#!/usr/bin/env python3
"""Delete thumbnails in S3 that have no corresponding photo in the DB."""

import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

from helpers import db_connection, list_s3_keys

load_dotenv(Path(__file__).parents[1] / ".env")

NEON_DATABASE_URL = os.environ["NEON_DATABASE_URL"]
THUMBNAIL_BUCKET = os.environ["THUMBNAIL_BUCKET"]


def main():
    print(f"Listing thumbnails in s3://{THUMBNAIL_BUCKET} ...", flush=True)
    existing_thumbs = list_s3_keys(THUMBNAIL_BUCKET, prefix="thumbnails/")

    print("Querying DB ...", flush=True)
    with db_connection(NEON_DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT s3_key FROM photos")
            known_stems = {Path(row[0]).stem for row in cur.fetchall()}

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
