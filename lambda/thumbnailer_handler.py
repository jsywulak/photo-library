"""
thumbnailer_handler.py — AWS Lambda entry point for the thumbnailer.

Accepts a direct invocation payload: {"s3_key": "..."}
Environment variables required:
  SOURCE_BUCKET     — S3 bucket to read photos from (photo-tagging-photos)
  THUMBNAIL_BUCKET  — S3 bucket to write thumbnails to (photo-tagging-thumbnails)
"""

import logging
import os

import boto3

from thumbnailer import generate_thumbnail, thumbnail_key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_SOURCE_BUCKET = os.environ.get("SOURCE_BUCKET")
_THUMBNAIL_BUCKET = os.environ.get("THUMBNAIL_BUCKET")

if not _SOURCE_BUCKET:
    raise RuntimeError("SOURCE_BUCKET environment variable is not set")
if not _THUMBNAIL_BUCKET:
    raise RuntimeError("THUMBNAIL_BUCKET environment variable is not set")


def lambda_handler(event, context):
    s3_key = event.get("s3_key")
    if not s3_key:
        raise ValueError(f"No s3_key in event: {event}")

    logger.info("Thumbnailing s3://%s/%s", _SOURCE_BUCKET, s3_key)

    s3 = boto3.client("s3")
    status = generate_thumbnail(s3_key, _SOURCE_BUCKET, _THUMBNAIL_BUCKET, s3)

    return {"status": status, "thumbnail_key": thumbnail_key(s3_key)}
