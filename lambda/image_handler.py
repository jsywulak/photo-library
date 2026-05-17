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

from exif import extract_captured_at
from thumbnailer import generate_thumbnail
from utils import get_required_env, record_event

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_UPLOAD_BUCKET = get_required_env("UPLOAD_BUCKET")
_INBOX_BUCKET = get_required_env("INBOX_BUCKET")
_THUMBNAIL_BUCKET = get_required_env("THUMBNAIL_BUCKET")
_DB_URL = os.environ.get("NEON_DATABASE_URL")


def _record_inbox_photo(
    s3_key: str,
    content_hash: str,
    original_filename: str,
    captured_at,
) -> None:
    """Insert the inbox photos row and emit the 'received' event in one transaction.

    Best-effort — never raises. A Neon outage must not break the upload path;
    if this fails, processor v2's EventBridge handler will INSERT the row when
    the inbox object triggers it (its existing ON CONFLICT DO NOTHING tolerates
    that race).
    """
    if not _DB_URL:
        logger.warning("NEON_DATABASE_URL not set; skipping inbox row + photo_events write")
        return
    try:
        conn = psycopg2.connect(_DB_URL, connect_timeout=5)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO photos (s3_key, bucket, captured_at, content_hash, original_filename, uploaded_at)"
                    " VALUES (%s, %s, %s, %s, %s, NOW())"
                    " ON CONFLICT DO NOTHING RETURNING id",
                    (s3_key, _INBOX_BUCKET, captured_at, content_hash, original_filename),
                )
                row = cur.fetchone()
                if row is not None:
                    photo_id = row[0]
                else:
                    cur.execute(
                        "SELECT id FROM photos WHERE s3_key = %s AND bucket = %s",
                        (s3_key, _INBOX_BUCKET),
                    )
                    existing = cur.fetchone()
                    photo_id = existing[0] if existing else None
                record_event(
                    cur, s3_key, _INBOX_BUCKET, "received", "image_handler",
                    photo_id=photo_id,
                    details={"content_hash": content_hash, "original_filename": original_filename},
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to write inbox photos row + received event for %s", s3_key)


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

    captured_at = extract_captured_at(image_bytes)

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
        Metadata={
            "original-filename": original_filename,
            "content-hash": content_hash,
            "pipeline-stage": "received",
        },
    )
    logger.info("Written to s3://%s/%s (original: %s)", _INBOX_BUCKET, dest_key, original_filename)

    s3.delete_object(Bucket=source_bucket, Key=s3_key)
    logger.info("Deleted original s3://%s/%s", source_bucket, s3_key)

    _record_inbox_photo(dest_key, content_hash, original_filename, captured_at)

    return {
        "status": "processed",
        "s3_key": s3_key,
        "content_hash": content_hash,
        "inbox_key": dest_key,
        "thumbnail_status": thumb_status,
    }
