"""
handler.py — AWS Lambda entry point for the photo processor.

Triggered by S3 events. Fetches the image, calls process_one, and commits.
Environment variables required:
  NEON_DATABASE_URL   — Neon PostgreSQL connection string
  ANTHROPIC_API_KEY   — Anthropic API key (read automatically by the client)
"""

import logging
import os

import anthropic
import boto3
import psycopg2

from processor import process_one

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_DB_URL = os.environ.get("NEON_DATABASE_URL")
if not _DB_URL:
    raise RuntimeError("NEON_DATABASE_URL environment variable is not set")


def lambda_handler(event, context):
    records = event.get("Records", [])
    if not records:
        raise ValueError(f"No Records in event: {event}")

    record = records[0].get("s3", {})
    bucket = record.get("bucket", {}).get("name")
    key = record.get("object", {}).get("key")

    if not bucket or not key:
        raise ValueError(f"Could not extract bucket/key from event: {event}")

    logger.info("Processing s3://%s/%s", bucket, key)

    image_bytes = (
        boto3.client("s3")
        .get_object(Bucket=bucket, Key=key)["Body"]
        .read()
    )

    conn = psycopg2.connect(_DB_URL, connect_timeout=10)
    conn.autocommit = False
    try:
        status = process_one(key, image_bytes, conn, anthropic.Anthropic(max_retries=4))
        conn.commit()
        logger.info("Completed s3://%s/%s: %s", bucket, key, status)
        return {"status": status, "s3_key": key}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
