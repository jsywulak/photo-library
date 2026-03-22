"""
thumbnailer_handler.py — AWS Lambda entry point for the thumbnailer.

Accepts a direct invocation payload: {"s3_key": "..."}
Environment variables required:
  SOURCE_BUCKET     — S3 bucket to read photos from (photo-tagging-photos)
  THUMBNAIL_BUCKET  — S3 bucket to write thumbnails to (photo-tagging-thumbnails)
"""

import logging

import boto3

from thumbnailer import generate_thumbnail
from utils import thumbnail_key
from utils import get_required_env

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_SOURCE_BUCKET = get_required_env("SOURCE_BUCKET")
_THUMBNAIL_BUCKET = get_required_env("THUMBNAIL_BUCKET")


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


def lambda_handler(event, context):
    source_bucket, s3_key = _extract_bucket_key(event)
    if not s3_key:
        raise ValueError(f"Could not extract s3_key from event: {event}")

    logger.info("Thumbnailing s3://%s/%s", source_bucket, s3_key)

    s3 = boto3.client("s3")
    status = generate_thumbnail(s3_key, source_bucket, _THUMBNAIL_BUCKET, s3)

    return {"status": status, "s3_key": s3_key, "thumbnail_key": thumbnail_key(s3_key)}
