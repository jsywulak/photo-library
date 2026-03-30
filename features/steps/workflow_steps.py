"""
Step definitions for workflow.feature.

Tests the full end-to-end pipeline: S3 upload → EventBridge → processor Lambda
(tags stored in Neon) and thumbnailer Lambda (WebP written to thumbnail bucket).

Requires in .env:
  - S3_BUCKET           photos bucket
  - THUMBNAIL_BUCKET    thumbnail bucket
  - NEON_DATABASE_URL   for polling processing results

Cleanup is handled automatically by environment.py via context.test_s3_key,
context.test_s3_bucket, context.test_thumbnail_key, and context.test_thumbnail_bucket.
"""

import hashlib
import os
import struct
import time
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
import psycopg2
from behave import given, then

from common import neon_conn, thumbnail_key as _thumbnail_key

IMAGES_DIR = Path(__file__).parents[2] / "images"


def _make_unique_jpeg(image_bytes: bytes) -> bytes:
    """Insert a JPEG comment block containing a UUID before the EOI marker.

    This produces a unique SHA-256 hash per run while keeping the image valid
    and processable by Anthropic.  Comment blocks (FF FE) are ignored by image
    decoders.
    """
    assert image_bytes[-2:] == b"\xff\xd9", "Not a valid JPEG (missing EOI marker)"
    uid = uuid.uuid4().bytes  # 16 bytes, always unique
    comment_data = b"test-run-" + uid
    length = len(comment_data) + 2  # length field includes itself
    com_block = b"\xff\xfe" + struct.pack(">H", length) + comment_data
    return image_bytes[:-2] + com_block + b"\xff\xd9"


@given("a photo is uploaded to the photos bucket")
def step_upload_photo(context):
    images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.jpeg"))
    assert images, f"No sample images found in {IMAGES_DIR}"

    # Make the image bytes unique per run so the Lambda never treats this upload
    # as a duplicate of an already-processed production photo.
    image_bytes = _make_unique_jpeg(images[0].read_bytes())
    content_hash = hashlib.sha256(image_bytes).hexdigest()
    s3_key = f"test-{uuid.uuid4().hex[:8]}-{images[0].name}"
    bucket = os.environ["S3_BUCKET"]

    # Pre-clean: remove all stale test- S3 objects and Neon records from the
    # photos bucket before uploading. The workflow test runs last — any remaining
    # test- objects are genuinely stale (S3 delete failed silently in a prior
    # scenario's cleanup). Without this, a delayed EventBridge invocation for a
    # stale object can race with the workflow Lambda and win the content_hash
    # insert, causing the workflow Lambda to return "skipped" with no DB record.
    try:
        s3_client = boto3.client("s3")
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix="test-"):
            for obj in page.get("Contents", []):
                s3_client.delete_object(Bucket=bucket, Key=obj["Key"])
    except Exception:
        pass
    try:
        conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM photos WHERE bucket = %s AND s3_key LIKE 'test-%%'",
                (bucket,),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass

    boto3.client("s3").put_object(Bucket=bucket, Key=s3_key, Body=image_bytes, ContentType="image/jpeg")

    context.test_s3_key = s3_key
    context.test_s3_bucket = bucket
    context.test_content_hash = content_hash
    context.test_thumbnail_key = _thumbnail_key(s3_key)
    context.test_thumbnail_bucket = os.environ["THUMBNAIL_BUCKET"]


@then("the photo should be processed and stored in the database within {timeout:d} seconds")
def step_photo_processed(context, timeout):
    deadline = time.time() + timeout
    s3_key = context.test_s3_key

    while time.time() < deadline:
        conn = neon_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT processed_at, last_error FROM photos WHERE s3_key = %s AND bucket = %s",
                    (s3_key, context.test_s3_bucket),
                )
                row = cur.fetchone()
        finally:
            conn.close()

        if row:
            processed_at, last_error = row
            assert not last_error, f"Photo processing failed with error: {last_error}"
            if processed_at:
                context.neon_photo_id = _get_photo_id(s3_key, context.test_s3_bucket)
                return

        time.sleep(5)

    raise AssertionError(
        f"Photo {s3_key!r} was not processed within {timeout} seconds"
    )


@then("a thumbnail should exist in the thumbnail bucket within {timeout:d} seconds")
def step_thumbnail_exists(context, timeout):
    s3 = boto3.client("s3")
    bucket = context.test_thumbnail_bucket
    key = context.test_thumbnail_key
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            s3.head_object(Bucket=bucket, Key=key)
            return
        except ClientError:
            pass
        time.sleep(5)

    raise AssertionError(
        f"Thumbnail {key!r} did not appear in {bucket!r} within {timeout} seconds"
    )


def _get_photo_id(s3_key: str, bucket: str) -> int:
    conn = neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM photos WHERE s3_key = %s AND bucket = %s", (s3_key, bucket))
            return cur.fetchone()[0]
    finally:
        conn.close()
