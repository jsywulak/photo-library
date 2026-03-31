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
import urllib.request
from behave import given, then, when

from common import neon_conn, seed_photo


def _api_get(path, api_key=None):
    url = os.environ["SEARCHER_URL"].rstrip("/") + path
    key = api_key if api_key is not None else os.environ["API_KEY"]
    req = urllib.request.Request(url, headers={"x-api-key": key}, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read()), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, None, dict(e.headers)


def _api_post(path, body_dict, api_key=None):
    url = os.environ["SEARCHER_URL"].rstrip("/") + path
    key = api_key if api_key is not None else os.environ["API_KEY"]
    body = json.dumps(body_dict).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"content-type": "application/json", "x-api-key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, None


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

    conn = neon_conn()
    seed_photo(conn, s3_key, tag_list)
    conn.commit()
    conn.close()

    context.neon_test_s3_keys.append(s3_key)
    # Track the "best" photo as the first seeded (most tags relative to search)
    if not hasattr(context, "best_photo_key"):
        context.best_photo_key = s3_key
    context.last_photo_key = s3_key


@given('{n:d} photos exist in the Neon database tagged with "{tags}"')
def step_seed_n_photos(context, n, tags):
    if not hasattr(context, "neon_test_s3_keys"):
        context.neon_test_s3_keys = []
    tag_list = [t.strip() for t in tags.split(",")]
    conn = neon_conn()
    for _ in range(n):
        s3_key = f"test-{uuid.uuid4().hex[:8]}-photo.jpg"
        seed_photo(conn, s3_key, tag_list)
        context.neon_test_s3_keys.append(s3_key)
    conn.commit()
    conn.close()


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


@when('the Lambda is invoked with tags "{tags}" and a limit of {limit:d}')
def step_invoke_searcher_with_limit(context, tags, limit):
    tag_list = [t.strip() for t in tags.split(",")]
    client = boto3.client("lambda")
    response = client.invoke(
        FunctionName=context.searcher_lambda_name,
        InvocationType="RequestResponse",
        Payload=json.dumps({"tags": tag_list, "limit": limit}),
    )
    assert response["StatusCode"] == 200, f"Lambda returned status {response['StatusCode']}"
    assert "FunctionError" not in response, (
        f"Lambda error: {json.loads(response['Payload'].read())}"
    )
    context.search_results = json.loads(response["Payload"].read())


@then("the results should contain exactly {n:d} photos")
def step_results_exactly_n(context, n):
    count = len(context.search_results)
    assert count == n, f"Expected exactly {n} results, got {count}"


@then("the Access-Control-Allow-Origin header should not be a wildcard")
def step_cors_not_wildcard(context):
    origin = context.response_headers.get("access-control-allow-origin")
    assert origin, "Expected Access-Control-Allow-Origin header to be present"
    assert origin != "*", (
        f"Expected CORS origin to be restricted to the frontend domain, got wildcard '*'"
    )


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


@when("the Function URL GET /tags is called with the correct API key")
def step_get_tags_correct_key(context):
    context.http_status, context.http_body, context.response_headers = _api_get("/tags")


@when("the Function URL GET /tags is called with an incorrect API key")
def step_get_tags_wrong_key(context):
    context.http_status, _, _ = _api_get("/tags", api_key="wrong-key")


@then("the response body should be a list of strings")
def step_response_is_list_of_strings(context):
    assert isinstance(context.http_body, list), (
        f"Expected a list, got: {type(context.http_body)}"
    )
    assert all(isinstance(t, str) for t in context.http_body), (
        f"Expected all items to be strings, got: {context.http_body}"
    )


@then("the response should contain at most 20 tags")
def step_response_at_most_20(context):
    assert len(context.http_body) <= 20, (
        f"Expected at most 20 tags, got {len(context.http_body)}"
    )


@when('the Function URL is called with tags "{tags}" and the correct API key')
def step_function_url_correct_key(context, tags):
    tag_list = [t.strip() for t in tags.split(",")]
    context.http_status, context.http_body = _api_post("/", {"tags": tag_list})


@when("the Function URL is called with a string tags payload and the correct API key")
def step_function_url_string_tags(context):
    context.http_status, _ = _api_post("/", {"tags": "cat"})  # string instead of list


@when('the Function URL is called with tags "{tags}" and an incorrect API key')
def step_function_url_wrong_key(context, tags):
    tag_list = [t.strip() for t in tags.split(",")]
    context.http_status, _ = _api_post("/", {"tags": tag_list}, api_key="wrong-key")


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
    boto3.client("s3").put_object(
        Bucket=bucket, Key=s3_key, Body=_MINIMAL_JPEG, ContentType="image/jpeg"
    )
    context.searcher_s3_uploads.append((bucket, s3_key))

    tag_list = [t.strip() for t in tags.split(",")]
    conn = neon_conn()
    seed_photo(conn, s3_key, tag_list)
    conn.commit()
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


@given("a thumbnail exists in the thumbnail bucket for that photo")
def step_thumbnail_exists_for_searcher_photo(context):
    import io
    from pathlib import Path
    from PIL import Image

    s3_key = context.last_photo_key
    thumbnail_bucket = os.environ["THUMBNAIL_BUCKET"]
    thumb_key = f"thumbnails/{Path(s3_key).stem}.webp"

    img = Image.new("RGB", (400, 400), color=(100, 100, 100))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    buf.seek(0)
    boto3.client("s3").put_object(
        Bucket=thumbnail_bucket,
        Key=thumb_key,
        Body=buf.read(),
        ContentType="image/webp",
    )

    # Register for cleanup via environment.py
    context.test_thumbnail_key = thumb_key
    context.test_thumbnail_bucket = thumbnail_bucket


@then("each result should include a thumbnail_url")
def step_results_have_thumbnail_url(context):
    assert context.search_results, "Expected at least one result"
    for result in context.search_results:
        assert "thumbnail_url" in result, f"Result missing 'thumbnail_url' field: {result}"
        assert result["thumbnail_url"].startswith("https://"), (
            f"Expected HTTPS URL, got: {result['thumbnail_url']!r}"
        )


_MINIMAL_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
    b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
    b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x87"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
    b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
    b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd2\x8a(\x03\xff\xd9"
)


@when('the Function URL POST /add-tags is called for the photo with tags "{tags}" and the correct API key')
def step_add_tags_correct_key(context, tags):
    tag_list = [t.strip() for t in tags.split(",")]
    context.http_status, context.http_body = _api_post(
        "/add-tags", {"s3_key": context.last_photo_key, "tags": tag_list}
    )


@when("the Function URL POST /add-tags is called with an incorrect API key")
def step_add_tags_wrong_key(context):
    context.http_status, _ = _api_post("/add-tags", {"s3_key": "dummy.jpg", "tags": ["cat"]}, api_key="wrong-key")


@then('searching for "{tag}" via the Lambda should return the photo')
def step_lambda_search_includes_photo_generic(context, tag):
    client = boto3.client("lambda")
    response = client.invoke(
        FunctionName=context.searcher_lambda_name,
        InvocationType="RequestResponse",
        Payload=json.dumps({"tags": [tag]}),
    )
    results = json.loads(response["Payload"].read())
    result_keys = {r["s3_key"] for r in results}
    assert context.last_photo_key in result_keys, (
        f"Expected {context.last_photo_key!r} in results for tag {tag!r}, got: {result_keys}"
    )


@when('the Function URL POST /remove-tag is called for the photo with tag "{tag}" and the correct API key')
def step_remove_tag_correct_key(context, tag):
    context.http_status, context.http_body = _api_post(
        "/remove-tag", {"s3_key": context.last_photo_key, "tag": tag}
    )
    context.removed_tag = tag


@when("the Function URL POST /remove-tag is called with an incorrect API key")
def step_remove_tag_wrong_key(context):
    context.http_status, _ = _api_post("/remove-tag", {"s3_key": "dummy.jpg", "tag": "cat"}, api_key="wrong-key")


@then('searching for "{tag}" via the Lambda should not return the photo')
def step_lambda_search_excludes_photo(context, tag):
    client = boto3.client("lambda")
    response = client.invoke(
        FunctionName=context.searcher_lambda_name,
        InvocationType="RequestResponse",
        Payload=json.dumps({"tags": [tag]}),
    )
    results = json.loads(response["Payload"].read())
    result_keys = {r["s3_key"] for r in results}
    assert context.last_photo_key not in result_keys, (
        f"Expected {context.last_photo_key!r} to be absent after tag removal, got: {result_keys}"
    )


@then('searching for "{tag}" via the Lambda should still return the photo')
def step_lambda_search_includes_photo(context, tag):
    client = boto3.client("lambda")
    response = client.invoke(
        FunctionName=context.searcher_lambda_name,
        InvocationType="RequestResponse",
        Payload=json.dumps({"tags": [tag]}),
    )
    results = json.loads(response["Payload"].read())
    result_keys = {r["s3_key"] for r in results}
    assert context.last_photo_key in result_keys, (
        f"Expected {context.last_photo_key!r} in results for tag {tag!r}, got: {result_keys}"
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
