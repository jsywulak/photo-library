#!/usr/bin/env python3
"""Re-invoke the processor Lambda for all photos with last_error set."""

import json
import os
from pathlib import Path

import boto3
import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

NEON_DATABASE_URL = os.environ["NEON_DATABASE_URL"]
PROCESSOR_LAMBDA_NAME = os.environ["PROCESSOR_LAMBDA_NAME"]
S3_BUCKET = os.environ["S3_BUCKET"]


def fetch_errored_keys(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT s3_key FROM photos WHERE last_error IS NOT NULL ORDER BY s3_key")
        return [row[0] for row in cur.fetchall()]


def make_s3_event(bucket: str, key: str) -> dict:
    return {
        "Records": [{
            "s3": {
                "bucket": {"name": bucket},
                "object": {"key": key},
            }
        }]
    }


def main():
    conn = psycopg2.connect(NEON_DATABASE_URL)
    try:
        keys = fetch_errored_keys(conn)
    finally:
        conn.close()

    if not keys:
        print("No errored photos found.")
        return

    print(f"Found {len(keys)} errored photos. Invoking {PROCESSOR_LAMBDA_NAME} ...\n")

    lam = boto3.client("lambda")
    invoked = failed = 0

    for key in keys:
        payload = json.dumps(make_s3_event(S3_BUCKET, key)).encode()
        try:
            lam.invoke(
                FunctionName=PROCESSOR_LAMBDA_NAME,
                InvocationType="Event",  # async
                Payload=payload,
            )
            print(f"  [queued] {key}")
            invoked += 1
        except Exception as e:
            print(f"  [error]  {key}: {e}")
            failed += 1

    print(f"\nDone. Queued: {invoked}, failed to invoke: {failed}.")
    if invoked:
        print("Invocations are async — check neon-errors again in a minute to see results.")


if __name__ == "__main__":
    main()
