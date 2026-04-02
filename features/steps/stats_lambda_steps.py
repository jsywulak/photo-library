"""
Step definitions for stats_lambda.feature.

Requires in .env:
  - STATS_LAMBDA_NAME  name of the deployed stats Lambda function
  - STATS_URL          Function URL of the deployed stats Lambda
  - API_KEY            shared API key for Lambda auth
"""

import json
import os
import urllib.request

import boto3
from behave import given, then, when


def _api_get(path, api_key=None):
    url = os.environ["STATS_URL"].rstrip("/") + path
    key = api_key if api_key is not None else os.environ["API_KEY"]
    req = urllib.request.Request(url, headers={"x-api-key": key}, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, None


@given("the stats Lambda is deployed")
def step_stats_lambda_deployed(context):
    name = os.environ["STATS_LAMBDA_NAME"]
    client = boto3.client("lambda")
    response = client.get_function(FunctionName=name)
    context.stats_lambda_name = name
    context.stats_lambda_state = response["Configuration"]["State"]
    assert context.stats_lambda_state == "Active", (
        f"Expected Lambda state Active, got {context.stats_lambda_state!r}"
    )


@when("the stats Function URL GET /stats is called with the correct API key")
def step_get_stats_correct_key(context):
    context.stats_http_status, context.stats_http_body = _api_get("/stats")


@when("the stats Function URL GET /stats is called with an incorrect API key")
def step_get_stats_wrong_key(context):
    context.stats_http_status, context.stats_http_body = _api_get("/stats", api_key="wrong-key")


@then("the stats HTTP response status should be {status:d}")
def step_stats_http_status(context, status):
    assert context.stats_http_status == status, (
        f"Expected HTTP {status}, got {context.stats_http_status}"
    )


_NUMERIC_STAT_FIELDS = (
    "inbox_count", "photos_count", "db_count", "archived_count",
    "total_photos", "inbox_s3_count", "processed_s3_count",
    "thumbnail_count", "orphaned_thumbnails", "orphaned_processed", "orphaned_inbox",
)


@then("the stats response body contains all numeric stat fields as non-negative integers")
def step_stats_response_has_fields(context):
    body = context.stats_http_body
    assert isinstance(body, dict), f"Expected dict response body, got: {type(body)}"
    for field in _NUMERIC_STAT_FIELDS:
        assert field in body, f"Missing field {field!r} in response: {body}"
        assert isinstance(body[field], int), (
            f"Expected {field!r} to be an integer, got {type(body[field])}: {body[field]}"
        )
        assert body[field] >= 0, f"Expected {field!r} >= 0, got {body[field]}"


@when("the stats Function URL GET /stats/inbox-count-mismatch is called with the correct API key")
def step_get_inbox_count_mismatch(context):
    context.stats_http_status, context.stats_http_body = _api_get("/stats/inbox-count-mismatch")


@then("the stats response body contains inbox-count-mismatch fields s3_count and db_count as non-negative integers")
def step_stats_inbox_count_mismatch_fields(context):
    body = context.stats_http_body
    assert isinstance(body, dict), f"Expected dict response body, got: {type(body)}"
    for field in ("s3_count", "db_count"):
        assert field in body, f"Missing field {field!r} in response: {body}"
        assert isinstance(body[field], int), (
            f"Expected {field!r} to be an integer, got {type(body[field])}: {body[field]}"
        )
        assert body[field] >= 0, f"Expected {field!r} >= 0, got {body[field]}"


@then("the stats response body contains top_tags as a list")
def step_stats_response_has_top_tags(context):
    body = context.stats_http_body
    assert "top_tags" in body, f"Missing field 'top_tags' in response: {body}"
    assert isinstance(body["top_tags"], list), (
        f"Expected 'top_tags' to be a list, got {type(body['top_tags'])}: {body['top_tags']}"
    )
    for entry in body["top_tags"]:
        assert "name" in entry and "count" in entry, f"top_tags entry missing name/count: {entry}"
