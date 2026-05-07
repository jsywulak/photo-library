"""
image_handler.py — AWS Lambda entry point for the upload staging pipeline.

Triggered by EventBridge when an object is created in the upload bucket.
Computes the SHA-256 hash of the image, generates a hash-keyed thumbnail,
writes the photo to the inbox bucket as {content_hash}.jpg (with the
original filename preserved as S3 object metadata), and deletes the
original from the upload bucket.

Environment variables required:
  UPLOAD_BUCKET     — S3 staging bucket where photos are uploaded
  INBOX_BUCKET      — S3 bucket for unprocessed inbox photos
  THUMBNAIL_BUCKET  — S3 bucket to write thumbnails to
"""

import hashlib
import logging
import os
import urllib.parse
from pathlib import Path

import boto3
import psycopg2
from botocore.exceptions import ClientError

from thumbnailer import generate_thumbnail
from utils import get_required_env, record_event

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_UPLOAD_BUCKET = get_required_env("UPLOAD_BUCKET")
_INBOX_BUCKET = get_required_env("INBOX_BUCKET")
_THUMBNAIL_BUCKET = get_required_env("THUMBNAIL_BUCKET")
_DB_URL = os.environ.get("NEON_DATABASE_URL")


def _emit_received_event(s3_key: str, content_hash: str, original_filename: str) -> None:
    """Best-effort write of a 'received' event. Never raises — observability must
    not break the upload path if Neon is briefly unreachable.
    """
    if not _DB_URL:
        logger.warning("NEON_DATABASE_URL not set; skipping photo_events write")
        return
    try:
        conn = psycopg2.connect(_DB_URL, connect_timeout=5)
        try:
            with conn.cursor() as cur:
                record_event(
                    cur, s3_key, _INBOX_BUCKET, "received", "image_handler",
                    photo_id=None,
                    details={"content_hash": content_hash, "original_filename": original_filename},
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to write 'received' photo_events row for %s", s3_key)


def _extract_s3_key(event):
    """Extract (source_bucket, s3_key) from EventBridge or direct dict invocation.

    EventBridge S3 Object Created events URL-encode the object key.
    Direct invocation passes a plain s3_key (and optional source_bucket) for testing.
    """
    if "s3_key" in event:
        return event.get("source_bucket", _UPLOAD_BUCKET), event["s3_key"]
    if event.get("source") == "aws.s3":
        detail = event.get("detail", {})
        raw_key = detail.get("object", {}).get("key", "")
        s3_key = urllib.parse.unquote_plus(raw_key)
        bucket = detail.get("bucket", {}).get("name", _UPLOAD_BUCKET)
        return bucket, s3_key
    raise ValueError(f"Unrecognised event format: {event}")


def lambda_handler(event, context):
    source_bucket, s3_key = _extract_s3_key(event)
    logger.info("Processing upload s3://%s/%s", source_bucket, s3_key)

    s3 = boto3.client("s3")

    try:
        obj = s3.get_object(Bucket=source_bucket, Key=s3_key)
        image_bytes = obj["Body"].read()
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code in ("NoSuchKey", "AccessDenied"):
            logger.warning("Skipping s3://%s/%s — %s", source_bucket, s3_key, error_code)
            return {"status": "skipped", "reason": error_code, "s3_key": s3_key}
        raise

    content_hash = hashlib.sha256(image_bytes).hexdigest()
    logger.info("content_hash=%s for s3://%s/%s", content_hash, source_bucket, s3_key)

    thumb_status = generate_thumbnail(
        s3_key, source_bucket, _THUMBNAIL_BUCKET, s3, content_hash=content_hash
    )
    logger.info("Thumbnail status: %s -> thumbnails/%s.webp", thumb_status, content_hash)

    dest_key = f"{content_hash}.jpg"
    original_filename = Path(s3_key).name
    s3.put_object(
        Bucket=_INBOX_BUCKET,
        Key=dest_key,
        Body=image_bytes,
        ContentType="image/jpeg",
        Metadata={"original-filename": original_filename},
    )
    logger.info("Written to s3://%s/%s (original: %s)", _INBOX_BUCKET, dest_key, original_filename)

    s3.delete_object(Bucket=source_bucket, Key=s3_key)
    logger.info("Deleted original s3://%s/%s", source_bucket, s3_key)

    _emit_received_event(dest_key, content_hash, original_filename)

    return {
        "status": "processed",
        "s3_key": s3_key,
        "content_hash": content_hash,
        "inbox_key": dest_key,
        "thumbnail_status": thumb_status,
    }
