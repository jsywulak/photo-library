#!/usr/bin/env python3
"""Generate thumbnails for all processed photos that don't already have one.

Invokes the thumbnailer Lambda synchronously for each s3_key in the database,
relying on the Lambda's own skip logic to avoid re-processing existing thumbnails.
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

CONCURRENCY = 20


def fetch_processed_keys(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s3_key FROM photos WHERE processed_at IS NOT NULL ORDER BY s3_key"
        )
        return [row[0] for row in cur.fetchall()]


def run_backfill(s3_keys: list[str], lambda_client, lambda_name: str) -> dict:
    """Invoke the thumbnailer Lambda for each key. Returns thumbnailed/skipped/failed counts."""
    thumbnailed = skipped = failed = 0
    lock = threading.Lock()

    def process(s3_key):
        result = invoke_lambda(lambda_client, lambda_name, {"s3_key": s3_key})
        return result.get("status")

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {executor.submit(process, key): key for key in s3_keys}
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
        keys = fetch_processed_keys(conn)

    if not keys:
        print("No processed photos found.")
        return

    print(f"Found {len(keys)} processed photos. Generating thumbnails...\n")

    lam = boto3.client("lambda")
    result = run_backfill(
        s3_keys=keys,
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
