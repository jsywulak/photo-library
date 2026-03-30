"""Shared utilities for maintenance scripts."""

import json
from contextlib import contextmanager
from pathlib import Path

import boto3
import psycopg2


def thumbnail_key(s3_key: str) -> str:
    """Derive the thumbnail S3 key from a source s3_key.

    The full path is preserved so that photos sharing the same filename
    across different directories don't collide on the same thumbnail key.
    """
    return f"thumbnails/{Path(s3_key).with_suffix('.webp')}"


def is_valid_image(key: str) -> bool:
    """Return True for JPEG files, excluding macOS metadata files (._*)."""
    p = Path(key)
    return p.name[:2] != "._" and p.suffix.lower() in (".jpg", ".jpeg")


def list_s3_keys(bucket: str, prefix: str = "", filter_fn=None) -> set[str]:
    """List S3 object keys, optionally filtered by prefix and/or a predicate."""
    s3 = boto3.client("s3")
    keys = set()
    paginator = s3.get_paginator("list_objects_v2")
    kwargs = {"Bucket": bucket}
    if prefix:
        kwargs["Prefix"] = prefix
    for page in paginator.paginate(**kwargs):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if filter_fn is None or filter_fn(key):
                keys.add(key)
    return keys


def make_s3_event(bucket: str, key: str) -> dict:
    """Build an S3 notification event payload for Lambda invocation."""
    return {
        "Records": [{
            "s3": {
                "bucket": {"name": bucket},
                "object": {"key": key},
            }
        }]
    }


def invoke_lambda(client, function_name: str, payload: dict, async_: bool = False):
    """Invoke a Lambda function and return the parsed JSON response.

    Raises RuntimeError on Lambda function errors.
    Returns None for async invocations.
    """
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="Event" if async_ else "RequestResponse",
        Payload=json.dumps(payload).encode(),
    )
    if async_:
        return None
    result = json.loads(response["Payload"].read())
    if "FunctionError" in response:
        raise RuntimeError(result.get("errorMessage", str(result)))
    return result


@contextmanager
def db_connection(db_url: str):
    """Context manager that opens a psycopg2 connection and ensures it is closed."""
    conn = psycopg2.connect(db_url)
    try:
        yield conn
    finally:
        conn.close()
