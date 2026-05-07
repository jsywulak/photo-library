"""
Step definitions for photo_events_lambda.feature.

Asserts that deployed Lambdas write rows to the photo_events table in Neon
when handling their endpoints. Reads context.inbox_s3_key (set by inbox steps)
or context.last_photo_key (set by searcher seed steps) to identify the photo.
"""

from behave import then

from common import neon_conn


def _select_event(s3_key, event_type, actor=None, tag=None):
    sql = (
        "SELECT id, actor, details FROM photo_events"
        " WHERE s3_key = %s AND event_type = %s"
    )
    params = [s3_key, event_type]
    if actor is not None:
        sql += " AND actor = %s"
        params.append(actor)
    if tag is not None:
        sql += " AND details->>'tag' = %s"
        params.append(tag)
    sql += " ORDER BY id DESC LIMIT 1"

    conn = neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    finally:
        conn.close()


@then('a photo_events row with event_type "{event_type}" and actor "{actor}" should exist in Neon for the inbox photo')
def step_neon_event_inbox(context, event_type, actor):
    s3_key = context.inbox_s3_key
    row = _select_event(s3_key, event_type, actor=actor)
    assert row is not None, (
        f"No photo_events row with event_type={event_type!r}, actor={actor!r} found in Neon for {s3_key!r}"
    )


@then('a photo_events row with event_type "{event_type}" and actor "{actor}" should exist in Neon for the seeded photo')
def step_neon_event_seeded(context, event_type, actor):
    s3_key = context.last_photo_key
    row = _select_event(s3_key, event_type, actor=actor)
    assert row is not None, (
        f"No photo_events row with event_type={event_type!r}, actor={actor!r} found in Neon for {s3_key!r}"
    )


@then('a photo_events row with event_type "{event_type}" and actor "{actor}" should exist in Neon for the seeded photo with tag "{tag}" in details')
def step_neon_event_seeded_with_tag(context, event_type, actor, tag):
    s3_key = context.last_photo_key
    row = _select_event(s3_key, event_type, actor=actor, tag=tag)
    assert row is not None, (
        f"No photo_events row with event_type={event_type!r}, actor={actor!r}, "
        f"details.tag={tag!r} found in Neon for {s3_key!r}"
    )


@then('a photo_events row with event_type "{event_type}" and actor "{actor}" should exist in Neon for the inbox key')
@then('a photo_events row with event_type "{event_type}" and actor "{actor}" should exist in Neon for the photo')
def step_neon_event_test_s3_key(context, event_type, actor):
    s3_key = context.test_s3_key
    row = _select_event(s3_key, event_type, actor=actor)
    assert row is not None, (
        f"No photo_events row with event_type={event_type!r}, actor={actor!r} found in Neon for {s3_key!r}"
    )
