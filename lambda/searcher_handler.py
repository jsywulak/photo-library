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
import os

import psycopg2

from searcher import search

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_DB_URL = os.environ.get("NEON_DATABASE_URL")
if not _DB_URL:
    raise RuntimeError("NEON_DATABASE_URL environment variable is not set")

_API_KEY = os.environ.get("API_KEY")
if not _API_KEY:
    raise RuntimeError("API_KEY environment variable is not set")

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
        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        if headers.get("x-api-key") != _API_KEY:
            return _http_response(401, {"error": "Unauthorized"})

        try:
            payload = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _http_response(400, {"error": "Invalid JSON body"})

        tags = payload.get("tags", [])
    else:
        tags = event.get("tags", [])

    if not tags:
        body = {"error": "No tags provided"}
        return _http_response(400, body) if is_function_url else body

    logger.info("Searching for tags: %s", tags)

    conn = psycopg2.connect(_DB_URL, connect_timeout=10)
    try:
        results = search(tags, conn)
        logger.info("Found %d results", len(results))
        return _http_response(200, results) if is_function_url else results
    finally:
        conn.close()
