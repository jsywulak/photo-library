#!/usr/bin/env python3
"""Sync existing inbox photos into the database and generate thumbnails.

Lists all JPEGs in the inbox bucket and invokes the processor Lambda (DB record
insert) and thumbnailer Lambda (thumbnail generation) directly for each one.

Use this for photos that were uploaded before the EventBridge trigger was set up.
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from dotenv import load_dotenv

from helpers import invoke_lambda, is_valid_image, list_s3_keys, make_s3_event

load_dotenv(Path(__file__).parents[1] / ".env")

INBOX_BUCKET = os.environ["INBOX_BUCKET"]
PROCESSOR_LAMBDA_NAME = os.environ["PROCESSOR_LAMBDA_NAME"]
THUMBNAILER_LAMBDA_NAME = os.environ["THUMBNAILER_LAMBDA_NAME"]
CONCURRENCY = 3


def sync(lam, bucket: str, keys: list[str]) -> dict:
    processed = thumbnailed = failed = 0
    lock = threading.Lock()

    def process(key):
        proc_result = invoke_lambda(lam, PROCESSOR_LAMBDA_NAME, make_s3_event(bucket, key))
        thumb_result = invoke_lambda(
            lam, THUMBNAILER_LAMBDA_NAME, {"s3_key": key, "source_bucket": bucket}
        )
        return proc_result.get("status"), thumb_result.get("status")

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = {executor.submit(process, key): key for key in keys}
        for future in as_completed(futures):
            key = futures[future]
            try:
                proc_status, thumb_status = future.result()
                with lock:
                    processed += 1
                    if thumb_status == "thumbnailed":
                        thumbnailed += 1
                    print(f"  [{proc_status}/{thumb_status}] {key}")
            except Exception as e:
                with lock:
                    failed += 1
                    print(f"  [error] {key}: {e}")

    return {"processed": processed, "thumbnailed": thumbnailed, "failed": failed}


def main():
    keys = sorted(list_s3_keys(INBOX_BUCKET, filter_fn=is_valid_image))

    if not keys:
        print(f"No JPEGs found in s3://{INBOX_BUCKET}/")
        return

    print(f"Found {len(keys)} JPEGs in s3://{INBOX_BUCKET}/\n")

    lam = boto3.client("lambda")
    result = sync(lam, INBOX_BUCKET, keys)

    print(
        f"\nDone. Processed: {result['processed']}, "
        f"thumbnailed: {result['thumbnailed']}, "
        f"failed: {result['failed']}."
    )


if __name__ == "__main__":
    main()
