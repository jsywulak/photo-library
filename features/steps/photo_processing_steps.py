"""
Step definitions for photo_processing.feature.

Steps interact only with:
  - The local filesystem (images/ directory in the project root)
  - The database (via the psycopg2 connection opened in environment.py)
  - The processor module (lambda/processor.py)

Isolation note: files are copied into a temp dir with a unique per-run prefix
(e.g. test-a1b2c3-photo1.jpg) so test s3_keys never collide with real data
that has been committed to the database by make process.
"""

import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import anthropic
from behave import given, when, then

sys.path.insert(0, str(Path(__file__).parents[2] / "lambda"))

IMAGES_DIR = Path(__file__).parents[2] / "images"


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------

@given("the database is empty")
def step_db_empty(context):
    context.location = None
    context.key_map = {}


@given('a local directory with photos "{photos}"')
def step_local_photos(context, photos):
    # Copy files to a temp dir with a unique prefix per scenario so s3_keys
    # can't clash with committed production data.
    names = [p.strip() for p in photos.split(",")]
    prefix = f"test-{uuid.uuid4().hex[:8]}-"
    tmp = tempfile.mkdtemp()
    context.temp_dirs.append(tmp)
    context.key_map = {name: prefix + name for name in names}
    for name, temp_name in context.key_map.items():
        src = IMAGES_DIR / name
        assert src.exists(), f"Sample image not found: images/{name}"
        shutil.copy(src, Path(tmp) / temp_name)
    context.location = tmp


@given('"{key}" is already in the database')
def step_key_in_db(context, key):
    db_key = context.key_map.get(key, key)
    with context.conn.cursor() as cur:
        cur.execute(
            "INSERT INTO photos (s3_key) VALUES (%s) ON CONFLICT DO NOTHING",
            (db_key,),
        )


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------

@when("the processor runs")
def step_run(context):
    import processor

    filenames = [f for f in os.listdir(context.location) if not f.startswith(".")]
    discovered = len(filenames)
    processed = skipped = 0

    for filename in filenames:
        image_bytes = (Path(context.location) / filename).read_bytes()
        status = processor.process_one(filename, image_bytes, context.conn, anthropic.Anthropic())
        if status == "skipped":
            skipped += 1
        else:
            processed += 1

    context.result = {"discovered": discovered, "processed": processed, "skipped": skipped}


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
    db_key = context.key_map.get(key, key)
    with context.conn.cursor() as cur:
        cur.execute("SELECT id FROM photos WHERE s3_key = %s", (db_key,))
        assert cur.fetchone(), f"{db_key!r} not found in photos table"


@then('"{key}" should have tags in the database')
def step_has_tags(context, key):
    db_key = context.key_map.get(key, key)
    with context.conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM tags t
            JOIN photo_tags pt ON pt.tag_id = t.id
            JOIN photos p ON p.id = pt.photo_id
            WHERE p.s3_key = %s
            """,
            (db_key,),
        )
        count = cur.fetchone()[0]
    assert count > 0, f"No tags found for {db_key!r}"
