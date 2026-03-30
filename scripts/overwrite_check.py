#!/usr/bin/env python3
"""Detect photos whose S3 object was replaced after they were processed.

When an inbox photo with the same s3_key as an already-processed photo is
moved to the photos bucket, the existing S3 object is silently overwritten.
The processor Lambda then skips it (processed_at is already set), leaving
the DB record pointing to the wrong image.

Heuristic: for a legitimately processed photo, S3 LastModified should be
slightly BEFORE processed_at (object arrives, EventBridge fires, processor
runs and stamps processed_at a few seconds/minutes later). If LastModified
is significantly NEWER than processed_at, the object was replaced after
processing — the S3 content no longer matches the DB record.

Prints all photos where  LastModified > processed_at + BUFFER_MINUTES.
"""

import os
from datetime import timezone
from pathlib import Path

import boto3
import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

S3_BUCKET          = os.environ["S3_BUCKET"]
NEON_DATABASE_URL  = os.environ["NEON_DATABASE_URL"]
BUFFER_MINUTES     = 10  # allow up to 10 min between upload and processed_at


def list_s3_last_modified(bucket: str) -> dict[str, object]:
    """Return {s3_key: last_modified (aware datetime)} for all objects in bucket."""
    s3 = boto3.client("s3")
    result = {}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            result[obj["Key"]] = obj["LastModified"]
    return result


def list_db_processed(conn) -> dict[str, object]:
    """Return {s3_key: processed_at (aware datetime)} for processed photos bucket rows."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s3_key, processed_at FROM photos WHERE bucket = %s AND processed_at IS NOT NULL",
            (S3_BUCKET,),
        )
        return {row[0]: row[1] for row in cur.fetchall()}


def main():
    from datetime import timedelta

    print(f"Listing S3 objects in s3://{S3_BUCKET} ...", flush=True)
    s3_objects = list_s3_last_modified(S3_BUCKET)

    print("Querying DB ...", flush=True)
    conn = psycopg2.connect(NEON_DATABASE_URL)
    try:
        db_photos = list_db_processed(conn)
    finally:
        conn.close()

    buffer = timedelta(minutes=BUFFER_MINUTES)
    suspect = []

    for s3_key, last_modified in s3_objects.items():
        processed_at = db_photos.get(s3_key)
        if processed_at is None:
            continue  # not yet processed — not our concern here
        # Make both timezone-aware for comparison
        if processed_at.tzinfo is None:
            processed_at = processed_at.replace(tzinfo=timezone.utc)
        if last_modified > processed_at + buffer:
            delta = last_modified - processed_at
            suspect.append((s3_key, processed_at, last_modified, delta))

    suspect.sort(key=lambda x: x[3], reverse=True)  # largest delta first

    print()
    if not suspect:
        print("No overwritten photos detected.")
        return

    print(f"SUSPECT PHOTOS ({len(suspect)}) — S3 object modified significantly after processed_at:")
    print(f"  {'s3_key':<60}  {'processed_at':<22}  {'last_modified':<22}  delta")
    print(f"  {'-'*60}  {'-'*22}  {'-'*22}  -----")
    for s3_key, processed_at, last_modified, delta in suspect:
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes = remainder // 60
        delta_str = f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m"
        print(f"  {s3_key:<60}  {str(processed_at)[:19]:<22}  {str(last_modified)[:19]:<22}  {delta_str}")
    print()
    print("These photos likely have DB records (tags, processed_at) from an older")
    print("photo that was overwritten when an inbox photo with the same name was processed.")


if __name__ == "__main__":
    main()
