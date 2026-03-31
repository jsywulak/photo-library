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
from contextlib import contextmanager

import boto3
import psycopg2
from botocore.config import Config

from searcher import add_tags, get_random_tags, remove_tag, search
from utils import get_required_env

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_DB_URL = get_required_env("NEON_DATABASE_URL")
_API_KEY = get_required_env("API_KEY")
_S3_BUCKET = get_required_env("S3_BUCKET")
_THUMBNAIL_BUCKET = get_required_env("THUMBNAIL_BUCKET")
_FRONTEND_ORIGIN = f"https://{get_required_env('FRONTEND_DOMAIN')}"

_s3_client = boto3.client("s3", config=Config(signature_version="s3v4"))

_DEFAULT_DIRECT_LIMIT = 10_000  # no public API cap for direct Lambda invocations

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": _FRONTEND_ORIGIN,
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "x-api-key, content-type",
}


@contextmanager
def _db():
    conn = psycopg2.connect(_DB_URL, connect_timeout=10)
    try:
        yield conn
    finally:
        conn.close()


def _parse_body(event):
    try:
        return json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return None


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
            with _db() as conn:
                return _http_response(200, get_random_tags(conn))

        if method == "POST" and path == "/add-tags":
            payload = _parse_body(event)
            if payload is None:
                return _http_response(400, {"error": "Invalid JSON body"})
            s3_key = payload.get("s3_key")
            tags = payload.get("tags", [])
            if not s3_key or not isinstance(tags, list):
                return _http_response(400, {"error": "s3_key and tags (list) are required"})
            with _db() as conn:
                count = add_tags(s3_key, tags, conn)
                if count is None:
                    return _http_response(404, {"error": "Photo not found"})
                conn.commit()
                return _http_response(200, {"added": count})

        if method == "POST" and path == "/remove-tag":
            payload = _parse_body(event)
            if payload is None:
                return _http_response(400, {"error": "Invalid JSON body"})
            s3_key = payload.get("s3_key")
            tag = payload.get("tag")
            if not s3_key or not tag:
                return _http_response(400, {"error": "s3_key and tag are required"})
            with _db() as conn:
                found = remove_tag(s3_key, tag, conn)
                conn.commit()
                return _http_response(200, {"removed": found})

        payload = _parse_body(event)
        if payload is None:
            return _http_response(400, {"error": "Invalid JSON body"})

        tags = payload.get("tags", [])
        if not isinstance(tags, list):
            return _http_response(400, {"error": "tags must be a list"})
    else:
        tags = event.get("tags", [])

    if not tags:
        body = {"error": "No tags provided"}
        return _http_response(400, body) if is_function_url else body

    if is_function_url:
        raw_limit = (payload or {}).get("limit", 200)
        limit = max(1, min(int(raw_limit), 200))
    else:
        limit = int(event.get("limit", _DEFAULT_DIRECT_LIMIT))

    logger.info("Searching for tags: %s (limit=%d)", tags, limit)

    with _db() as conn:
        results = search(tags, conn, _s3_client, _S3_BUCKET, _THUMBNAIL_BUCKET, limit=limit)
        logger.info("Found %d results", len(results))
        return _http_response(200, results) if is_function_url else results
