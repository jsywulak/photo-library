#!/usr/bin/env python3
"""Re-invoke the processor Lambda for all photos with last_error set."""

import os
from pathlib import Path

import boto3
from dotenv import load_dotenv

from helpers import db_connection, invoke_lambda, make_s3_event

load_dotenv(Path(__file__).parents[1] / ".env")

NEON_DATABASE_URL = os.environ["NEON_DATABASE_URL"]
PROCESSOR_LAMBDA_NAME = os.environ["PROCESSOR_V2_LAMBDA_NAME"]


def fetch_errored(conn) -> list[tuple[str, str]]:
    """Return list of (s3_key, bucket) for all errored photos."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT s3_key, bucket FROM photos WHERE last_error IS NOT NULL ORDER BY bucket, s3_key"
        )
        return [(row[0], row[1]) for row in cur.fetchall()]


def main():
    with db_connection(NEON_DATABASE_URL) as conn:
        errored = fetch_errored(conn)

    if not errored:
        print("No errored photos found.")
        return

    print(f"Found {len(errored)} errored photos. Invoking {PROCESSOR_LAMBDA_NAME} ...\n")

    lam = boto3.client("lambda")
    invoked = failed = 0

    for key, bucket in errored:
        try:
            invoke_lambda(lam, PROCESSOR_LAMBDA_NAME, make_s3_event(bucket, key), async_=True)
            print(f"  [queued] [{bucket}] {key}")
            invoked += 1
        except Exception as e:
            print(f"  [error]  [{bucket}] {key}: {e}")
            failed += 1

    print(f"\nDone. Queued: {invoked}, failed to invoke: {failed}.")
    if invoked:
        print("Invocations are async — check neon-errors again in a minute to see results.")


if __name__ == "__main__":
    main()
