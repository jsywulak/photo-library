"""
Step definitions for inbox_lambda.feature.

Requires in .env:
  - INBOX_LAMBDA_NAME  name of the deployed inbox Lambda function
  - INBOX_URL          Function URL of the deployed inbox Lambda
  - NEON_DATABASE_URL  for seeding test data and verifying results
  - INBOX_BUCKET       S3 bucket for unprocessed photos
  - S3_BUCKET          photos bucket (for process-inbox verification)

Steps are suffixed with "v2" to avoid conflicts with the duplicate steps in
searcher_lambda_steps.py while both suites coexist. The v2 suffix will be
removed when the inbox routes are removed from the searcher Lambda.
"""

import hashlib
import json
import os
import uuid

import boto3
import urllib.request
from behave import given, then, when

from common import neon_conn


def _api_get(path, api_key=None):
    url = os.environ["INBOX_URL"].rstrip("/") + path
    key = api_key if api_key is not None else os.environ["API_KEY"]
    req = urllib.request.Request(url, headers={"x-api-key": key}, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def _api_post(path, body_dict, api_key=None):
    url = os.environ["INBOX_URL"].rstrip("/") + path
    key = api_key if api_key is not None else os.environ["API_KEY"]
    body = json.dumps(body_dict).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"content-type": "application/json", "x-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, None


_MINIMAL_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
    b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
    b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x87"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
    b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
    b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd2\x8a(\x03\xff\xd9"
)


@given("the inbox Lambda is deployed")
def step_inbox_lambda_deployed(context):
    name = os.environ["INBOX_LAMBDA_NAME"]
    client = boto3.client("lambda")
    response = client.get_function(FunctionName=name)
    context.inbox_lambda_name = name
    context.inbox_lambda_state = response["Configuration"]["State"]


@then("the inbox function should be active")
def step_inbox_function_active(context):
    assert context.inbox_lambda_state == "Active", (
        f"Expected Lambda state Active, got {context.inbox_lambda_state!r}"
    )


@given("a photo is uploaded to the inbox bucket and recorded in the database v2")
def step_upload_to_inbox_with_db_v2(context):
    if not hasattr(context, "searcher_s3_uploads"):
        context.searcher_s3_uploads = []
    if not hasattr(context, "neon_test_s3_keys"):
        context.neon_test_s3_keys = []

    prefix = f"testA6FA7E1D-{uuid.uuid4().hex[:8]}-"
    s3_key = f"{prefix}photo.jpg"
    bucket = os.environ["INBOX_BUCKET"]
    content_hash = hashlib.sha256(_MINIMAL_JPEG).hexdigest()
    dest_key = f"{content_hash}.jpg"  # the eventual photos-bucket key after promotion

    boto3.client("s3").put_object(
        Bucket=bucket, Key=s3_key, Body=_MINIMAL_JPEG, ContentType="image/jpeg"
    )
    context.searcher_s3_uploads.append((bucket, s3_key))

    conn = neon_conn()
    with conn.cursor() as cur:
        # Defensive sweep: a late-arriving processor v2 invocation from a prior test
        # may have created a 'failed' row at dest_key with content_hash=NULL (escaping
        # the (content_hash) unique constraint). Clear it so the promotion UPDATE in
        # this scenario doesn't collide on (s3_key, bucket).
        cur.execute("DELETE FROM photos WHERE s3_key = %s", (dest_key,))
        cur.execute(
            "INSERT INTO photos (s3_key, bucket, captured_at, content_hash) VALUES (%s, %s, '1970-01-01 00:00:00+00', %s)"
            " ON CONFLICT (content_hash) DO UPDATE SET s3_key = EXCLUDED.s3_key, bucket = EXCLUDED.bucket, captured_at = EXCLUDED.captured_at"
            " RETURNING id",
            (s3_key, bucket, content_hash),
        )
        photo_id = cur.fetchone()[0]
    conn.commit()
    conn.close()

    context.neon_test_s3_keys.append(s3_key)
    # Promotion renames s3_key to {hash}.jpg in the photos bucket; track for cleanup.
    context.neon_test_s3_keys.append(f"{content_hash}.jpg")
    # Also clean by content_hash to catch the photos-bucket row a delayed processor v2
    # EventBridge invocation may re-insert AFTER the s3_key cleanup runs.
    if not hasattr(context, "neon_test_content_hash_buckets"):
        context.neon_test_content_hash_buckets = []
    context.neon_test_content_hash_buckets.append((content_hash, os.environ["INBOX_BUCKET"]))
    context.neon_test_content_hash_buckets.append((content_hash, os.environ["S3_BUCKET"]))
    context.inbox_s3_key = s3_key
    context.inbox_content_hash = content_hash
    context.inbox_photo_id = photo_id


@given('a photo with captured_at "{captured_at}", original_filename "{original_filename}", and a known content_hash exists in the inbox')
def step_inbox_photo_with_metadata(context, captured_at, original_filename):
    """Upload a unique JPEG to the inbox bucket and INSERT a photos row with the
    given metadata. Used by Slice 4 promotion-history scenarios."""
    import io
    from PIL import Image

    if not hasattr(context, "searcher_s3_uploads"):
        context.searcher_s3_uploads = []
    if not hasattr(context, "neon_test_s3_keys"):
        context.neon_test_s3_keys = []

    # Synthesize a unique JPEG so the content_hash is fresh and the test is hermetic.
    img = Image.new("RGB", (8, 8), color=(uuid.uuid4().int & 0xFF, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    image_bytes = buf.getvalue()
    content_hash = hashlib.sha256(image_bytes).hexdigest()

    bucket = os.environ["INBOX_BUCKET"]
    prefix = f"testA6FA7E1D-{uuid.uuid4().hex[:8]}-"
    s3_key = f"{prefix}{original_filename}"
    dest_key = f"{content_hash}.jpg"

    boto3.client("s3").put_object(
        Bucket=bucket, Key=s3_key, Body=image_bytes, ContentType="image/jpeg",
    )
    context.searcher_s3_uploads.append((bucket, s3_key))

    conn = neon_conn()
    with conn.cursor() as cur:
        # Defensive sweep — same rationale as step_upload_to_inbox_with_db_v2.
        cur.execute("DELETE FROM photos WHERE s3_key = %s", (dest_key,))
        cur.execute(
            "INSERT INTO photos (s3_key, bucket, captured_at, content_hash, original_filename)"
            " VALUES (%s, %s, %s, %s, %s)"
            " RETURNING id",
            (s3_key, bucket, captured_at, content_hash, original_filename),
        )
        photo_id = cur.fetchone()[0]
    conn.commit()
    conn.close()

    context.neon_test_s3_keys.append(s3_key)
    context.neon_test_s3_keys.append(f"{content_hash}.jpg")
    if not hasattr(context, "neon_test_content_hash_buckets"):
        context.neon_test_content_hash_buckets = []
    context.neon_test_content_hash_buckets.append((content_hash, os.environ["INBOX_BUCKET"]))
    context.neon_test_content_hash_buckets.append((content_hash, os.environ["S3_BUCKET"]))
    context.inbox_s3_key = s3_key
    context.inbox_content_hash = content_hash
    context.inbox_photo_id = photo_id
    context.inbox_captured_at = captured_at
    context.inbox_original_filename = original_filename


@given('a "received" photo_events row exists for the inbox photo')
def step_seed_received_event(context):
    conn = neon_conn()
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO photo_events (photo_id, s3_key, bucket, event_type, actor)"
            " VALUES (%s, %s, %s, 'received', 'image_handler')",
            (context.inbox_photo_id, context.inbox_s3_key, os.environ["INBOX_BUCKET"]),
        )
    conn.commit()
    conn.close()


def _fetch_photos_row_by_content_hash(content_hash):
    conn = neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, bucket, s3_key, captured_at, content_hash, original_filename"
                " FROM photos WHERE content_hash = %s ORDER BY id DESC LIMIT 1",
                (content_hash,),
            )
            return cur.fetchone()
    finally:
        conn.close()


@then("the photos row id should be preserved across promotion")
def step_photo_id_preserved(context):
    row = _fetch_photos_row_by_content_hash(context.inbox_content_hash)
    assert row is not None, f"No photos row for content_hash={context.inbox_content_hash!r}"
    assert row[0] == context.inbox_photo_id, (
        f"Expected photos.id {context.inbox_photo_id} preserved, got {row[0]} (DELETE+re-INSERT)"
    )


@then('the photos row bucket should now be "{bucket}"')
def step_photo_bucket_now(context, bucket):
    row = _fetch_photos_row_by_content_hash(context.inbox_content_hash)
    assert row is not None, "photos row not found by content_hash"
    assert row[1] == bucket, f"Expected bucket {bucket!r}, got {row[1]!r}"


@then('the photos row captured_at should still be "{expected}"')
def step_photo_captured_at_preserved(context, expected):
    row = _fetch_photos_row_by_content_hash(context.inbox_content_hash)
    assert row is not None, "photos row not found"
    actual = row[3].strftime("%Y-%m-%d %H:%M:%S")
    assert actual == expected, f"Expected captured_at {expected!r}, got {actual!r}"


@then('the photos row original_filename should still be "{expected}"')
def step_photo_original_filename_preserved(context, expected):
    row = _fetch_photos_row_by_content_hash(context.inbox_content_hash)
    assert row is not None, "photos row not found"
    assert row[5] == expected, f"Expected original_filename {expected!r}, got {row[5]!r}"


@then("the photos row content_hash should still be the original")
def step_photo_content_hash_preserved(context):
    row = _fetch_photos_row_by_content_hash(context.inbox_content_hash)
    assert row is not None, "photos row not found"
    assert row[4] == context.inbox_content_hash, (
        f"Expected content_hash {context.inbox_content_hash!r}, got {row[4]!r}"
    )


@then('the prior "received" photo_events row should still reference the same photo_id')
def step_received_event_preserved(context):
    conn = neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT photo_id FROM photo_events"
                " WHERE event_type = 'received' AND s3_key = %s",
                (context.inbox_s3_key,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    assert row is not None, f"'received' event for {context.inbox_s3_key!r} was lost (cascade-deleted by DELETE+re-INSERT)"
    assert row[0] == context.inbox_photo_id, (
        f"Expected received event photo_id {context.inbox_photo_id}, got {row[0]}"
    )


@then('a "promoted" photo_events row should exist for the same photo_id')
def step_promoted_event_for_photo_id(context):
    conn = neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM photo_events"
                " WHERE event_type = 'promoted' AND photo_id = %s",
                (context.inbox_photo_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    assert row is not None, (
        f"No 'promoted' event found with photo_id={context.inbox_photo_id} "
        f"(today inbox.py writes the event with photo_id=NULL because the row is being deleted)"
    )


@when("the inbox Function URL GET /inbox is called with the correct API key")
def step_get_inbox_correct_key(context):
    context.http_status, context.http_body = _api_get("/inbox")


@when("the inbox Function URL GET /inbox is called with an incorrect API key")
def step_get_inbox_wrong_key(context):
    context.http_status, _ = _api_get("/inbox", api_key="wrong-key")


@when("the inbox Function URL GET /inbox is called with limit {limit:d} and the correct API key")
def step_get_inbox_with_limit(context, limit):
    context.http_status, context.http_body = _api_get(f"/inbox?limit={limit}")
    context.inbox_last_limit = limit


@when("the inbox Function URL GET /inbox is called with the next cursor and the correct API key")
def step_get_inbox_with_next_cursor(context):
    cursor = context.http_body["next_cursor"]
    limit = getattr(context, "inbox_last_limit", 50)
    context.http_status, context.http_body = _api_get(f"/inbox?cursor={cursor}&limit={limit}")


@when('the inbox Function URL GET /inbox is called with cursor "{cursor}" and the correct API key')
def step_get_inbox_with_cursor_string(context, cursor):
    context.http_status, context.http_body = _api_get(f"/inbox?cursor={cursor}")


@when("the inbox Function URL POST /process-inbox is called for the inbox photo with the correct API key")
def step_process_inbox_photo(context):
    context.http_status, context.http_body = _api_post("/process-inbox", {"s3_key": context.inbox_s3_key})


@when("the inbox Function URL POST /process-inbox is called with an incorrect API key")
def step_process_inbox_wrong_key(context):
    context.http_status, _ = _api_post("/process-inbox", {"s3_key": "dummy.jpg"}, api_key="wrong-key")


@when("the inbox Function URL POST /archive-inbox is called for the inbox photo with the correct API key")
def step_archive_inbox_photo(context):
    context.http_status, context.http_body = _api_post("/archive-inbox", {"s3_key": context.inbox_s3_key})


@when("the inbox Function URL POST /archive-inbox is called with an incorrect API key")
def step_archive_inbox_wrong_key(context):
    context.http_status, _ = _api_post("/archive-inbox", {"s3_key": "dummy.jpg"}, api_key="wrong-key")


@then("the HTTP response status should be {status:d} v2")
def step_http_status_v2(context, status):
    assert context.http_status == status, (
        f"Expected HTTP {status}, got {context.http_status}"
    )


@then("the response body should contain the inbox photo with a presigned URL v2")
def step_inbox_contains_photo_v2(context):
    items = context.http_body.get("items", [])
    keys = {item["s3_key"] for item in items}
    assert context.inbox_s3_key in keys, (
        f"Expected {context.inbox_s3_key!r} in inbox response, got: {keys}"
    )
    result = next(r for r in items if r["s3_key"] == context.inbox_s3_key)
    assert "url" in result and result["url"].startswith("https://"), (
        f"Expected presigned URL in result, got: {result}"
    )


@then("each inbox result should include a thumbnail_url v2")
def step_inbox_results_have_thumbnail_url_v2(context):
    items = context.http_body.get("items", [])
    assert items, "Expected at least one inbox result"
    for result in items:
        assert "thumbnail_url" in result, f"Inbox result missing 'thumbnail_url': {result}"
        assert result["thumbnail_url"].startswith("https://"), (
            f"Expected HTTPS thumbnail URL, got: {result['thumbnail_url']!r}"
        )


@then("the response body should be a list v2")
def step_response_is_list_v2(context):
    assert isinstance(context.http_body, dict) and "items" in context.http_body, (
        f"Expected a paginated inbox response with 'items' key, got: {type(context.http_body)}"
    )


@then("the inbox response contains {n:d} item v2")
@then("the inbox response contains {n:d} items v2")
def step_inbox_response_contains_n_items_v2(context, n):
    assert isinstance(context.http_body, dict), f"Expected dict, got {type(context.http_body)}"
    items = context.http_body.get("items", [])
    assert len(items) == n, f"Expected {n} items, got {len(items)}"
    context.inbox_last_page_keys = {item["s3_key"] for item in items}


@then("the inbox response has a next_cursor v2")
def step_inbox_response_has_next_cursor_v2(context):
    cursor = context.http_body.get("next_cursor")
    assert cursor is not None, f"Expected a next_cursor, got None. Body: {context.http_body}"


@then("the inbox response items do not overlap with the previous page v2")
def step_inbox_no_overlap_v2(context):
    assert isinstance(context.http_body, dict), f"Expected dict, got {type(context.http_body)}"
    items = context.http_body.get("items", [])
    assert items, "Expected at least one item on the second page"
    current_keys = {item["s3_key"] for item in items}
    previous_keys = getattr(context, "inbox_last_page_keys", set())
    overlap = current_keys & previous_keys
    assert not overlap, f"Pages overlap on keys: {overlap}"


@then("the photos bucket should contain the photo at its hash-based key v2")
def step_photos_bucket_has_hash_key_v2(context):
    from botocore.exceptions import ClientError

    hash_key = f"{context.inbox_content_hash}.jpg"
    context.promoted_hash_key = hash_key

    photos_bucket = os.environ["S3_BUCKET"]
    if not hasattr(context, "searcher_s3_uploads"):
        context.searcher_s3_uploads = []
    if not hasattr(context, "neon_test_s3_keys"):
        context.neon_test_s3_keys = []
    context.searcher_s3_uploads.append((photos_bucket, hash_key))
    context.neon_test_s3_keys.append(hash_key)

    try:
        boto3.client("s3").head_object(Bucket=photos_bucket, Key=hash_key)
    except ClientError as e:
        assert False, f"Expected {hash_key!r} in photos bucket {photos_bucket!r}, but got: {e}"


@then("the inbox bucket should no longer contain the original photo v2")
def step_inbox_no_longer_has_photo_v2(context):
    from botocore.exceptions import ClientError

    inbox_bucket = os.environ["INBOX_BUCKET"]
    try:
        boto3.client("s3").head_object(Bucket=inbox_bucket, Key=context.inbox_s3_key)
        assert False, f"Expected {context.inbox_s3_key!r} to be deleted from inbox bucket but it still exists"
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        assert error_code in ("404", "NoSuchKey"), f"Unexpected S3 error: {e}"


@then("the inbox photo should no longer appear in GET /inbox")
def step_archived_photo_not_in_inbox(context):
    _, body = _api_get("/inbox")
    items = body.get("items", []) if body else []
    keys = {item["s3_key"] for item in items}
    assert context.inbox_s3_key not in keys, (
        f"Expected archived photo {context.inbox_s3_key!r} to be absent from inbox, but found it"
    )
