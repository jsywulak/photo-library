"""
Step definitions for infrastructure.feature.

Checks that cloud resources are reachable. Requires:
  - NEON_DATABASE_URL set in .env (standard postgres:// connection string)
"""

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


@given("a frontend bucket name is configured")
def step_frontend_bucket_configured(context):
    bucket = os.environ.get("FRONTEND_BUCKET")
    assert bucket, "FRONTEND_BUCKET is not set in the environment"
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
