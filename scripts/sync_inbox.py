#!/usr/bin/env python3
"""Sync existing inbox photos into the database and generate thumbnails.

Lists all JPEGs in the inbox bucket and invokes the processor Lambda (DB record
insert) and thumbnailer Lambda (thumbnail generation) directly for each one.

Use this for photos that were uploaded before the EventBridge trigger was set up.
"""

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import boto3
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

INBOX_BUCKET = os.environ["INBOX_BUCKET"]
PROCESSOR_LAMBDA_NAME = os.environ["PROCESSOR_LAMBDA_NAME"]
THUMBNAILER_LAMBDA_NAME = os.environ["THUMBNAILER_LAMBDA_NAME"]
CONCURRENCY = 3


def _is_valid_image(key: str) -> bool:
    p = Path(key)
    return p.name[:2] != "._" and p.suffix.lower() in (".jpg", ".jpeg")


def list_inbox_keys(s3_client, bucket: str) -> list[str]:
    keys = []
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if _is_valid_image(key):
                keys.append(key)
    return keys


def _s3_payload(bucket: str, key: str) -> bytes:
    return json.dumps({
        "Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]
    }).encode()


def sync(lam, bucket: str, keys: list[str]) -> dict:
    processed = thumbnailed = failed = 0
    lock = threading.Lock()

    def process(key):
        payload = _s3_payload(bucket, key)

        proc_resp = lam.invoke(
            FunctionName=PROCESSOR_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=payload,
        )
        proc_result = json.loads(proc_resp["Payload"].read())
        if "FunctionError" in proc_resp:
            raise RuntimeError(f"processor: {proc_result.get('errorMessage', proc_result)}")

        thumb_resp = lam.invoke(
            FunctionName=THUMBNAILER_LAMBDA_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps({"s3_key": key, "source_bucket": bucket}).encode(),
        )
        thumb_result = json.loads(thumb_resp["Payload"].read())
        if "FunctionError" in thumb_resp:
            raise RuntimeError(f"thumbnailer: {thumb_result.get('errorMessage', thumb_result)}")

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
    s3 = boto3.client("s3")
    keys = list_inbox_keys(s3, INBOX_BUCKET)

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
