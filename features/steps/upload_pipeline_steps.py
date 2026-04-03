"""
Step definitions for upload_pipeline.feature.

Full pipeline test: UPLOAD_BUCKET → image handler → INBOX_BUCKET + thumbnail →
process-inbox → S3_BUCKET → processor_v2 → tags in Neon.

Requires in .env:
  - UPLOAD_BUCKET       S3 staging bucket
  - INBOX_BUCKET        S3 inbox bucket
  - S3_BUCKET           S3 photos bucket
  - THUMBNAIL_BUCKET    S3 thumbnail bucket
  - INBOX_URL           Function URL of the inbox Lambda
  - API_KEY             API key for the inbox Lambda
  - NEON_DATABASE_URL   Neon database connection string

Cleanup is handled by environment.py via:
  - context.test_upload_s3_key  → upload bucket (if handler didn't delete it)
  - context.test_s3_key         → photos bucket after process-inbox step updates test_s3_bucket
  - context.test_s3_bucket      → updated to S3_BUCKET after process-inbox
  - context.test_thumbnail_key  → thumbnail bucket

Steps "the photo should be processed and stored in the database within N seconds"
and "a thumbnail should exist in the thumbnail bucket within N seconds" are
defined in workflow_steps.py and reused here.
"""

import hashlib
import json
import os
import struct
import time
import urllib.request
import uuid
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from behave import given, then, when

from common import neon_conn

IMAGES_DIR = Path(__file__).parents[2] / "images"
IMAGE_NAME = "PXL_20260319_193406856.jpg"


def _make_unique_jpeg(image_bytes: bytes) -> bytes:
    """Insert a UUID JPEG comment block before the EOI marker to produce unique bytes."""
    assert image_bytes[-2:] == b"\xff\xd9", "Not a valid JPEG (missing EOI marker)"
    uid = uuid.uuid4().bytes
    comment_data = b"test-run-" + uid
    length = len(comment_data) + 2
    com_block = b"\xff\xfe" + struct.pack(">H", length) + comment_data
    return image_bytes[:-2] + com_block + b"\xff\xd9"


def _api_post(path, body_dict):
    url = os.environ["INBOX_URL"].rstrip("/") + path
    body = json.dumps(body_dict).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json", "x-api-key": os.environ["API_KEY"]},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read())


@given("PXL_20260319_193406856.jpg is uploaded to the upload bucket")
def step_upload_pxl_to_upload_bucket(context):
    image_path = IMAGES_DIR / IMAGE_NAME
    assert image_path.exists(), f"Test image not found: {image_path}"

    image_bytes = _make_unique_jpeg(image_path.read_bytes())
    content_hash = hashlib.sha256(image_bytes).hexdigest()

    prefix = f"testA6FA7E1D-{uuid.uuid4().hex[:8]}-"
    s3_key = prefix + IMAGE_NAME

    boto3.client("s3").put_object(
        Bucket=os.environ["UPLOAD_BUCKET"],
        Key=s3_key,
        Body=image_bytes,
        ContentType="image/jpeg",
    )

    context.test_upload_s3_key = s3_key
    context.test_upload_bucket = os.environ["UPLOAD_BUCKET"]
    context.test_content_hash = content_hash
    # After image handler runs, photo lands in inbox as {content_hash}.jpg
    context.test_s3_key = f"{content_hash}.jpg"
    context.test_s3_bucket = os.environ["INBOX_BUCKET"]
    context.test_thumbnail_key = f"thumbnails/{content_hash}.webp"
    context.test_thumbnail_bucket = os.environ["THUMBNAIL_BUCKET"]


@then("the photo should appear in the inbox bucket within {timeout:d} seconds")
def step_photo_in_inbox_within_timeout(context, timeout):
    s3 = boto3.client("s3")
    bucket = context.test_s3_bucket
    key = context.test_s3_key
    deadline = time.time() + timeout

    while time.time() < deadline:
        try:
            s3.head_object(Bucket=bucket, Key=key)
            return
        except ClientError:
            pass
        time.sleep(5)

    raise AssertionError(
        f"Photo {key!r} did not appear in {bucket!r} within {timeout} seconds"
    )


@when("the photo is submitted for processing via the inbox Lambda")
def step_submit_for_processing(context):
    status, body = _api_post("/process-inbox", {"s3_key": context.test_s3_key})
    assert status == 200, f"process-inbox returned HTTP {status}: {body}"
    # Photo moved from inbox to photos bucket; update context so cleanup targets right bucket
    context.test_s3_bucket = os.environ["S3_BUCKET"]


@then("the photo should have tags in the Neon database")
def step_photo_has_tags_in_neon(context):
    conn = neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM photo_tags WHERE photo_id = %s",
                (context.neon_photo_id,),
            )
            count = cur.fetchone()[0]
        assert count > 0, f"No tags found for photo id {context.neon_photo_id}"
    finally:
        conn.close()
