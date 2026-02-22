"""
handler.py — AWS Lambda entry point for the photo processor.

Triggered by S3 events. Fetches the image, calls process_one, and commits.
Environment variables required:
  NEON_DATABASE_URL   — Neon PostgreSQL connection string
  ANTHROPIC_API_KEY   — Anthropic API key (read automatically by the client)
"""

import os

import anthropic
import boto3
import psycopg2

from processor import process_one


def lambda_handler(event, context):
    record = event["Records"][0]["s3"]
    bucket = record["bucket"]["name"]
    key = record["object"]["key"]

    image_bytes = (
        boto3.client("s3")
        .get_object(Bucket=bucket, Key=key)["Body"]
        .read()
    )

    conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
    conn.autocommit = False
    try:
        status = process_one(key, image_bytes, conn, anthropic.Anthropic())
        conn.commit()
        return {"status": status, "s3_key": key}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
