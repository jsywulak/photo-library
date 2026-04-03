"""
Step definitions for search_live.feature.

Uploads a photo directly to the photos bucket to trigger the processor Lambda
via EventBridge, then opens the live search page and verifies the photo appears
in results when searching for "clean".

Requires in .env:
  - S3_BUCKET           S3 photos bucket
  - NEON_DATABASE_URL   Neon database connection string
  - FRONTEND_DOMAIN     Base URL of the live frontend (e.g. http://lax.jsywulak.com)

Cleanup is handled by environment.py via context.test_s3_key and context.test_s3_bucket.

The step "the photo should be processed and stored in the database within N seconds"
is defined in workflow_steps.py and reused here.
"""

import hashlib
import os
import struct
import uuid
from pathlib import Path

import boto3
from behave import given, when, then

IMAGES_DIR = Path(__file__).parents[2] / "images"
IMAGE_NAME = "PXL_20260319_193406856.jpg"


def _make_unique_jpeg(image_bytes: bytes) -> bytes:
    """Insert a UUID JPEG comment block before the EOI marker."""
    assert image_bytes[-2:] == b"\xff\xd9", "Not a valid JPEG (missing EOI marker)"
    uid = uuid.uuid4().bytes
    comment_data = b"test-run-" + uid
    length = len(comment_data) + 2
    com_block = b"\xff\xfe" + struct.pack(">H", length) + comment_data
    return image_bytes[:-2] + com_block + b"\xff\xd9"


@given("PXL_20260319_193406856.jpg is uploaded to the photos bucket")
def step_upload_pxl_to_photos_bucket(context):
    image_path = IMAGES_DIR / IMAGE_NAME
    assert image_path.exists(), f"Test image not found: {image_path}"

    image_bytes = _make_unique_jpeg(image_path.read_bytes())
    content_hash = hashlib.sha256(image_bytes).hexdigest()

    prefix = f"testA6FA7E1D-{uuid.uuid4().hex[:8]}-"
    s3_key = prefix + IMAGE_NAME
    bucket = os.environ["S3_BUCKET"]

    boto3.client("s3").put_object(
        Bucket=bucket,
        Key=s3_key,
        Body=image_bytes,
        ContentType="image/jpeg",
    )

    context.test_s3_key = s3_key
    context.test_s3_bucket = bucket
    context.test_content_hash = content_hash


@when("I open the live search page and search by a tag the photo received")
def step_open_search_with_photo_tag(context):
    from common import neon_conn
    # Pick the rarest tag among the photo's tags to stay within the 200-result limit
    conn = neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT t.name, COUNT(pt2.photo_id) AS cnt"
                " FROM photo_tags pt"
                " JOIN tags t ON t.id = pt.tag_id"
                " JOIN photo_tags pt2 ON pt2.tag_id = t.id"
                " WHERE pt.photo_id = %s"
                " GROUP BY t.name ORDER BY cnt ASC LIMIT 1",
                (context.neon_photo_id,),
            )
            row = cur.fetchone()
        assert row, f"No tags found for photo id {context.neon_photo_id}"
        tag = row[0]
    finally:
        conn.close()

    context.search_tag = tag
    frontend = os.environ["FRONTEND_DOMAIN"].rstrip("/")
    context.page.goto(f"{frontend}/index.html")
    context.page.wait_for_load_state("networkidle")
    context.page.locator("#tag-input").click()
    context.page.locator("#tag-input").fill(tag)
    context.page.keyboard.press("Enter")
    # Wait for grid items to appear (debounce is 400ms, then API call)
    context.page.wait_for_selector("#grid .grid-item", timeout=15000)


@then("the test photo appears in the search results")
def step_test_photo_in_search_results(context):
    page = context.page
    s3_key = context.test_s3_key
    # Results render img elements with alt = s3_key
    page.wait_for_selector(f'img[alt="{s3_key}"]', timeout=10000)
    assert page.locator(f'img[alt="{s3_key}"]').count() > 0, (
        f"Test photo {s3_key!r} not found in search results for 'clean'"
    )


@given("a tag exists in the Neon database with more than 200 photos")
def step_find_tag_with_many_photos(context):
    from common import neon_conn
    conn = neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT t.name, COUNT(pt.photo_id) AS cnt"
                " FROM tags t JOIN photo_tags pt ON pt.tag_id = t.id"
                " WHERE pt.removed_at IS NULL"
                " GROUP BY t.name HAVING COUNT(pt.photo_id) > 200"
                " ORDER BY cnt DESC LIMIT 1"
            )
            row = cur.fetchone()
    finally:
        conn.close()
    assert row, "No tag with more than 200 photos found in the database"
    context.many_results_tag = row[0]


@when("I open the live search page and search for that tag")
def step_search_for_many_results_tag(context):
    frontend = os.environ["FRONTEND_DOMAIN"].rstrip("/")
    context.page.goto(f"{frontend}/index.html")
    context.page.wait_for_load_state("networkidle")
    context.page.locator("#tag-input").fill(context.many_results_tag)
    context.page.keyboard.press("Enter")
    context.page.wait_for_selector("#grid .grid-item", timeout=15000)


@when('I click the "Load more" button on the search page')
def step_click_load_more_search(context):
    context.page.locator("#load-more-btn").wait_for(state="visible", timeout=5000)
    context.page.locator("#load-more-btn").click()
    context.page.wait_for_timeout(3000)


@then("I see more than 200 photos in the grid")
def step_grid_has_more_than_200(context):
    count = context.page.locator(".grid-item").count()
    assert count > 200, f"Expected more than 200 photos after Load more, got {count}"
