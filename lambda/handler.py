"""
handler.py — AWS Lambda entry point for the photo processor.

Triggered by S3 events. Fetches the image, calls process_one, and commits.
Environment variables required:
  NEON_DATABASE_URL   — Neon PostgreSQL connection string
  ANTHROPIC_API_KEY   — Anthropic API key (read automatically by the client)
"""

import logging

import anthropic
import boto3
import psycopg2
from botocore.exceptions import ClientError

from processor import process_one, record_error
from utils import get_required_env

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_DB_URL = get_required_env("NEON_DATABASE_URL")


def _extract_bucket_key(event):
    """Extract bucket and key from either an S3 notification or EventBridge event."""
    if "Records" in event:
        record = event["Records"][0].get("s3", {})
        return record.get("bucket", {}).get("name"), record.get("object", {}).get("key")
    if event.get("source") == "aws.s3":
        detail = event.get("detail", {})
        return detail.get("bucket", {}).get("name"), detail.get("object", {}).get("key")
    return None, None


def lambda_handler(event, context):
    bucket, key = _extract_bucket_key(event)

    if not bucket or not key:
        raise ValueError(f"Could not extract bucket/key from event: {event}")

    logger.info("Processing s3://%s/%s", bucket, key)

    try:
        image_bytes = (
            boto3.client("s3")
            .get_object(Bucket=bucket, Key=key)["Body"]
            .read()
        )
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("NoSuchKey", "AccessDenied"):
            logger.warning("Skipping s3://%s/%s — S3 error: %s", bucket, key, error_code)
            return {"status": "skipped", "reason": error_code, "s3_key": key}
        raise

    conn = psycopg2.connect(_DB_URL, connect_timeout=10)
    conn.autocommit = False
    try:
        status = process_one(key, image_bytes, conn, anthropic.Anthropic(max_retries=4), bucket=bucket)
        conn.commit()
        logger.info("Completed s3://%s/%s: %s", bucket, key, status)
        return {"status": status, "s3_key": key}
    except Exception as e:
        conn.rollback()
        record_error(conn, key, e, bucket=bucket)
        raise
    finally:
        conn.close()
