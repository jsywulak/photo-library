"""
Step definitions for infrastructure.feature.

Checks that cloud resources are reachable. Requires:
  - NEON_DATABASE_URL set in .env (standard postgres:// connection string)
"""

import json
import os
import socket
import urllib.request
from urllib.parse import urlparse

import boto3
from behave import given, then


@given("a Neon database URL is configured")
def step_neon_url_configured(context):
    url = os.environ.get("NEON_DATABASE_URL")
    assert url, "NEON_DATABASE_URL is not set in the environment"
    parsed = urlparse(url)
    assert parsed.hostname, f"Could not parse hostname from NEON_DATABASE_URL"
    context.db_host = parsed.hostname


@then("the database should be reachable on port 5432")
def step_db_reachable(context):
    try:
        with socket.create_connection((context.db_host, 5432), timeout=10):
            pass
    except OSError as e:
        raise AssertionError(f"Could not reach database at {context.db_host}:5432 — {e}")


@then("the following tables should exist:")
def step_tables_exist(context):
    import psycopg2
    url = os.environ["NEON_DATABASE_URL"]
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
            """)
            existing = {row[0] for row in cur.fetchall()}
    finally:
        conn.close()

    expected = [row["table"] for row in context.table]
    missing = [t for t in expected if t not in existing]
    assert not missing, f"Missing tables: {', '.join(missing)}"


@given("the processor Lambda is configured")
def step_processor_lambda_configured(context):
    name = os.environ.get("PROCESSOR_LAMBDA_NAME")
    assert name, "PROCESSOR_LAMBDA_NAME is not set in the environment"
    context.processor_lambda_name = name


@then("the reserved concurrency should be {limit:d}")
def step_reserved_concurrency(context, limit):
    lamb = boto3.client("lambda")
    resp = lamb.get_function_concurrency(FunctionName=context.processor_lambda_name)
    actual = resp.get("ReservedConcurrentExecutions")
    assert actual == limit, (
        f"Expected reserved concurrency {limit}, got {actual!r}"
    )


@given("a frontend bucket name is configured")
def step_frontend_bucket_configured(context):
    bucket = os.environ.get("FRONTEND_DOMAIN")
    assert bucket, "FRONTEND_DOMAIN is not set in the environment"
    context.frontend_bucket = bucket


@then("the bucket should have static website hosting enabled")
def step_bucket_website_enabled(context):
    s3 = boto3.client("s3")
    try:
        s3.get_bucket_website(Bucket=context.frontend_bucket)
    except s3.exceptions.NoSuchWebsiteConfiguration:
        raise AssertionError(
            f"Bucket {context.frontend_bucket!r} does not have website hosting enabled"
        )


@given("the searcher Lambda is configured")
def step_searcher_lambda_configured(context):
    name = os.environ.get("SEARCHER_LAMBDA_NAME")
    assert name, "SEARCHER_LAMBDA_NAME is not set in the environment"
    context.searcher_lambda_name = name


def _get_policy_statements(context):
    lamb = boto3.client("lambda")
    try:
        resp = lamb.get_policy(FunctionName=context.searcher_lambda_name)
    except lamb.exceptions.ResourceNotFoundException:
        raise AssertionError(
            f"No resource policy found on Lambda {context.searcher_lambda_name!r}"
        )
    return json.loads(resp["Policy"]).get("Statement", [])


@then('the Lambda resource policy should not grant unrestricted lambda:InvokeFunction to Principal "*"')
def step_no_unrestricted_invoke_function_permission(context):
    """Check there is no InvokeFunction permission without the InvokedViaFunctionUrl condition.

    An unrestricted lambda:InvokeFunction allows anyone with AWS credentials to call the
    function directly via the AWS API, bypassing the Function URL and the API key check.
    The correct permission must include the lambda:InvokedViaFunctionUrl condition.
    """
    violations = [
        stmt.get("Sid", "<no sid>")
        for stmt in _get_policy_statements(context)
        if stmt.get("Action") == "lambda:InvokeFunction"
        and stmt.get("Principal") in ("*", {"AWS": "*"})
        and "lambda:InvokedViaFunctionUrl" not in stmt.get("Condition", {}).get("Bool", {})
    ]
    assert not violations, (
        f"Lambda {context.searcher_lambda_name!r} has unrestricted InvokeFunction permission(s): "
        f"{violations} — must include lambda:InvokedViaFunctionUrl condition"
    )


@then("the Lambda resource policy should grant lambda:InvokeFunction only via function URL")
def step_invoke_function_via_url_permission_exists(context):
    """Verify the InvokedViaFunctionUrl-scoped InvokeFunction permission is present.

    Lambda Function URL invocations require both lambda:InvokeFunctionUrl (for URL access)
    and lambda:InvokeFunction with lambda:InvokedViaFunctionUrl: true (for actual execution).
    """
    has_url_invoke = any(
        stmt.get("Action") == "lambda:InvokeFunction"
        and stmt.get("Principal") in ("*", {"AWS": "*"})
        and stmt.get("Condition", {}).get("Bool", {}).get("lambda:InvokedViaFunctionUrl") == "true"
        for stmt in _get_policy_statements(context)
    )
    assert has_url_invoke, (
        f"Lambda {context.searcher_lambda_name!r} is missing lambda:InvokeFunction permission "
        f"with lambda:InvokedViaFunctionUrl condition — Function URL will return 403"
    )


@then("the website URL should return HTTP 200")
def step_website_url_returns_200(context):
    s3 = boto3.client("s3")
    location = s3.get_bucket_location(Bucket=context.frontend_bucket)["LocationConstraint"]
    region = location or "us-east-1"
    url = f"http://{context.frontend_bucket}.s3-website-{region}.amazonaws.com/"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            assert resp.status == 200, f"Expected 200, got {resp.status}"
    except urllib.error.HTTPError as e:
        raise AssertionError(f"Website URL returned HTTP {e.code}: {url}")
