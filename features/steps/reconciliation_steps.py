"""
Step definitions for reconciliation.feature (Slice 7b).

Requires in .env:
  - NEON_DATABASE_URL
  - S3_BUCKET (photos bucket)
"""

import os
import subprocess
import uuid
from pathlib import Path

import boto3
from behave import given, then, when

from common import neon_conn

PROJECT_ROOT = Path(__file__).parents[2]


def _make_decoy_bytes() -> bytes:
    """Return bytes that pass the reconciler's suffix-based image filter but
    fail PIL decoding inside processor v2, so EventBridge → process_one returns
    'unsupported' without writing a photos row. This keeps the orphan_s3_only
    fixture race-free.
    """
    return f"not-a-real-jpeg-{uuid.uuid4().hex}".encode()


def _run_reconciler():
    """Invoke the reconciler script as a subprocess. Asserts exit 0."""
    result = subprocess.run(
        ["python", str(PROJECT_ROOT / "scripts" / "reconcile_pipeline.py")],
        capture_output=True,
        text=True,
        env={**os.environ},
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, (
        f"Reconciler exited {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


@given("a unique JPEG exists in the photos bucket with no corresponding photos row")
def step_stray_s3_object(context):
    bucket = os.environ["S3_BUCKET"]
    s3_key = f"testA6FA7E1D-recon-{uuid.uuid4().hex[:12]}.jpg"
    # Use decoy bytes so processor v2 returns "unsupported" without INSERTing
    # a row — keeps the orphan_s3_only condition stable while EventBridge fires.
    boto3.client("s3").put_object(Bucket=bucket, Key=s3_key, Body=_make_decoy_bytes(), ContentType="image/jpeg")

    if not hasattr(context, "searcher_s3_uploads"):
        context.searcher_s3_uploads = []
    context.searcher_s3_uploads.append((bucket, s3_key))
    if not hasattr(context, "neon_test_s3_keys"):
        context.neon_test_s3_keys = []
    context.neon_test_s3_keys.append(s3_key)

    context.recon_s3_key = s3_key
    context.recon_bucket = bucket


@given("a unique photos row exists in Neon with no corresponding S3 object")
def step_stray_db_row(context):
    bucket = os.environ["S3_BUCKET"]
    s3_key = f"testA6FA7E1D-recon-{uuid.uuid4().hex[:12]}.jpg"
    content_hash = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char fake hash

    conn = neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO photos (s3_key, bucket, content_hash) VALUES (%s, %s, %s)",
                (s3_key, bucket, content_hash),
            )
        conn.commit()
    finally:
        conn.close()

    if not hasattr(context, "neon_test_s3_keys"):
        context.neon_test_s3_keys = []
    context.neon_test_s3_keys.append(s3_key)

    context.recon_s3_key = s3_key
    context.recon_bucket = bucket


@given("the reconciler has already run once")
def step_reconciler_already_ran(context):
    _run_reconciler()


@when("the reconciler runs")
def step_run_reconciler(context):
    _run_reconciler()


@when("the reconciler runs again")
def step_run_reconciler_again(context):
    _run_reconciler()


def _count_orphan_events(s3_key: str, event_type: str) -> int:
    conn = neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*), MIN(actor) FROM photo_events"
                " WHERE s3_key = %s AND event_type = %s",
                (s3_key, event_type),
            )
            count, actor = cur.fetchone()
            return count, actor
    finally:
        conn.close()


@then('a photo_events row with event_type "{event_type}" should exist for the stray s3_key')
def step_orphan_event_exists(context, event_type):
    count, actor = _count_orphan_events(context.recon_s3_key, event_type)
    assert count >= 1, f"Expected ≥1 {event_type!r} event for {context.recon_s3_key!r}, got {count}"
    context.last_orphan_actor = actor


@then('the orphan event actor should be "{actor}"')
def step_orphan_event_actor(context, actor):
    assert context.last_orphan_actor == actor, (
        f"Expected actor {actor!r}, got {context.last_orphan_actor!r}"
    )


@then('exactly one "{event_type}" photo_events row should exist for the stray s3_key')
def step_exactly_one_orphan_event(context, event_type):
    count, _ = _count_orphan_events(context.recon_s3_key, event_type)
    assert count == 1, f"Expected exactly 1 {event_type!r} event for {context.recon_s3_key!r}, got {count}"
