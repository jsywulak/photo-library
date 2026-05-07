"""
thumbnailer_handler.py — AWS Lambda entry point for the thumbnailer.

Accepts a direct invocation payload: {"s3_key": "..."}
Environment variables required:
  SOURCE_BUCKET     — S3 bucket to read photos from (photo-tagging-photos)
  THUMBNAIL_BUCKET  — S3 bucket to write thumbnails to (photo-tagging-thumbnails)
  NEON_DATABASE_URL — optional; if unset, photo_events writes are skipped
"""

import logging
import os

import boto3
import psycopg2

from thumbnailer import generate_thumbnail
from utils import get_required_env, record_event, thumbnail_key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_SOURCE_BUCKET = get_required_env("SOURCE_BUCKET")
_THUMBNAIL_BUCKET = get_required_env("THUMBNAIL_BUCKET")
_DB_URL = os.environ.get("NEON_DATABASE_URL")


def _extract_bucket_key(event):
    """Extract (source_bucket, s3_key) from a direct invocation, S3 notification, or EventBridge event."""
    if "s3_key" in event:
        return event.get("source_bucket", _SOURCE_BUCKET), event["s3_key"]
    if "Records" in event:
        s3 = event["Records"][0].get("s3", {})
        return s3.get("bucket", {}).get("name", _SOURCE_BUCKET), s3.get("object", {}).get("key")
    if event.get("source") == "aws.s3":
        detail = event.get("detail", {})
        return detail.get("bucket", {}).get("name", _SOURCE_BUCKET), detail.get("object", {}).get("key")
    return _SOURCE_BUCKET, None


def _emit_thumbnail_event(s3_key: str, source_bucket: str, status: str, content_hash: str | None) -> None:
    """Best-effort photo_events write. Never raises — thumbnail success must
    not be reported as failure when Neon is briefly unreachable.
    """
    if not _DB_URL:
        logger.warning("NEON_DATABASE_URL not set; skipping photo_events write")
        return
    event_type = "thumbnail_created" if status == "thumbnailed" else "thumbnail_skipped"
    try:
        conn = psycopg2.connect(_DB_URL, connect_timeout=5)
        try:
            with conn.cursor() as cur:
                # Look up the photo row if one exists for this key+bucket so the
                # event links back to it; for image_handler-driven invocations
                # the row may not exist yet, in which case photo_id stays NULL.
                cur.execute(
                    "SELECT id FROM photos WHERE s3_key = %s AND bucket = %s",
                    (s3_key, source_bucket),
                )
                row = cur.fetchone()
                photo_id = row[0] if row else None
                details = {"content_hash": content_hash} if content_hash else None
                record_event(
                    cur, s3_key, source_bucket, event_type, "thumbnailer",
                    photo_id=photo_id, details=details,
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("Failed to write %s photo_events row for %s", event_type, s3_key)


def lambda_handler(event, context):
    source_bucket, s3_key = _extract_bucket_key(event)
    if not s3_key:
        raise ValueError(f"Could not extract s3_key from event: {event}")

    logger.info("Thumbnailing s3://%s/%s", source_bucket, s3_key)

    s3 = boto3.client("s3")
    content_hash = event.get("content_hash")
    status = generate_thumbnail(s3_key, source_bucket, _THUMBNAIL_BUCKET, s3, content_hash=content_hash)

    actual_thumb_key = f"thumbnails/{content_hash}.webp" if content_hash else thumbnail_key(s3_key)

    _emit_thumbnail_event(s3_key, source_bucket, status, content_hash)

    return {"status": status, "s3_key": s3_key, "thumbnail_key": actual_thumb_key}
