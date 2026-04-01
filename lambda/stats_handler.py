"""
stats_handler.py — AWS Lambda entry point for the stats dashboard.

Routes:
  GET /stats                    — return all stats metrics (backwards compat)
  GET /stats/inbox-count        — inbox photo count (DB)
  GET /stats/db-count           — processed photo count (DB)
  GET /stats/archived-count     — archived photo count (DB)
  GET /stats/inbox-s3-count     — inbox S3 object count
  GET /stats/processed-s3-count — processed S3 object count
  GET /stats/thumbnail-count    — thumbnail S3 object count
  GET /stats/orphaned-thumbnails — orphaned thumbnail count
  GET /stats/orphaned-processed  — orphaned processed object count
  GET /stats/orphaned-inbox      — orphaned inbox object count
  GET /stats/top-tags            — top 5 tags by usage

Environment variables required:
  NEON_DATABASE_URL  — Neon PostgreSQL connection string
  API_KEY            — Secret key checked in x-api-key header
  INBOX_BUCKET       — S3 bucket containing unprocessed photos
  PHOTOS_BUCKET      — S3 bucket containing processed photos
  THUMBNAIL_BUCKET   — S3 bucket containing thumbnails
  FRONTEND_DOMAIN    — Full origin for CORS (e.g. http://lax.jsywulak.com)
"""

import json
import logging
from contextlib import contextmanager

import boto3
import psycopg2

from stats import (
    get_stats,
    count_db_photos,
    count_archived_photos,
    count_s3_objects,
    count_orphaned_thumbnails,
    count_orphaned_processed,
    count_orphaned_inbox,
    get_top_tags,
)
from utils import get_required_env

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_DB_URL = get_required_env("NEON_DATABASE_URL")
_API_KEY = get_required_env("API_KEY")
_INBOX_BUCKET = get_required_env("INBOX_BUCKET")
_PHOTOS_BUCKET = get_required_env("PHOTOS_BUCKET")
_THUMBNAIL_BUCKET = get_required_env("THUMBNAIL_BUCKET")
_FRONTEND_ORIGIN = get_required_env("FRONTEND_DOMAIN")

_s3_client = boto3.client("s3")

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": _FRONTEND_ORIGIN,
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "x-api-key, content-type",
}


@contextmanager
def _db():
    conn = psycopg2.connect(_DB_URL, connect_timeout=10)
    try:
        yield conn
    finally:
        conn.close()


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

    if method != "GET":
        return _http_response(404, {"error": "Not found"})

    # Backwards-compatible aggregate endpoint
    if path == "/stats":
        with _db() as conn:
            return _http_response(200, get_stats(conn, _s3_client, _INBOX_BUCKET, _PHOTOS_BUCKET, _THUMBNAIL_BUCKET))

    # Per-stat endpoints — DB only
    if path == "/stats/inbox-count":
        with _db() as conn:
            return _http_response(200, {"value": count_db_photos(conn, _INBOX_BUCKET)})

    if path == "/stats/db-count":
        with _db() as conn:
            return _http_response(200, {"value": count_db_photos(conn, _PHOTOS_BUCKET)})

    if path == "/stats/archived-count":
        with _db() as conn:
            return _http_response(200, {"value": count_archived_photos(conn, _INBOX_BUCKET)})

    if path == "/stats/top-tags":
        with _db() as conn:
            return _http_response(200, {"value": get_top_tags(conn)})

    # Per-stat endpoints — S3 only (no DB connection needed)
    if path == "/stats/inbox-s3-count":
        return _http_response(200, {"value": count_s3_objects(_s3_client, _INBOX_BUCKET)})

    if path == "/stats/processed-s3-count":
        return _http_response(200, {"value": count_s3_objects(_s3_client, _PHOTOS_BUCKET)})

    if path == "/stats/thumbnail-count":
        return _http_response(200, {"value": count_s3_objects(_s3_client, _THUMBNAIL_BUCKET, "thumbnails/")})

    # Per-stat endpoints — DB + S3
    if path == "/stats/orphaned-thumbnails":
        with _db() as conn:
            return _http_response(200, {"value": count_orphaned_thumbnails(conn, _s3_client, _THUMBNAIL_BUCKET)})

    if path == "/stats/orphaned-processed":
        with _db() as conn:
            return _http_response(200, {"value": count_orphaned_processed(conn, _s3_client, _PHOTOS_BUCKET)})

    if path == "/stats/orphaned-inbox":
        with _db() as conn:
            return _http_response(200, {"value": count_orphaned_inbox(conn, _s3_client, _INBOX_BUCKET)})

    return _http_response(404, {"error": "Not found"})
