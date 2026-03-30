"""
Step definitions for inbox_ordering.feature.

Calls list_inbox() from inbox.py directly against the local DB with a stub S3 client.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from behave import given, then, when

sys.path.insert(0, str(Path(__file__).parents[2] / "lambda"))

INBOX_BUCKET = "photo-tagging-inbox"
THUMBNAIL_BUCKET = "photo-tagging-thumbnails"


class _FakeS3:
    """Minimal S3 client stub — returns a predictable URL for presigned requests."""
    def generate_presigned_url(self, operation, Params, ExpiresIn):
        return f"https://fake.s3/{Params['Key']}"


def _seed_inbox_photo(conn, s3_key, captured_at=None):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO photos (s3_key, bucket, captured_at) VALUES (%s, %s, %s) RETURNING id",
            (s3_key, INBOX_BUCKET, captured_at),
        )
        return cur.fetchone()[0]


@given('an inbox photo "{s3_key}" with captured_at "{dt_str}"')
def step_inbox_photo_with_captured_at(context, s3_key, dt_str):
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    _seed_inbox_photo(context.conn, s3_key, dt)


@given('an inbox photo "{s3_key}" with no captured_at')
def step_inbox_photo_no_captured_at(context, s3_key):
    _seed_inbox_photo(context.conn, s3_key, None)


@when("I list the inbox")
def step_list_inbox(context):
    import inbox
    context.inbox_result = inbox.list_inbox(
        context.conn, _FakeS3(), INBOX_BUCKET, THUMBNAIL_BUCKET
    )
    context.inbox_cursor = None


@when("I list the inbox with limit {limit:d}")
def step_list_inbox_with_limit(context, limit):
    import inbox
    context.inbox_result = inbox.list_inbox(
        context.conn, _FakeS3(), INBOX_BUCKET, THUMBNAIL_BUCKET, limit=limit
    )
    context.inbox_cursor = context.inbox_result.get("next_cursor")


@when("I list the inbox with the next cursor and limit {limit:d}")
def step_list_inbox_with_cursor(context, limit):
    import inbox
    context.inbox_result = inbox.list_inbox(
        context.conn, _FakeS3(), INBOX_BUCKET, THUMBNAIL_BUCKET,
        limit=limit, cursor=context.inbox_cursor
    )
    context.inbox_cursor = context.inbox_result.get("next_cursor")


@then('the inbox results should be in order "{keys}"')
def step_inbox_order(context, keys):
    expected = [k.strip() for k in keys.split(",")]
    actual = [item["s3_key"] for item in context.inbox_result["items"]]
    assert actual == expected, f"Expected order {expected}, got {actual}"


@then("the inbox listing has a next_cursor")
def step_has_next_cursor(context):
    assert context.inbox_result.get("next_cursor") is not None, "Expected next_cursor but got None"


@then("the inbox listing has no next_cursor")
def step_no_next_cursor(context):
    assert context.inbox_result.get("next_cursor") is None, (
        f"Expected no next_cursor but got {context.inbox_result.get('next_cursor')!r}"
    )
