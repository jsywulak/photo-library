"""
inbox_handler.py — AWS Lambda entry point for inbox management.

Handles listing, processing, and archiving unprocessed photos in the inbox
S3 bucket via a Lambda Function URL.

Routes:
  GET  /inbox          — paginated list of inbox photos
  POST /process-inbox  — promote an inbox photo to the photos bucket
  POST /archive-inbox  — soft-delete an inbox photo

Environment variables required:
  NEON_DATABASE_URL — Neon PostgreSQL connection string
  API_KEY           — Secret key checked in x-api-key header
  INBOX_BUCKET      — S3 bucket containing unprocessed photos
  PHOTOS_BUCKET     — S3 bucket to promote processed photos into
  THUMBNAIL_BUCKET  — Public S3 bucket containing thumbnails
"""

import json
import logging
from contextlib import contextmanager

import boto3
import psycopg2
from botocore.config import Config

from inbox import _INBOX_PAGE_SIZE, archive_inbox_photo, list_inbox, process_inbox_photo
from utils import get_required_env

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_DB_URL = get_required_env("NEON_DATABASE_URL")
_API_KEY = get_required_env("API_KEY")
_INBOX_BUCKET = get_required_env("INBOX_BUCKET")
_PHOTOS_BUCKET = get_required_env("PHOTOS_BUCKET")
_THUMBNAIL_BUCKET = get_required_env("THUMBNAIL_BUCKET")
_FRONTEND_ORIGIN = f"https://{get_required_env('FRONTEND_DOMAIN')}"

_s3_client = boto3.client("s3", config=Config(signature_version="s3v4"))

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
    http_ctx = event.get("requestContext", {}).get("http", {})
    method = http_ctx.get("method", "").upper()
    path = http_ctx.get("path", "/")

    if method == "OPTIONS":
        return _http_response(200, {})

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if headers.get("x-api-key") != _API_KEY:
        return _http_response(401, {"error": "Unauthorized"})

    if method == "GET" and path == "/inbox":
        qs = event.get("queryStringParameters") or {}
        cursor = qs.get("cursor") or None
        limit = _INBOX_PAGE_SIZE
        try:
            raw = qs.get("limit")
            if raw is not None:
                limit = max(1, min(int(raw), 200))
        except (ValueError, TypeError):
            return _http_response(400, {"error": "limit must be an integer"})
        try:
            with _db() as conn:
                return _http_response(200, list_inbox(conn, _s3_client, _INBOX_BUCKET, _THUMBNAIL_BUCKET, limit=limit, cursor=cursor))
        except ValueError as e:
            return _http_response(400, {"error": str(e)})

    if method == "POST" and path == "/process-inbox":
        payload = _parse_body(event)
        if payload is None:
            return _http_response(400, {"error": "Invalid JSON body"})
        s3_key = payload.get("s3_key")
        if not s3_key:
            return _http_response(400, {"error": "s3_key is required"})
        with _db() as conn:
            found = process_inbox_photo(s3_key, conn, _s3_client, _INBOX_BUCKET, _PHOTOS_BUCKET)
            if not found:
                return _http_response(404, {"error": "Photo not found"})
            conn.commit()
            return _http_response(200, {"success": True})

    if method == "POST" and path == "/archive-inbox":
        payload = _parse_body(event)
        if payload is None:
            return _http_response(400, {"error": "Invalid JSON body"})
        s3_key = payload.get("s3_key")
        if not s3_key:
            return _http_response(400, {"error": "s3_key is required"})
        with _db() as conn:
            found = archive_inbox_photo(s3_key, conn, _INBOX_BUCKET)
            if not found:
                return _http_response(404, {"error": "Photo not found"})
            conn.commit()
            return _http_response(200, {"success": True})

    return _http_response(404, {"error": "Not found"})
