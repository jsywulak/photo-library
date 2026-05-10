"""
Step definitions for inbox_live.feature.

Opens the real FRONTEND_DOMAIN/inbox.html page in a Playwright browser with
real inbox data, then processes and archives specific test photos.

Requires in .env:
  - FRONTEND_DOMAIN     Base URL of the live frontend (e.g. http://lax.jsywulak.com)
  - INBOX_BUCKET        S3 inbox bucket
  - S3_BUCKET           S3 photos bucket (destination after process-inbox)
  - NEON_DATABASE_URL   Neon database connection string

Cleanup is handled by environment.py via context.searcher_s3_uploads and
context.neon_test_s3_keys. The processed photo's hash-based S3 key is added
to those lists after the process step runs.
"""

import hashlib
import os
import struct
import uuid
from pathlib import Path

import boto3
import psycopg2
from behave import given, then, when
from botocore.exceptions import ClientError

from common import neon_conn

IMAGES_DIR = Path(__file__).parents[2] / "images"


def _make_unique_jpeg(image_bytes: bytes) -> bytes:
    """Insert a UUID JPEG comment block before the EOI marker."""
    assert image_bytes[-2:] == b"\xff\xd9", "Not a valid JPEG (missing EOI marker)"
    uid = uuid.uuid4().bytes
    comment_data = b"test-run-" + uid
    length = len(comment_data) + 2
    com_block = b"\xff\xfe" + struct.pack(">H", length) + comment_data
    return image_bytes[:-2] + com_block + b"\xff\xd9"


def _upload_inbox_photo(filename: str, context) -> tuple[str, str]:
    """Upload a unique version of filename to INBOX_BUCKET and insert a Neon record.

    Returns (s3_key, content_hash).
    """
    image_path = IMAGES_DIR / filename
    assert image_path.exists(), f"Test image not found: {image_path}"

    image_bytes = _make_unique_jpeg(image_path.read_bytes())
    content_hash = hashlib.sha256(image_bytes).hexdigest()

    prefix = f"testA6FA7E1D-{uuid.uuid4().hex[:8]}-"
    s3_key = prefix + filename
    bucket = os.environ["INBOX_BUCKET"]

    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=image_bytes,
        ContentType="image/jpeg",
    )

    conn = neon_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO photos (s3_key, bucket, content_hash, captured_at)"
            " VALUES (%s, %s, %s, '1970-01-01 00:00:00+00')"
            " ON CONFLICT (content_hash)"
            " DO UPDATE SET s3_key = EXCLUDED.s3_key, bucket = EXCLUDED.bucket, captured_at = EXCLUDED.captured_at",
            (s3_key, bucket, content_hash),
        )
    conn.commit()
    conn.close()

    context.searcher_s3_uploads.append((bucket, s3_key))
    context.neon_test_s3_keys.append(s3_key)

    return s3_key, content_hash


@given("two test photos are uploaded to the inbox bucket with current timestamps")
def step_upload_two_inbox_photos(context):
    if not hasattr(context, "searcher_s3_uploads"):
        context.searcher_s3_uploads = []
    if not hasattr(context, "neon_test_s3_keys"):
        context.neon_test_s3_keys = []

    s3_key1, hash1 = _upload_inbox_photo("photo1.jpg", context)
    s3_key2, hash2 = _upload_inbox_photo("photo2.jpg", context)

    context.inbox_s3_key1 = s3_key1
    context.inbox_content_hash1 = hash1
    context.inbox_s3_key2 = s3_key2
    context.inbox_content_hash2 = hash2


@when("I open the live inbox page")
def step_open_live_inbox_page(context):
    frontend = os.environ["FRONTEND_DOMAIN"].rstrip("/")
    context.page.goto(f"{frontend}/inbox")
    context.page.wait_for_load_state("networkidle")


@then("both test photos are visible in the inbox grid")
def step_both_photos_visible(context):
    page = context.page
    page.wait_for_selector(f'img[alt="{context.inbox_s3_key1}"]', timeout=15000)
    page.wait_for_selector(f'img[alt="{context.inbox_s3_key2}"]', timeout=5000)


@when("I process the first test photo")
def step_process_first_photo(context):
    page = context.page
    # Click the thumbnail to open the lightbox
    page.locator(f'img[alt="{context.inbox_s3_key1}"]').click()
    page.wait_for_selector("#lightbox:not(.hidden)", timeout=5000)
    # Click Process
    page.locator("#lightbox-process").click()
    # Wait for the grid item to be removed from DOM
    page.wait_for_selector(f'img[alt="{context.inbox_s3_key1}"]', state="detached", timeout=15000)


@then("the first photo is removed from the inbox grid")
def step_first_photo_removed(context):
    assert context.page.locator(f'img[alt="{context.inbox_s3_key1}"]').count() == 0, (
        f"Expected photo {context.inbox_s3_key1!r} to be removed from inbox grid"
    )


@then("the first photo exists in the photos bucket")
def step_first_photo_in_photos_bucket(context):
    photos_bucket = os.environ["S3_BUCKET"]
    hash_key = f"{context.inbox_content_hash1}.jpg"
    try:
        boto3.client("s3").head_object(Bucket=photos_bucket, Key=hash_key)
    except ClientError as e:
        raise AssertionError(
            f"Expected {hash_key!r} in photos bucket {photos_bucket!r}: {e}"
        )
    # Register for cleanup
    context.searcher_s3_uploads.append((photos_bucket, hash_key))
    context.neon_test_s3_keys.append(hash_key)


@when("I archive the second test photo")
def step_archive_second_photo(context):
    page = context.page
    # After processing photo1 the lightbox auto-advances to the next item (possibly photo2).
    # Close whatever is open, then explicitly open photo2.
    if page.locator("#lightbox:not(.hidden)").count():
        page.locator("#lightbox-close").click()
        # Wait for #lightbox to gain the "hidden" class (state="attached" since it has display:none)
        page.wait_for_selector("#lightbox.hidden", state="attached", timeout=5000)
    # Click the thumbnail to open the lightbox with photo2
    page.locator(f'img[alt="{context.inbox_s3_key2}"]').click()
    page.wait_for_selector("#lightbox:not(.hidden)", timeout=5000)
    # Click Archive
    page.locator("#lightbox-archive").click()
    page.wait_for_selector(f'img[alt="{context.inbox_s3_key2}"]', state="detached", timeout=15000)


@then("the second photo is removed from the inbox grid")
def step_second_photo_removed(context):
    assert context.page.locator(f'img[alt="{context.inbox_s3_key2}"]').count() == 0, (
        f"Expected photo {context.inbox_s3_key2!r} to be removed from inbox grid"
    )


@then("the second photo is marked archived in Neon")
def step_second_photo_archived_in_neon(context):
    conn = neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT archived_at FROM photos WHERE content_hash = %s AND bucket = %s",
                (context.inbox_content_hash2, os.environ["INBOX_BUCKET"]),
            )
            row = cur.fetchone()
        assert row, f"No Neon record found for content_hash {context.inbox_content_hash2!r}"
        assert row[0] is not None, "Expected archived_at to be set, got NULL"
    finally:
        conn.close()
