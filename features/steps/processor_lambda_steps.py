"""
Step definitions for processor_lambda.feature.

Requires in .env:
  - PROCESSOR_LAMBDA_NAME  name of the deployed Lambda function
  - S3_BUCKET              bucket the Lambda reads from
  - NEON_DATABASE_URL      for verifying results and cleaning up

Test images are uploaded to S3 with a unique prefix so they never collide
with real data. DB records created by the Lambda are deleted after each
scenario via a direct Neon connection.
"""

import json
import os
import uuid
from pathlib import Path

import boto3
from behave import given, then, when

from common import neon_conn, thumbnail_key
from infrastructure_steps import assert_eventbridge_rule_targets_lambda

IMAGES_DIR = Path(__file__).parents[2] / "images"


@given("the processor Lambda is deployed")
def step_processor_lambda_deployed(context):
    name = os.environ["PROCESSOR_LAMBDA_NAME"]
    client = boto3.client("lambda")
    response = client.get_function(FunctionName=name)
    context.lambda_name = name
    context.lambda_state = response["Configuration"]["State"]


@given("a test photo is uploaded to S3")
def step_upload_test_photo(context):
    import hashlib
    bucket = os.environ["S3_BUCKET"]
    # Use the first image available in images/ as the test fixture.
    images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.jpeg"))
    assert images, f"No sample images found in {IMAGES_DIR}"
    image_bytes = images[0].read_bytes()
    content_hash = hashlib.sha256(image_bytes).hexdigest()

    # Pre-clean any stale Neon records with this content_hash left by delayed
    # EventBridge Lambda invocations from a prior test run whose after_scenario
    # cleanup committed before the EventBridge Lambda finished inserting.
    try:
        conn = neon_conn()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM photos WHERE content_hash = %s AND bucket = %s AND s3_key LIKE 'test-%%'",
                (content_hash, bucket),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass

    prefix = f"test-{uuid.uuid4().hex[:8]}-"
    s3_key = prefix + images[0].name

    boto3.client("s3").upload_file(str(images[0]), bucket, s3_key)
    context.test_s3_key = s3_key
    context.test_s3_bucket = bucket
    context.test_thumbnail_key = thumbnail_key(s3_key)
    context.test_thumbnail_bucket = os.environ["THUMBNAIL_BUCKET"]
    context.test_content_hash = content_hash  


@when("the Lambda is invoked with a key that does not exist in S3")
def step_invoke_lambda_missing_key(context):
    client = boto3.client("lambda")
    payload = {
        "Records": [{
            "s3": {
                "bucket": {"name": os.environ["S3_BUCKET"]},
                "object": {"key": f"test-{uuid.uuid4().hex[:8]}-nonexistent.jpg"},
            }
        }]
    }
    response = client.invoke(
        FunctionName=context.lambda_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload),
    )
    context.lambda_response = response
    context.lambda_result = json.loads(response["Payload"].read())


@then("the Lambda should return without a function error")
def step_lambda_no_function_error(context):
    assert "FunctionError" not in context.lambda_response, (
        f"Lambda crashed with: {context.lambda_result}"
    )


@when("the Lambda processes the photo")
def step_invoke_lambda(context):
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
        FunctionName=context.lambda_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload),
    )
    result = json.loads(response["Payload"].read())
    assert response["StatusCode"] == 200, f"Lambda returned status {response['StatusCode']}"
    assert "FunctionError" not in response, f"Lambda error: {result}"
    context.lambda_result = result


@then("the function should be active")
def step_function_active(context):
    assert context.lambda_state == "Active", (
        f"Expected Lambda state Active, got {context.lambda_state!r}"
    )


@then("an EventBridge rule should trigger the processor Lambda on S3 uploads to the photos bucket")
def step_processor_eventbridge_rule(context):
    assert_eventbridge_rule_targets_lambda(context.lambda_name, os.environ["S3_BUCKET"])


@then("the photo should be stored in the Neon database")
def step_photo_in_db(context):
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


@then("the photo should have tags in the Neon database")
def step_photo_has_tags(context):
    conn = neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM photo_tags WHERE photo_id = %s
                """,
                (context.neon_photo_id,),
            )
            count = cur.fetchone()[0]
        assert count > 0, f"No tags found for photo {context.test_s3_key!r}"
    finally:
        conn.close()


