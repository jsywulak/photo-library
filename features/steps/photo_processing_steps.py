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

import logging.handlers
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


@given('a local directory with an oversized image "{filename}"')
def step_oversized_image(context, filename):
    """Create a JPEG padded to 4.5 MB — above the base64 threshold but below 5 MB raw.

    Images in the 3.75–5 MB raw range slip past the old >5 MB resize check, but
    their base64 encoding (~6 MB) exceeds Anthropic's 5 MB limit.  We pad a tiny
    real JPEG to exactly 4.5 MB by inserting JPEG comment blocks (FF FE) before
    the end-of-image marker.  Comment blocks are ignored by image decoders, so
    the file is a valid JPEG that Anthropic can process after resizing.
    """
    import io
    import struct
    from PIL import Image

    TARGET_SIZE = int(4.5 * 1024 * 1024)  # 4.5 MB — between 3.75 MB and 5 MB

    # Build a small but valid base JPEG
    img = Image.new("RGB", (100, 100), color=(100, 149, 237))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    base_jpeg = buf.getvalue()
    assert base_jpeg[-2:] == b"\xff\xd9", "Unexpected JPEG structure"

    # Insert COM blocks (FF FE) before the EOI marker to reach TARGET_SIZE.
    # Each block: 2-byte marker + 2-byte length (includes itself) + data.
    body = bytearray(base_jpeg[:-2])  # everything except EOI
    remaining = TARGET_SIZE - len(base_jpeg)  # bytes still needed
    MAX_COM_DATA = 65533  # max data bytes per COM block (length field max 65535)
    while remaining > 0:
        data_size = min(remaining - 4, MAX_COM_DATA)
        if data_size <= 0:
            break
        body += b"\xff\xfe"
        body += struct.pack(">H", data_size + 2)
        body += b"\x00" * data_size
        remaining -= 4 + data_size
    body += b"\xff\xd9"  # EOI
    image_bytes = bytes(body)

    assert len(image_bytes) >= TARGET_SIZE, (
        f"Padded JPEG too small: {len(image_bytes)} bytes"
    )

    prefix = f"test-{uuid.uuid4().hex[:8]}-"
    tmp = tempfile.mkdtemp()
    context.temp_dirs.append(tmp)
    context.key_map = {filename: prefix + filename}
    (Path(tmp) / (prefix + filename)).write_bytes(image_bytes)
    context.location = tmp


@given('a local directory with a corrupted oversized image "{filename}"')
def step_corrupted_oversized_image(context, filename):
    """Create a file that is too large to skip resizing but is not valid JPEG.

    _prepare_image() will call Image.open() on anything above MAX_IMAGE_BYTES,
    which raises an exception on non-JPEG data — triggering the error-logging
    path without needing to call the Anthropic API.
    """
    from processor import MAX_IMAGE_BYTES

    prefix = f"test-{uuid.uuid4().hex[:8]}-"
    tmp = tempfile.mkdtemp()
    context.temp_dirs.append(tmp)
    context.key_map = {filename: prefix + filename}
    corrupt_bytes = b"\x00" * (MAX_IMAGE_BYTES + 1)
    (Path(tmp) / (prefix + filename)).write_bytes(corrupt_bytes)
    context.location = tmp


@given('a local directory with a JPEG with EXIF DateTimeOriginal "{exif_datetime}" named "{filename}"')
def step_jpeg_with_exif(context, exif_datetime, filename):
    """Create a minimal JPEG with a DateTimeOriginal EXIF tag."""
    import io
    from PIL import Image

    img = Image.new("RGB", (100, 100), color=(80, 80, 80))
    exif = img.getexif()
    exif[36867] = exif_datetime  # DateTimeOriginal tag ID
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())

    prefix = f"test-{uuid.uuid4().hex[:8]}-"
    tmp = tempfile.mkdtemp()
    context.temp_dirs.append(tmp)
    context.key_map = {filename: prefix + filename}
    (Path(tmp) / (prefix + filename)).write_bytes(buf.getvalue())
    context.location = tmp


@given('a local directory with a JPEG without EXIF named "{filename}"')
def step_jpeg_without_exif(context, filename):
    """Create a minimal JPEG with no EXIF data."""
    import io
    from PIL import Image

    img = Image.new("RGB", (100, 100), color=(80, 80, 80))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    prefix = f"test-{uuid.uuid4().hex[:8]}-"
    tmp = tempfile.mkdtemp()
    context.temp_dirs.append(tmp)
    context.key_map = {filename: prefix + filename}
    (Path(tmp) / (prefix + filename)).write_bytes(buf.getvalue())
    context.location = tmp


@given('a local directory with an unsupported file "{filename}"')
def step_unsupported_file(context, filename):
    prefix = f"test-{uuid.uuid4().hex[:8]}-"
    tmp = tempfile.mkdtemp()
    context.temp_dirs.append(tmp)
    context.key_map = {filename: prefix + filename}
    (Path(tmp) / (prefix + filename)).write_bytes(b"not a jpeg")
    context.location = tmp


@given('"{key}" is already in the database')
def step_key_in_db(context, key):
    db_key = context.key_map.get(key, key)
    with context.conn.cursor() as cur:
        cur.execute(
            "INSERT INTO photos (s3_key, processed_at) VALUES (%s, NOW()) ON CONFLICT DO NOTHING",
            (db_key,),
        )


@given('"{key}" is already in the database for bucket "{bucket}"')
def step_key_in_db_with_bucket(context, key, bucket):
    db_key = context.key_map.get(key, key)
    with context.conn.cursor() as cur:
        cur.execute(
            "INSERT INTO photos (s3_key, bucket, processed_at) VALUES (%s, %s, NOW()) ON CONFLICT DO NOTHING",
            (db_key, bucket),
        )


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------

@when("the processor attempts to process the image and fails")
def step_run_expecting_failure(context):
    import logging
    import processor

    log_handler = logging.handlers.MemoryHandler(capacity=1000, flushLevel=logging.CRITICAL)
    log_handler.buffer = []

    class CapturingHandler(logging.Handler):
        def emit(self, record):
            log_handler.buffer.append(self.format(record))

    capturing = CapturingHandler()
    processor_logger = logging.getLogger("processor")
    processor_logger.addHandler(capturing)
    try:
        filenames = [f for f in os.listdir(context.location) if not f.startswith(".")]
        assert len(filenames) == 1
        filename = filenames[0]
        image_bytes = (Path(context.location) / filename).read_bytes()
        try:
            processor.process_one(filename, image_bytes, context.conn, anthropic.Anthropic())
        except Exception as e:
            context.processing_error = e
        else:
            context.processing_error = None
    finally:
        processor_logger.removeHandler(capturing)

    context.captured_logs = log_handler.buffer


def _run_processor(context, bucket=None):
    import processor

    filenames = [f for f in os.listdir(context.location) if not f.startswith(".")]
    discovered = len(filenames)
    processed = skipped = 0
    kwargs = {"bucket": bucket} if bucket is not None else {}

    for filename in filenames:
        image_bytes = (Path(context.location) / filename).read_bytes()
        status = processor.process_one(filename, image_bytes, context.conn, anthropic.Anthropic(), **kwargs)
        if status in ("skipped", "unsupported"):
            skipped += 1
        else:
            processed += 1

    context.result = {"discovered": discovered, "processed": processed, "skipped": skipped}


@when("the processor runs")
def step_run(context):
    _run_processor(context)


@when('the processor runs for bucket "{bucket}"')
def step_run_with_bucket(context, bucket):
    _run_processor(context, bucket=bucket)


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------

@then("{count:d} photos should be discovered")
def step_discovered(context, count):
    assert context.result["discovered"] == count, (
        f"Expected {count} discovered, got {context.result['discovered']}"
    )


@then("{count:d} photo should be processed")
@then("{count:d} photos should be processed")
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


@then('"{key}" should be saved to the database with bucket "{bucket}"')
def step_photo_saved_with_bucket(context, key, bucket):
    db_key = context.key_map.get(key, key)
    with context.conn.cursor() as cur:
        cur.execute("SELECT id FROM photos WHERE s3_key = %s AND bucket = %s", (db_key, bucket))
        assert cur.fetchone(), f"{db_key!r} not found in photos table with bucket {bucket!r}"


@then('"{key}" should not be saved to the database')
def step_photo_not_saved(context, key):
    db_key = context.key_map.get(key, key)
    with context.conn.cursor() as cur:
        cur.execute("SELECT id FROM photos WHERE s3_key = %s", (db_key,))
        assert cur.fetchone() is None, f"{db_key!r} should not be in photos table but was found"


@then('the error log should include "{filename}"')
def step_log_includes_filename(context, filename):
    assert context.processing_error is not None, "Expected processing to fail but it succeeded"
    db_key = context.key_map.get(filename, filename)
    matching = [line for line in context.captured_logs if db_key in line]
    assert matching, (
        f"Expected log message containing {db_key!r} but got:\n"
        + "\n".join(context.captured_logs)
    )


@then('"{key}" should have captured_at "{expected_dt}" in the database')
def step_has_captured_at(context, key, expected_dt):
    from datetime import datetime
    db_key = context.key_map.get(key, key)
    with context.conn.cursor() as cur:
        cur.execute("SELECT captured_at FROM photos WHERE s3_key = %s", (db_key,))
        row = cur.fetchone()
    assert row, f"{db_key!r} not found in photos table"
    assert row[0] is not None, f"captured_at is NULL for {db_key!r}"
    expected = datetime.strptime(expected_dt, "%Y-%m-%d %H:%M:%S")
    actual = row[0].replace(tzinfo=None)
    assert actual == expected, f"Expected captured_at {expected}, got {actual}"


@given("the same photo bytes already exist in the photos bucket")
def step_same_bytes_in_photos_bucket(context):
    """Seed a photos bucket record with the same content_hash as the inbox photo."""
    import hashlib
    from pathlib import Path

    # Find the one file in the temp dir and compute its hash
    filenames = [f for f in os.listdir(context.location) if not f.startswith(".")]
    assert len(filenames) == 1, "Expected exactly one file in temp dir"
    image_bytes = (Path(context.location) / filenames[0]).read_bytes()
    content_hash = hashlib.sha256(image_bytes).hexdigest()

    with context.conn.cursor() as cur:
        cur.execute(
            "INSERT INTO photos (s3_key, bucket, content_hash, processed_at) VALUES (%s, %s, %s, NOW())",
            (filenames[0], "photo-tagging-photos", content_hash),
        )


@given("the same photo bytes already exist in the photos bucket under a different key")
def step_same_bytes_in_photos_bucket_different_key(context):
    """Seed a photos bucket record with the same content_hash but a different s3_key."""
    import hashlib
    from pathlib import Path

    filenames = [f for f in os.listdir(context.location) if not f.startswith(".")]
    assert len(filenames) == 1, "Expected exactly one file in temp dir"
    image_bytes = (Path(context.location) / filenames[0]).read_bytes()
    content_hash = hashlib.sha256(image_bytes).hexdigest()

    # Use a different s3_key to simulate a concurrent upload of the same content
    other_key = "existing_copy_" + filenames[0]
    with context.conn.cursor() as cur:
        cur.execute(
            "INSERT INTO photos (s3_key, bucket, content_hash, processed_at) VALUES (%s, %s, %s, NOW())",
            (other_key, "photo-tagging-photos", content_hash),
        )


@then('"{key}" should have a 64-character content_hash in the database')
def step_has_content_hash(context, key):
    db_key = context.key_map.get(key, key)
    with context.conn.cursor() as cur:
        cur.execute("SELECT content_hash FROM photos WHERE s3_key = %s", (db_key,))
        row = cur.fetchone()
    assert row, f"{db_key!r} not found in photos table"
    assert row[0] is not None, f"content_hash is NULL for {db_key!r}"
    assert len(row[0]) == 64, f"Expected 64-char hex hash, got {len(row[0])!r} chars: {row[0]!r}"


@then('"{key}" should have original_filename set in the database')
def step_has_original_filename(context, key):
    db_key = context.key_map.get(key, key)
    with context.conn.cursor() as cur:
        cur.execute("SELECT original_filename FROM photos WHERE s3_key = %s", (db_key,))
        row = cur.fetchone()
    assert row, f"{db_key!r} not found in photos table"
    assert row[0] is not None, f"original_filename is NULL for {db_key!r}"
    assert row[0] == db_key, f"Expected original_filename={db_key!r}, got {row[0]!r}"


@then('"{key}" should have captured_at NULL in the database')
def step_has_null_captured_at(context, key):
    db_key = context.key_map.get(key, key)
    with context.conn.cursor() as cur:
        cur.execute("SELECT captured_at FROM photos WHERE s3_key = %s", (db_key,))
        row = cur.fetchone()
    assert row, f"{db_key!r} not found in photos table"
    assert row[0] is None, f"Expected captured_at to be NULL for {db_key!r}, got {row[0]}"


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
