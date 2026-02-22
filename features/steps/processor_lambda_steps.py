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
import psycopg2
from behave import given, then, when

IMAGES_DIR = Path(__file__).parents[2] / "images"


def _neon_conn():
    return psycopg2.connect(os.environ["NEON_DATABASE_URL"])


@given("the processor Lambda is deployed")
def step_processor_lambda_deployed(context):
    name = os.environ["PROCESSOR_LAMBDA_NAME"]
    client = boto3.client("lambda")
    response = client.get_function(FunctionName=name)
    context.lambda_name = name
    context.lambda_state = response["Configuration"]["State"]


@given("a test photo is uploaded to S3")
def step_upload_test_photo(context):
    bucket = os.environ["S3_BUCKET"]
    # Use the first image available in images/ as the test fixture.
    images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.jpeg"))
    assert images, f"No sample images found in {IMAGES_DIR}"

    prefix = f"test-{uuid.uuid4().hex[:8]}-"
    s3_key = prefix + images[0].name

    boto3.client("s3").upload_file(str(images[0]), bucket, s3_key)
    context.test_s3_key = s3_key
    context.test_s3_bucket = bucket


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


@then("the photo should be stored in the Neon database")
def step_photo_in_db(context):
    conn = _neon_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM photos WHERE s3_key = %s", (context.test_s3_key,))
            row = cur.fetchone()
        assert row, f"Photo {context.test_s3_key!r} not found in photos table"
        context.neon_photo_id = row[0]
    finally:
        conn.close()


@then("the photo should have tags in the Neon database")
def step_photo_has_tags(context):
    conn = _neon_conn()
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


