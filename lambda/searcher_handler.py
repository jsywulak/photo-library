"""
searcher_handler.py — AWS Lambda entry point for the photo searcher.

Expected invocation payload:
  {"tags": ["cat", "outdoor", ...]}

Returns a list of matching photos ranked by tag match count:
  [{"s3_key": "photo.jpg", "match_count": 2}, ...]

Environment variables required:
  NEON_DATABASE_URL — Neon PostgreSQL connection string
"""

import logging
import os

import psycopg2

from searcher import search

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_DB_URL = os.environ.get("NEON_DATABASE_URL")
if not _DB_URL:
    raise RuntimeError("NEON_DATABASE_URL environment variable is not set")


def lambda_handler(event, context):
    tags = event.get("tags", [])
    if not tags:
        return {"error": "No tags provided"}

    logger.info("Searching for tags: %s", tags)

    conn = psycopg2.connect(_DB_URL, connect_timeout=10)
    try:
        results = search(tags, conn)
        logger.info("Found %d results", len(results))
        return results
    finally:
        conn.close()
