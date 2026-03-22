"""Shared utilities for Lambda handlers."""

import os
from pathlib import Path


def get_required_env(name: str) -> str:
    """Return the value of a required environment variable or raise RuntimeError."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is not set")
    return value


def thumbnail_key(s3_key: str) -> str:
    """Derive the thumbnail S3 key from a source s3_key."""
    return f"thumbnails/{Path(s3_key).stem}.webp"
