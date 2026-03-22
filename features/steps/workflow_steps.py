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

import os
import time
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
import psycopg2
from behave import given, then

from common import neon_conn, thumbnail_key as _thumbnail_key

IMAGES_DIR = Path(__file__).parents[2] / "images"


@given("a photo is uploaded to the photos bucket")
def step_upload_photo(context):
    images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.jpeg"))
    assert images, f"No sample images found in {IMAGES_DIR}"

    s3_key = f"test-{uuid.uuid4().hex[:8]}-{images[0].name}"
    bucket = os.environ["S3_BUCKET"]

    boto3.client("s3").upload_file(str(images[0]), bucket, s3_key)

    context.test_s3_key = s3_key
    context.test_s3_bucket = bucket
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
