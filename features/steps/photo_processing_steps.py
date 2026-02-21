"""
Step definitions for photo_processing.feature.

Steps interact only with:
  - The local filesystem (images/ directory in the project root)
  - The database (via the psycopg2 connection opened in environment.py)
  - The processor module (lambda/processor.py)
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

from behave import given, when, then

sys.path.insert(0, str(Path(__file__).parents[2] / "lambda"))


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------

IMAGES_DIR = Path(__file__).parents[2] / "images"


@given("the database is empty")
def step_db_empty(context):
    context.location = None


@given('a local directory with photos "{photos}"')
def step_local_photos(context, photos):
    # Verify the requested filenames exist in images/ before running.
    names = [p.strip() for p in photos.split(",")]
    for name in names:
        assert (IMAGES_DIR / name).exists(), f"Sample image not found: images/{name}"
    context.location = str(IMAGES_DIR)


@given('"{key}" is already in the database')
def step_key_in_db(context, key):
    with context.conn.cursor() as cur:
        cur.execute("INSERT INTO photos (s3_key) VALUES (%s)", (key,))


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------

@when("the processor runs")
def step_run(context):
    import processor

    # Anthropic is mocked here so the processor can run end-to-end without
    # a real API key. Tests make no assertions about it.
    anthropic_client = MagicMock()
    anthropic_client.messages.create.return_value.content = [
        MagicMock(text=json.dumps({"summary": "test photo", "tags": ["test-tag"]}))
    ]

    context.result = processor.process(context.location, context.conn, anthropic_client)


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------

@then("{count:d} photos should be discovered")
def step_discovered(context, count):
    assert context.result["discovered"] == count, (
        f"Expected {count} discovered, got {context.result['discovered']}"
    )


@then("{count:d} photo should be processed")
def step_processed(context, count):
    assert context.result["processed"] == count, (
        f"Expected {count} processed, got {context.result['processed']}"
    )


@then("{count:d} photo should be skipped")
def step_skipped(context, count):
    assert context.result["skipped"] == count, (
        f"Expected {count} skipped, got {context.result['skipped']}"
    )


@then('"{key}" should be saved to the database')
def step_photo_saved(context, key):
    with context.conn.cursor() as cur:
        cur.execute("SELECT id FROM photos WHERE s3_key = %s", (key,))
        assert cur.fetchone(), f"{key!r} not found in photos table"


@then('"{key}" should have tags in the database')
def step_has_tags(context, key):
    with context.conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM tags t
            JOIN photo_tags pt ON pt.tag_id = t.id
            JOIN photos p ON p.id = pt.photo_id
            WHERE p.s3_key = %s
            """,
            (key,),
        )
        count = cur.fetchone()[0]
    assert count > 0, f"No tags found for {key!r}"
