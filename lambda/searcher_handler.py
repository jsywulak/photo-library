"""
searcher_handler.py — AWS Lambda entry point for the photo searcher.

Supports two invocation modes:
  - Direct invocation (tests, CLI): {"tags": ["cat", "outdoor", ...]}
  - Lambda Function URL (frontend):  POST with JSON body and x-api-key header

Returns a list of matching photos ranked by tag match count:
  [{"s3_key": "photo.jpg", "match_count": 2}, ...]

Environment variables required:
  NEON_DATABASE_URL — Neon PostgreSQL connection string
  API_KEY           — Secret key checked in x-api-key header (Function URL only)
"""

import json
import logging

import boto3
import psycopg2

from searcher import get_random_tags, list_inbox, search
from utils import get_required_env

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_DB_URL = get_required_env("NEON_DATABASE_URL")
_API_KEY = get_required_env("API_KEY")
_S3_BUCKET = get_required_env("S3_BUCKET")
_THUMBNAIL_BUCKET = get_required_env("THUMBNAIL_BUCKET")
_INBOX_BUCKET = get_required_env("INBOX_BUCKET")

_s3_client = boto3.client("s3")

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "x-api-key, content-type",
}


def _http_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {**_CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    is_function_url = "requestContext" in event

    if is_function_url:
        http_ctx = event.get("requestContext", {}).get("http", {})
        method = http_ctx.get("method", "").upper()
        path = http_ctx.get("path", "/")

        if method == "OPTIONS":
            return _http_response(200, {})

        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        if headers.get("x-api-key") != _API_KEY:
            return _http_response(401, {"error": "Unauthorized"})

        if method == "GET" and path == "/tags":
            conn = psycopg2.connect(_DB_URL, connect_timeout=10)
            try:
                return _http_response(200, get_random_tags(conn))
            finally:
                conn.close()

        if method == "GET" and path == "/inbox":
            conn = psycopg2.connect(_DB_URL, connect_timeout=10)
            try:
                return _http_response(200, list_inbox(conn, _s3_client, _INBOX_BUCKET, _THUMBNAIL_BUCKET))
            finally:
                conn.close()

        try:
            payload = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _http_response(400, {"error": "Invalid JSON body"})

        tags = payload.get("tags", [])
        if not isinstance(tags, list):
            return _http_response(400, {"error": "tags must be a list"})
    else:
        tags = event.get("tags", [])

    if not tags:
        body = {"error": "No tags provided"}
        return _http_response(400, body) if is_function_url else body

    logger.info("Searching for tags: %s", tags)

    conn = psycopg2.connect(_DB_URL, connect_timeout=10)
    try:
        results = search(tags, conn, _s3_client, _S3_BUCKET, _THUMBNAIL_BUCKET)
        logger.info("Found %d results", len(results))
        return _http_response(200, results) if is_function_url else results
    finally:
        conn.close()
