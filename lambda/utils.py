"""Shared utilities for Lambda handlers."""

import os
from pathlib import Path

from psycopg2.extras import Json


def get_required_env(name: str) -> str:
    """Return the value of a required environment variable or raise RuntimeError."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is not set")
    return value


def thumbnail_key(s3_key: str) -> str:
    """Derive the thumbnail S3 key from a source s3_key.

    The full path is preserved so that photos sharing the same filename
    across different directories don't collide on the same thumbnail key.
    """
    return f"thumbnails/{Path(s3_key).with_suffix('.webp')}"


def record_event(
    cur,
    s3_key: str,
    bucket: str,
    event_type: str,
    actor: str,
    photo_id: int | None = None,
    details: dict | None = None,
) -> None:
    """Append a row to the photo_events audit log using the caller's cursor.

    Caller owns the transaction. For failure-path events whose outer transaction
    has been poisoned, write the event in a fresh transaction after rolling back.
    """
    cur.execute(
        "INSERT INTO photo_events (photo_id, s3_key, bucket, event_type, actor, details)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        (photo_id, s3_key, bucket, event_type, actor, Json(details) if details else None),
    )
