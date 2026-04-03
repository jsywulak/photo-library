"""
Step definitions for image_lambda.feature.

Requires in .env:
  - IMAGE_LAMBDA_NAME   name of the deployed image handler Lambda function
  - UPLOAD_BUCKET       S3 staging bucket where photos are uploaded
  - INBOX_BUCKET        S3 inbox bucket (where handler copies photos)
  - THUMBNAIL_BUCKET    S3 thumbnail bucket

Test photos are uploaded with the standard testA6FA7E1D- prefix.
After each scenario, environment.py cleans up test_upload_s3_key,
test_s3_key (inbox result), and test_thumbnail_key.
"""

import hashlib
import json
import os
import uuid
from pathlib import Path

import boto3
from behave import given, then, when

from infrastructure_steps import assert_eventbridge_rule_targets_lambda

IMAGES_DIR = Path(__file__).parents[2] / "images"


@given("the image handler Lambda is deployed")
def step_image_handler_deployed(context):
    name = os.environ["IMAGE_LAMBDA_NAME"]
    client = boto3.client("lambda")
    response = client.get_function(FunctionName=name)
    context.image_lambda_name = name
    context.image_lambda_state = response["Configuration"]["State"]


@given("a test photo is uploaded to the upload bucket")
def step_upload_test_photo_to_upload_bucket(context):
    upload_bucket = os.environ["UPLOAD_BUCKET"]
    images = list(IMAGES_DIR.glob("*.jpg")) + list(IMAGES_DIR.glob("*.jpeg"))
    assert images, f"No sample images found in {IMAGES_DIR}"

    image_bytes = images[0].read_bytes()
    content_hash = hashlib.sha256(image_bytes).hexdigest()

    prefix = f"testA6FA7E1D-{uuid.uuid4().hex[:8]}-"
    s3_key = prefix + images[0].name

    boto3.client("s3").put_object(
        Bucket=upload_bucket,
        Key=s3_key,
        Body=image_bytes,
        ContentType="image/jpeg",
    )

    context.test_upload_s3_key = s3_key
    context.test_upload_bucket = upload_bucket
    context.test_expected_content_hash = content_hash
    context.test_expected_source_hash = content_hash
    # After the handler runs, the inbox key and thumbnail key are hash-based
    context.test_s3_key = f"{content_hash}.jpg"
    context.test_s3_bucket = os.environ["INBOX_BUCKET"]
    context.test_thumbnail_key = f"thumbnails/{content_hash}.webp"
    context.test_thumbnail_bucket = os.environ["THUMBNAIL_BUCKET"]


@when("the image handler Lambda processes the photo")
def step_invoke_image_handler(context):
    client = boto3.client("lambda")
    payload = {
        "s3_key": context.test_upload_s3_key,
        "source_bucket": context.test_upload_bucket,
    }
    response = client.invoke(
        FunctionName=context.image_lambda_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload),
    )
    result = json.loads(response["Payload"].read())
    assert response["StatusCode"] == 200, f"Lambda returned status {response['StatusCode']}"
    assert "FunctionError" not in response, f"Lambda error: {result}"
    context.image_handler_result = result


@then("the image handler function should be active")
def step_image_handler_active(context):
    assert context.image_lambda_state == "Active", (
        f"Expected Lambda state Active, got {context.image_lambda_state!r}"
    )


@then("an EventBridge rule should trigger the image handler Lambda on S3 uploads to the upload bucket")
def step_image_handler_eventbridge_rule(context):
    assert_eventbridge_rule_targets_lambda(context.image_lambda_name, os.environ["UPLOAD_BUCKET"])


@then("the photo should appear in the inbox bucket with a hash-based key")
def step_photo_in_inbox_with_hash_key(context):
    s3 = boto3.client("s3")
    try:
        s3.head_object(Bucket=context.test_s3_bucket, Key=context.test_s3_key)
    except Exception:
        raise AssertionError(
            f"Expected inbox key {context.test_s3_key!r} not found in {context.test_s3_bucket!r}"
        )


@then("a thumbnail should exist in the thumbnail bucket with the hash-based key")
def step_thumbnail_exists_with_hash_key(context):
    s3 = boto3.client("s3")
    try:
        s3.head_object(Bucket=context.test_thumbnail_bucket, Key=context.test_thumbnail_key)
    except Exception:
        raise AssertionError(
            f"Expected thumbnail {context.test_thumbnail_key!r} not found in "
            f"{context.test_thumbnail_bucket!r}"
        )


@then("the original photo should no longer exist in the upload bucket")
def step_original_deleted_from_upload_bucket(context):
    s3 = boto3.client("s3")
    try:
        s3.head_object(Bucket=context.test_upload_bucket, Key=context.test_upload_s3_key)
        raise AssertionError(
            f"Expected {context.test_upload_s3_key!r} to be deleted from "
            f"{context.test_upload_bucket!r}, but it still exists"
        )
    except s3.exceptions.ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey"):
            return
        raise


@then("the Lambda should return the expected content_hash")
def step_result_has_expected_content_hash(context):
    returned = context.image_handler_result.get("content_hash")
    expected = context.test_expected_content_hash
    assert returned == expected, (
        f"Expected content_hash {expected!r}, got {returned!r}"
    )


@then("the inbox object should have original-filename metadata matching the upload key")
def step_inbox_object_has_original_filename_metadata(context):
    s3 = boto3.client("s3")
    response = s3.head_object(Bucket=context.test_s3_bucket, Key=context.test_s3_key)
    metadata = response.get("Metadata", {})
    assert "original-filename" in metadata, (
        f"Expected 'original-filename' in inbox object metadata, got: {metadata}"
    )
    expected = Path(context.test_upload_s3_key).name
    assert metadata["original-filename"] == expected, (
        f"Expected original-filename {expected!r}, got {metadata['original-filename']!r}"
    )


@then("the inbox thumbnail should have source-hash metadata matching the photo's SHA-256")
def step_image_handler_thumbnail_has_source_hash(context):
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
