"""
Step definitions for thumbnailer_lambda.feature.

Requires in .env:
  - THUMBNAILER_LAMBDA_NAME  name of the deployed Lambda function
  - S3_BUCKET                bucket the Lambda reads from (photo-tagging-photos)
  - THUMBNAIL_BUCKET         bucket the Lambda writes to (photo-tagging-thumbnails)

Test photos are uploaded with a unique prefix to avoid collisions with real data.
Thumbnails and source photos created during tests are deleted in after_scenario
via environment.py.
"""

import hashlib
import io
import json
import os
import uuid
from pathlib import Path

import boto3
from behave import given, then, when
from PIL import Image

from common import thumbnail_key as _thumbnail_key
from infrastructure_steps import assert_eventbridge_rule_targets_lambda

IMAGES_DIR = Path(__file__).parents[2] / "images"


@given("the thumbnailer Lambda is deployed")
def step_thumbnailer_deployed(context):
    name = os.environ["THUMBNAILER_LAMBDA_NAME"]
    client = boto3.client("lambda")
    response = client.get_function(FunctionName=name)
    context.thumbnailer_lambda_name = name
    context.thumbnailer_lambda_state = response["Configuration"]["State"]


@given("a test photo is uploaded to the photos bucket")
def step_upload_test_photo_to_photos_bucket(context):
    bucket = os.environ["S3_BUCKET"]
    images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.jpeg"))
    assert images, f"No sample images found in {IMAGES_DIR}"

    prefix = f"testA6FA7E1D-{uuid.uuid4().hex[:8]}-"
    s3_key = prefix + images[0].name

    boto3.client("s3").upload_file(str(images[0]), bucket, s3_key)
    context.test_s3_key = s3_key
    context.test_s3_bucket = bucket
    context.test_thumbnail_key = _thumbnail_key(s3_key)
    context.test_thumbnail_bucket = os.environ["THUMBNAIL_BUCKET"]
    context.test_expected_source_hash = hashlib.sha256(images[0].read_bytes()).hexdigest()


@given("a thumbnail already exists for the photo")
def step_thumbnail_already_exists(context):
    # Upload a minimal valid WebP as a stand-in thumbnail.
    img = Image.new("RGB", (400, 400), color=(100, 100, 100))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    buf.seek(0)
    boto3.client("s3").put_object(
        Bucket=context.test_thumbnail_bucket,
        Key=context.test_thumbnail_key,
        Body=buf.read(),
        ContentType="image/webp",
    )


@when("the thumbnailer Lambda processes the photo")
def step_invoke_thumbnailer(context):
    client = boto3.client("lambda")
    payload = {"s3_key": context.test_s3_key}
    response = client.invoke(
        FunctionName=context.thumbnailer_lambda_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload),
    )
    result = json.loads(response["Payload"].read())
    assert response["StatusCode"] == 200, f"Lambda returned status {response['StatusCode']}"
    assert "FunctionError" not in response, f"Lambda error: {result}"
    context.thumbnailer_result = result


@then("the thumbnailer function should be active")
def step_thumbnailer_active(context):
    assert context.thumbnailer_lambda_state == "Active", (
        f"Expected Lambda state Active, got {context.thumbnailer_lambda_state!r}"
    )


@then("an EventBridge rule should trigger the thumbnailer Lambda on S3 uploads to the photos bucket")
def step_thumbnailer_eventbridge_rule(context):
    assert_eventbridge_rule_targets_lambda(context.thumbnailer_lambda_name, os.environ["S3_BUCKET"])


@then("a thumbnail should exist in the thumbnail bucket")
def step_thumbnail_exists(context):
    s3 = boto3.client("s3")
    try:
        s3.head_object(Bucket=context.test_thumbnail_bucket, Key=context.test_thumbnail_key)
    except s3.exceptions.ClientError:
        raise AssertionError(
            f"Thumbnail {context.test_thumbnail_key!r} not found in {context.test_thumbnail_bucket!r}"
        )


@then("the thumbnail should be a 400x400 WebP")
def step_thumbnail_dimensions(context):
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=context.test_thumbnail_bucket, Key=context.test_thumbnail_key)
    img = Image.open(io.BytesIO(obj["Body"].read()))
    assert img.format == "WEBP", f"Expected WebP, got {img.format}"
    assert img.size == (400, 400), f"Expected 400x400, got {img.size}"


@then('the Lambda should return status "{expected_status}"')
def step_lambda_status(context, expected_status):
    actual = context.thumbnailer_result.get("status")
    assert actual == expected_status, f"Expected status {expected_status!r}, got {actual!r}"


@then("the thumbnail should have source-hash metadata matching the photo's SHA-256")
def step_thumbnail_has_matching_source_hash(context):
    s3 = boto3.client("s3")
    response = s3.head_object(Bucket=context.test_thumbnail_bucket, Key=context.test_thumbnail_key)
    metadata = response.get("Metadata", {})
    assert "source-hash" in metadata, (
        f"Expected 'source-hash' in thumbnail metadata, got: {metadata}"
    )
    assert metadata["source-hash"] == context.test_expected_source_hash, (
        f"Expected source-hash {context.test_expected_source_hash!r}, "
        f"got {metadata['source-hash']!r}"
    )


@given("a photos row exists in Neon for the test photo")
def step_seed_photos_row_for_thumbnailer_test(context):
    import psycopg2
    conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO photos (s3_key, bucket, content_hash) VALUES (%s, %s, %s)"
                " ON CONFLICT (content_hash) DO UPDATE SET s3_key = EXCLUDED.s3_key, bucket = EXCLUDED.bucket",
                (context.test_s3_key, context.test_s3_bucket, context.test_expected_source_hash),
            )
        conn.commit()
    finally:
        conn.close()
    if not hasattr(context, "neon_test_s3_keys"):
        context.neon_test_s3_keys = []
    context.neon_test_s3_keys.append(context.test_s3_key)


@then("the photos row thumbnailed_at should be populated")
def step_photos_row_thumbnailed_at(context):
    import psycopg2
    conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT thumbnailed_at FROM photos WHERE content_hash = %s",
                (context.test_expected_source_hash,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    assert row is not None, f"No photos row for content_hash={context.test_expected_source_hash!r}"
    assert row[0] is not None, "Expected thumbnailed_at to be populated, got NULL"
