"""
Step definitions for processor_v2_lambda.feature.

Requires in .env:
  - PROCESSOR_V2_LAMBDA_NAME  name of the deployed v2 Lambda function
  - S3_BUCKET                 bucket the Lambda reads from
  - NEON_DATABASE_URL         for verifying results and cleaning up

Steps are suffixed with "v2" to avoid conflicts with the duplicate steps in
processor_lambda_steps.py while both lambdas coexist.
"""

import json
import os
import struct
import uuid
from pathlib import Path

import boto3
from behave import given, then, when

from common import neon_conn, thumbnail_key
from infrastructure_steps import assert_eventbridge_rule_targets_lambda

IMAGES_DIR = Path(__file__).parents[2] / "images"


def _make_unique_jpeg(image_bytes: bytes) -> bytes:
    """Insert a JPEG comment block containing a UUID before the EOI marker."""
    assert image_bytes[-2:] == b"\xff\xd9", "Not a valid JPEG (missing EOI marker)"
    uid = uuid.uuid4().bytes
    comment_data = b"test-run-" + uid
    length = len(comment_data) + 2
    com_block = b"\xff\xfe" + struct.pack(">H", length) + comment_data
    return image_bytes[:-2] + com_block + b"\xff\xd9"


@given("the processor v2 Lambda is deployed")
def step_processor_v2_lambda_deployed(context):
    name = os.environ["PROCESSOR_V2_LAMBDA_NAME"]
    client = boto3.client("lambda")
    response = client.get_function(FunctionName=name)
    context.v2_lambda_name = name
    context.v2_lambda_state = response["Configuration"]["State"]


@then("the processor v2 function should be active")
def step_processor_v2_function_active(context):
    assert context.v2_lambda_state == "Active", (
        f"Expected Lambda state Active, got {context.v2_lambda_state!r}"
    )


@then("an EventBridge rule should trigger the processor v2 Lambda on S3 uploads to the photos bucket")
def step_processor_v2_eventbridge_rule(context):
    assert_eventbridge_rule_targets_lambda(context.v2_lambda_name, os.environ["S3_BUCKET"])


@when("the v2 Lambda is invoked with a key that does not exist in S3")
def step_invoke_v2_lambda_missing_key(context):
    client = boto3.client("lambda")
    payload = {
        "Records": [{
            "s3": {
                "bucket": {"name": os.environ["S3_BUCKET"]},
                "object": {"key": f"testA6FA7E1D-{uuid.uuid4().hex[:8]}-nonexistent.jpg"},
            }
        }]
    }
    response = client.invoke(
        FunctionName=context.v2_lambda_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload),
    )
    context.v2_lambda_response = response
    context.v2_lambda_result = json.loads(response["Payload"].read())


@then("the v2 Lambda should return without a function error")
def step_v2_lambda_no_function_error(context):
    assert "FunctionError" not in context.v2_lambda_response, (
        f"Lambda crashed with: {context.v2_lambda_result}"
    )


@given("a test photo is uploaded to S3 v2")
def step_upload_test_photo_v2(context):
    import hashlib
    bucket = os.environ["S3_BUCKET"]
    images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.jpeg"))
    assert images, f"No sample images found in {IMAGES_DIR}"
    image_bytes = _make_unique_jpeg(images[0].read_bytes())
    content_hash = hashlib.sha256(image_bytes).hexdigest()

    # Pre-clean any stale Neon records with this content_hash left by delayed
    # Lambda invocations from a prior test run.
    try:
        conn = neon_conn()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM photos WHERE content_hash = %s AND bucket = %s AND s3_key LIKE 'testA6FA7E1D-%%'",
                (content_hash, bucket),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass

    prefix = f"testA6FA7E1D-{uuid.uuid4().hex[:8]}-"
    s3_key = prefix + images[0].name

    boto3.client("s3").put_object(Bucket=bucket, Key=s3_key, Body=image_bytes, ContentType="image/jpeg")
    context.test_s3_key = s3_key
    context.test_s3_bucket = bucket
    context.test_thumbnail_key = thumbnail_key(s3_key)
    context.test_thumbnail_bucket = os.environ["THUMBNAIL_BUCKET"]
    context.test_content_hash = content_hash


@when("the v2 Lambda processes the photo")
def step_invoke_v2_lambda(context):
    client = boto3.client("lambda")
    payload = {
        "Records": [{
            "s3": {
                "bucket": {"name": context.test_s3_bucket},
                "object": {"key": context.test_s3_key},
            }
        }]
    }
    response = client.invoke(
        FunctionName=context.v2_lambda_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload),
    )
    result = json.loads(response["Payload"].read())
    assert response["StatusCode"] == 200, f"Lambda returned status {response['StatusCode']}"
    assert "FunctionError" not in response, f"Lambda error: {result}"
    context.v2_lambda_result = result


@then("the v2 photo should be stored in the Neon database")
def step_v2_photo_in_db(context):
    conn = neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM photos WHERE s3_key = %s AND bucket = %s",
                (context.test_s3_key, context.test_s3_bucket),
            )
            row = cur.fetchone()
        assert row, f"Photo {context.test_s3_key!r} not found in photos table"
        context.neon_photo_id = row[0]
    finally:
        conn.close()


@then("the v2 photo should have tags in the Neon database")
def step_v2_photo_has_tags(context):
    conn = neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM photo_tags WHERE photo_id = %s",
                (context.neon_photo_id,),
            )
            count = cur.fetchone()[0]
        assert count > 0, f"No tags found for photo {context.test_s3_key!r}"
    finally:
        conn.close()
