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


def _stamp_tagged_metadata(s3, bucket: str, key: str, conn) -> None:
    """Self-CopyObject to stamp tagged-by-model + pipeline-stage=tagged on the
    photo object after successful tagging. Best-effort — failures here must not
    invalidate the DB commit that already ran. Only runs when tagged_by_model
    is set, which gates out inbox-bucket invocations (where no tagging happens).
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash, original_filename, tagged_by_model"
                " FROM photos WHERE s3_key = %s AND bucket = %s",
                (key, bucket),
            )
            row = cur.fetchone()
        if not row:
            return
        content_hash, original_filename, tagged_by_model = row
        if not tagged_by_model:
            return
        metadata = {"pipeline-stage": "tagged", "tagged-by-model": tagged_by_model}
        if content_hash:
            metadata["content-hash"] = content_hash
        if original_filename:
            metadata["original-filename"] = original_filename
        s3.copy_object(
            CopySource={"Bucket": bucket, "Key": key},
            Bucket=bucket,
            Key=key,
            Metadata=metadata,
            MetadataDirective="REPLACE",
        )
    except Exception:
        logger.exception("Failed to stamp tagged metadata on s3://%s/%s", bucket, key)


def lambda_handler(event, context):
    bucket, key = _extract_bucket_key(event)

    if not bucket or not key:
        raise ValueError(f"Could not extract bucket/key from event: {event}")

    logger.info("Processing s3://%s/%s", bucket, key)

    s3 = boto3.client("s3")
    try:
        image_bytes = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
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
        if status == "processed":
            _stamp_tagged_metadata(s3, bucket, key, conn)
        return {"status": status, "s3_key": key}
    except Exception as e:
        conn.rollback()
        record_error(conn, key, e, bucket=bucket)
        raise
    finally:
        conn.close()
