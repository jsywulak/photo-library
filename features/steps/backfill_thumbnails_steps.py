"""
Step definitions for backfill_thumbnails.feature.

Requires in .env:
  - S3_BUCKET                bucket containing source photos (photo-tagging-photos)
  - THUMBNAIL_BUCKET         bucket for thumbnails (photo-tagging-thumbnails)
  - THUMBNAILER_LAMBDA_NAME  name of the deployed thumbnailer Lambda

Uploads a real photo to S3, seeds a matching Neon DB record, runs the backfill,
and asserts the thumbnail was created. Cleanup is handled by environment.py via
context.searcher_s3_uploads, context.neon_test_s3_keys, and context.test_thumbnail_*.
"""

import hashlib
import os
import sys
import uuid
from pathlib import Path

import boto3
from behave import given, then, when

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from common import neon_conn, seed_photo, thumbnail_key as _thumbnail_key

IMAGES_DIR = Path(__file__).parents[2] / "images"


@given("a processed photo exists in the database and S3")
def step_processed_photo_in_db_and_s3(context):
    if not hasattr(context, "neon_test_s3_keys"):
        context.neon_test_s3_keys = []
    if not hasattr(context, "searcher_s3_uploads"):
        context.searcher_s3_uploads = []

    bucket = os.environ["S3_BUCKET"]
    images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.jpeg"))
    assert images, f"No sample images found in {IMAGES_DIR}"

    prefix = f"testA6FA7E1D-{uuid.uuid4().hex[:8]}-"
    s3_key = prefix + images[0].name

    boto3.client("s3").upload_file(str(images[0]), bucket, s3_key)
    context.searcher_s3_uploads.append((bucket, s3_key))

    conn = neon_conn()
    seed_photo(conn, s3_key, ["test"])
    conn.commit()
    conn.close()

    context.neon_test_s3_keys.append(s3_key)
    context.backfill_s3_key = s3_key
    context.backfill_source_bucket = bucket
    context.test_thumbnail_key = _thumbnail_key(s3_key)
    context.test_thumbnail_bucket = os.environ["THUMBNAIL_BUCKET"]


@given("an inbox photo exists in the database and inbox S3 bucket")
def step_inbox_photo_in_db_and_s3(context):
    if not hasattr(context, "neon_test_s3_keys"):
        context.neon_test_s3_keys = []
    if not hasattr(context, "searcher_s3_uploads"):
        context.searcher_s3_uploads = []

    inbox_bucket = os.environ["INBOX_BUCKET"]
    images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.jpeg"))
    assert images, f"No sample images found in {IMAGES_DIR}"

    prefix = f"testA6FA7E1D-{uuid.uuid4().hex[:8]}-"
    s3_key = prefix + images[0].name
    content_hash = hashlib.sha256(images[0].read_bytes()).hexdigest()

    boto3.client("s3").upload_file(str(images[0]), inbox_bucket, s3_key)
    context.searcher_s3_uploads.append((inbox_bucket, s3_key))

    conn = neon_conn()
    seed_photo(conn, s3_key, [], bucket=inbox_bucket, content_hash=content_hash)
    conn.commit()
    conn.close()

    context.neon_test_s3_keys.append(s3_key)
    context.backfill_s3_key = s3_key
    context.backfill_source_bucket = inbox_bucket
    context.backfill_content_hash = content_hash
    context.test_thumbnail_key = f"thumbnails/{content_hash}.webp"
    context.test_thumbnail_bucket = os.environ["THUMBNAIL_BUCKET"]


@when("the backfill script runs for that photo")
def step_run_backfill(context):
    from backfill_thumbnails import run_backfill

    lam = boto3.client("lambda")
    context.backfill_result = run_backfill(
        s3_keys=[context.backfill_s3_key],
        lambda_client=lam,
        lambda_name=os.environ["THUMBNAILER_LAMBDA_NAME"],
    )


@when("the inbox backfill script runs for that photo")
def step_run_inbox_backfill(context):
    from backfill_inbox_thumbnails import run_inbox_backfill

    lam = boto3.client("lambda")
    context.backfill_result = run_inbox_backfill(
        rows=[(context.backfill_s3_key, context.backfill_content_hash)],
        inbox_bucket=context.backfill_source_bucket,
        lambda_client=lam,
        lambda_name=os.environ["THUMBNAILER_LAMBDA_NAME"],
    )


@then("a thumbnail should exist in the thumbnail bucket for that photo")
def step_thumbnail_exists_for_photo(context):
    s3 = boto3.client("s3")
    try:
        s3.head_object(Bucket=context.test_thumbnail_bucket, Key=context.test_thumbnail_key)
    except s3.exceptions.ClientError:
        raise AssertionError(
            f"Thumbnail {context.test_thumbnail_key!r} not found in "
            f"{context.test_thumbnail_bucket!r}"
        )


@then("the backfill result should show 0 thumbnailed and 1 skipped")
def step_backfill_result_counts(context):
    result = context.backfill_result
    assert result["thumbnailed"] == 0, (
        f"Expected 0 thumbnailed, got {result['thumbnailed']}"
    )
    assert result["skipped"] == 1, (
        f"Expected 1 skipped, got {result['skipped']}"
    )


@when("the metadata backfill runs for that photo")
def step_run_metadata_backfill(context):
    from backfill_thumbnails import run_metadata_backfill

    s3 = boto3.client("s3")
    context.metadata_backfill_result = run_metadata_backfill(
        rows=[(context.backfill_s3_key, None)],
        source_bucket=context.backfill_source_bucket,
        thumbnail_bucket=context.test_thumbnail_bucket,
        s3_client=s3,
    )


@when("the inbox metadata backfill runs for that photo")
def step_run_inbox_metadata_backfill(context):
    from backfill_inbox_thumbnails import run_inbox_metadata_backfill

    s3 = boto3.client("s3")
    context.metadata_backfill_result = run_inbox_metadata_backfill(
        rows=[(context.backfill_s3_key, context.backfill_content_hash)],
        thumbnail_bucket=context.test_thumbnail_bucket,
        s3_client=s3,
    )


@then("the thumbnail should have source-hash metadata")
def step_thumbnail_has_source_hash_metadata(context):
    s3 = boto3.client("s3")
    response = s3.head_object(Bucket=context.test_thumbnail_bucket, Key=context.test_thumbnail_key)
    metadata = response.get("Metadata", {})
    assert "source-hash" in metadata, (
        f"Expected 'source-hash' in thumbnail metadata, got: {metadata}"
    )
    source_hash = metadata["source-hash"]
    assert len(source_hash) == 64 and all(c in "0123456789abcdef" for c in source_hash), (
        f"Expected 64-char hex string for source-hash, got: {source_hash!r}"
    )
