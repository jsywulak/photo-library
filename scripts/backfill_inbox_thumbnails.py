#!/usr/bin/env python3
"""Generate thumbnails for all inbox photos that don't already have one.

Invokes the thumbnailer Lambda synchronously for each s3_key in the inbox bucket,
passing source_bucket so the Lambda reads from the correct bucket.
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from dotenv import load_dotenv

from helpers import db_connection, invoke_lambda

load_dotenv(Path(__file__).parents[1] / ".env")

NEON_DATABASE_URL = os.environ["NEON_DATABASE_URL"]
THUMBNAILER_LAMBDA_NAME = os.environ["THUMBNAILER_LAMBDA_NAME"]
INBOX_BUCKET = os.environ["INBOX_BUCKET"]

CONCURRENCY = 20


def fetch_inbox_keys(conn, inbox_bucket: str) -> list[tuple[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s3_key, content_hash FROM photos WHERE bucket = %s ORDER BY s3_key",
            (inbox_bucket,),
        )
        return cur.fetchall()


def run_inbox_backfill(rows: list[tuple[str, str]], inbox_bucket: str, lambda_client, lambda_name: str) -> dict:
    """Invoke the thumbnailer Lambda for each inbox key. Returns thumbnailed/skipped/failed counts."""
    thumbnailed = skipped = failed = 0
    lock = threading.Lock()

    def process(s3_key, content_hash):
        result = invoke_lambda(
            lambda_client, lambda_name,
            {"s3_key": s3_key, "source_bucket": inbox_bucket, "content_hash": content_hash},
        )
        return result.get("status")

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {executor.submit(process, key, hash_): key for key, hash_ in rows}
        for future in as_completed(futures):
            s3_key = futures[future]
            try:
                status = future.result()
                with lock:
                    if status == "thumbnailed":
                        thumbnailed += 1
                        print(f"  [thumbnailed] {s3_key}")
                    else:
                        skipped += 1
                        print(f"  [skipped]     {s3_key}")
            except Exception as e:
                with lock:
                    print(f"  [error]       {s3_key}: {e}")
                    failed += 1

    return {"thumbnailed": thumbnailed, "skipped": skipped, "failed": failed}


def main():
    with db_connection(NEON_DATABASE_URL) as conn:
        rows = fetch_inbox_keys(conn, INBOX_BUCKET)

    if not rows:
        print("No inbox photos found.")
        return

    print(f"Found {len(rows)} inbox photos. Generating thumbnails...\n")

    lam = boto3.client("lambda")
    result = run_inbox_backfill(
        rows=rows,
        inbox_bucket=INBOX_BUCKET,
        lambda_client=lam,
        lambda_name=THUMBNAILER_LAMBDA_NAME,
    )

    print(
        f"\nDone. Thumbnailed: {result['thumbnailed']}, "
        f"skipped: {result['skipped']}, "
        f"failed: {result['failed']}."
    )


if __name__ == "__main__":
    main()
