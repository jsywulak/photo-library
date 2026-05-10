"""
Step definitions for photo_state.feature.

Asserts that the photos.state column transitions correctly through the
local processing path. Uses context.conn from environment.py so the
rollback isolation pattern still applies.
"""

from behave import then


@then('"{key}" should have state "{state}" in the database')
def step_has_state(context, key, state):
    db_key = context.key_map.get(key, key)
    with context.conn.cursor() as cur:
        cur.execute("SELECT state FROM photos WHERE s3_key = %s", (db_key,))
        row = cur.fetchone()
    assert row, f"{db_key!r} not found in photos table"
    assert row[0] == state, f"Expected state {state!r} for {db_key!r}, got {row[0]!r}"


@then('"{key}" should have tagged_at populated in the database')
def step_has_tagged_at(context, key):
    db_key = context.key_map.get(key, key)
    with context.conn.cursor() as cur:
        cur.execute("SELECT tagged_at FROM photos WHERE s3_key = %s", (db_key,))
        row = cur.fetchone()
    assert row, f"{db_key!r} not found in photos table"
    assert row[0] is not None, f"tagged_at is NULL for {db_key!r}"
