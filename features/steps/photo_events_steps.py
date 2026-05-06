"""
Step definitions for photo_events.feature.

Asserts that rows are written to the photo_events audit table by the local
processor. Reuses context.conn from environment.py so the transaction-rollback
isolation pattern still applies.

Note: when a scenario triggers an exception in process_one, the connection's
top-level transaction is aborted. The implementation must use savepoints so
later SELECTs against photo_events still succeed; until that lands, this test
will fail at the SELECT — which is the expected pre-implementation failure
described in the plan.
"""

from behave import then


def _select_event(conn, s3_key, event_type):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, details FROM photo_events WHERE s3_key = %s AND event_type = %s ORDER BY id DESC LIMIT 1",
            (s3_key, event_type),
        )
        return cur.fetchone()


@then('a photo_events row with event_type "{event_type}" should exist for "{key}"')
def step_event_exists(context, event_type, key):
    db_key = context.key_map.get(key, key)
    row = _select_event(context.conn, db_key, event_type)
    assert row is not None, (
        f"No photo_events row with event_type={event_type!r} found for {db_key!r}"
    )
    context.last_event_details = row[1]


@then('the "{event_type}" event details should include the model name')
def step_event_details_include_model(context, event_type):
    details = context.last_event_details
    assert details is not None, f"event_type={event_type!r} row had NULL details"
    assert "model" in details, f"event details missing 'model' key: {details!r}"
    assert details["model"], f"event details 'model' was empty: {details!r}"


@then('"{key}" should have processed_at NULL in the database')
def step_processed_at_null(context, key):
    db_key = context.key_map.get(key, key)
    with context.conn.cursor() as cur:
        cur.execute("SELECT processed_at FROM photos WHERE s3_key = %s", (db_key,))
        row = cur.fetchone()
    assert row, f"{db_key!r} not found in photos table"
    assert row[0] is None, f"Expected processed_at NULL for {db_key!r}, got {row[0]}"
