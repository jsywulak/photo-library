#!/usr/bin/env python3
"""Compare S3 object listing vs DB photos table and report discrepancies."""

import os
import sys
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


def list_db_photos(conn) -> dict[str, dict]:
    """Return {s3_key: {processed_at, last_error}} for all DB rows."""
    with conn.cursor() as cur:
        cur.execute("SELECT s3_key, processed_at, last_error FROM photos")
        return {
            row[0]: {"processed_at": row[1], "last_error": row[2]}
            for row in cur.fetchall()
        }


def main():
    print(f"Listing S3 objects in s3://{S3_BUCKET} ...", flush=True)
    s3_keys = list_s3_keys(S3_BUCKET)

    print("Querying DB ...", flush=True)
    conn = psycopg2.connect(NEON_DATABASE_URL)
    try:
        db_photos = list_db_photos(conn)
    finally:
        conn.close()

    db_keys = set(db_photos.keys())

    in_s3_not_db = sorted(s3_keys - db_keys)
    in_db_not_s3 = sorted(db_keys - s3_keys)

    # Categorise DB records for the summary
    processed_ok = sum(
        1 for v in db_photos.values() if v["processed_at"] and not v["last_error"]
    )
    errored = sum(1 for v in db_photos.values() if v["last_error"])
    stuck = sum(
        1 for v in db_photos.values() if not v["processed_at"] and not v["last_error"]
    )

    print()
    print("=" * 60)
    print("SYNC CHECK SUMMARY")
    print("=" * 60)
    print(f"  S3 images:           {len(s3_keys):>6}")
    print(f"  DB records:          {len(db_keys):>6}")
    print(f"    processed OK:      {processed_ok:>6}")
    print(f"    errored:           {errored:>6}")
    print(f"    stuck (no status): {stuck:>6}")
    print()

    if in_s3_not_db:
        print(f"IN S3 BUT NOT IN DB ({len(in_s3_not_db)}) — never processed or lost:")
        for key in in_s3_not_db:
            print(f"  {key}")
        print()
    else:
        print("IN S3 BUT NOT IN DB: none")
        print()

    if in_db_not_s3:
        print(f"IN DB BUT NOT IN S3 ({len(in_db_not_s3)}) — orphaned DB records:")
        for key in in_db_not_s3:
            meta = db_photos[key]
            status = "error" if meta["last_error"] else ("ok" if meta["processed_at"] else "stuck")
            print(f"  [{status}] {key}")
        print()
    else:
        print("IN DB BUT NOT IN S3: none")
        print()


if __name__ == "__main__":
    main()
