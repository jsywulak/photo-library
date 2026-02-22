"""
Step definitions for searcher_lambda.feature.

Requires in .env:
  - SEARCHER_LAMBDA_NAME  name of the deployed Lambda function
  - NEON_DATABASE_URL     for seeding test data and verifying results

Test photos are inserted into Neon with a unique prefix. The environment.py
after_scenario hook cleans them up via context.neon_test_s3_keys.
"""

import json
import os
import uuid

import boto3
import psycopg2
import urllib.request
from behave import given, then, when


def _neon_conn():
    return psycopg2.connect(os.environ["NEON_DATABASE_URL"])


def _seed_photo(conn, s3_key, tags):
    """Insert a photo and its tags into Neon. Returns the photo id."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO photos (s3_key, processed_at) VALUES (%s, NOW()) RETURNING id",
            (s3_key,),
        )
        photo_id = cur.fetchone()[0]
        for tag_name in tags:
            cur.execute(
                """
                INSERT INTO tags (name) VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (tag_name.strip().lower(),),
            )
            tag_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO photo_tags (photo_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (photo_id, tag_id),
            )
    conn.commit()
    return photo_id


@given("the searcher Lambda is deployed")
def step_searcher_lambda_deployed(context):
    name = os.environ["SEARCHER_LAMBDA_NAME"]
    client = boto3.client("lambda")
    response = client.get_function(FunctionName=name)
    context.searcher_lambda_name = name
    context.searcher_lambda_state = response["Configuration"]["State"]


@given('a photo exists in the Neon database tagged with "{tags}"')
def step_seed_photo(context, tags):
    if not hasattr(context, "neon_test_s3_keys"):
        context.neon_test_s3_keys = []

    prefix = f"test-{uuid.uuid4().hex[:8]}-"
    s3_key = f"{prefix}photo.jpg"
    tag_list = [t.strip() for t in tags.split(",")]

    conn = _neon_conn()
    _seed_photo(conn, s3_key, tag_list)
    conn.close()

    context.neon_test_s3_keys.append(s3_key)
    # Track the "best" photo as the first seeded (most tags relative to search)
    if not hasattr(context, "best_photo_key"):
        context.best_photo_key = s3_key
    context.last_photo_key = s3_key


@when('the Lambda is invoked with tags "{tags}"')
def step_invoke_searcher(context, tags):
    tag_list = [t.strip() for t in tags.split(",")]
    client = boto3.client("lambda")
    response = client.invoke(
        FunctionName=context.searcher_lambda_name,
        InvocationType="RequestResponse",
        Payload=json.dumps({"tags": tag_list}),
    )
    assert response["StatusCode"] == 200, f"Lambda returned status {response['StatusCode']}"
    assert "FunctionError" not in response, (
        f"Lambda error: {json.loads(response['Payload'].read())}"
    )
    context.search_results = json.loads(response["Payload"].read())


@then("the searcher function should be active")
def step_searcher_active(context):
    assert context.searcher_lambda_state == "Active", (
        f"Expected Lambda state Active, got {context.searcher_lambda_state!r}"
    )


@then("the results should contain both photos")
def step_results_contain_both(context):
    result_keys = {r["s3_key"] for r in context.search_results}
    for key in context.neon_test_s3_keys:
        assert key in result_keys, f"Expected {key!r} in results, got: {result_keys}"


@then("the photo with more matching tags should rank higher")
def step_ranking(context):
    result_keys = [r["s3_key"] for r in context.search_results]
    best_idx = result_keys.index(context.best_photo_key)
    last_idx = result_keys.index(context.last_photo_key)
    assert best_idx < last_idx, (
        f"Expected {context.best_photo_key!r} to rank above {context.last_photo_key!r}"
    )


@when('the Function URL is called with tags "{tags}" and the correct API key')
def step_function_url_correct_key(context, tags):
    tag_list = [t.strip() for t in tags.split(",")]
    url = os.environ["SEARCHER_URL"]
    api_key = os.environ["API_KEY"]
    body = json.dumps({"tags": tag_list}).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"content-type": "application/json", "x-api-key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        context.http_status = resp.status
        context.http_body = json.loads(resp.read())


@when('the Function URL is called with tags "{tags}" and an incorrect API key')
def step_function_url_wrong_key(context, tags):
    tag_list = [t.strip() for t in tags.split(",")]
    url = os.environ["SEARCHER_URL"]
    body = json.dumps({"tags": tag_list}).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"content-type": "application/json", "x-api-key": "wrong-key"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            context.http_status = resp.status
    except urllib.error.HTTPError as e:
        context.http_status = e.code


@then("the HTTP response status should be {status:d}")
def step_http_status(context, status):
    assert context.http_status == status, (
        f"Expected HTTP {status}, got {context.http_status}"
    )


@then("the response body should contain the photo")
def step_response_contains_photo(context):
    result_keys = {r["s3_key"] for r in context.http_body}
    assert context.last_photo_key in result_keys, (
        f"Expected {context.last_photo_key!r} in response, got: {result_keys}"
    )


@given('a photo is uploaded to S3 and tagged in the database with "{tags}"')
def step_upload_to_s3_and_seed(context, tags):
    if not hasattr(context, "neon_test_s3_keys"):
        context.neon_test_s3_keys = []
    if not hasattr(context, "searcher_s3_uploads"):
        context.searcher_s3_uploads = []

    prefix = f"test-{uuid.uuid4().hex[:8]}-"
    s3_key = f"{prefix}photo.jpg"
    bucket = os.environ["S3_BUCKET"]

    # Minimal valid JPEG bytes (1x1 pixel)
    minimal_jpeg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
        b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
        b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x87"
        b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
        b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00"
        b"\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
        b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd2\x8a(\x03\xff\xd9"
    )

    boto3.client("s3").put_object(
        Bucket=bucket, Key=s3_key, Body=minimal_jpeg, ContentType="image/jpeg"
    )
    context.searcher_s3_uploads.append((bucket, s3_key))

    tag_list = [t.strip() for t in tags.split(",")]
    conn = _neon_conn()
    _seed_photo(conn, s3_key, tag_list)
    conn.close()

    context.neon_test_s3_keys.append(s3_key)
    context.last_photo_key = s3_key


@then("each result should include a presigned URL")
def step_results_have_url(context):
    assert context.search_results, "Expected at least one result"
    for result in context.search_results:
        assert "url" in result, f"Result missing 'url' field: {result}"
        assert result["url"].startswith("https://"), (
            f"Expected HTTPS URL, got: {result['url']!r}"
        )


@then("the presigned URL for the photo should return HTTP 200")
def step_presigned_url_accessible(context):
    result = next(
        (r for r in context.http_body if r["s3_key"] == context.last_photo_key), None
    )
    assert result is not None, f"Photo {context.last_photo_key!r} not found in results"
    assert "url" in result, f"Result missing 'url' field: {result}"

    req = urllib.request.Request(result["url"], method="GET")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200, f"Expected 200 from presigned URL, got {resp.status}"
