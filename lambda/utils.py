"""Shared utilities for Lambda handlers."""

import os


def get_required_env(name: str) -> str:
    """Return the value of a required environment variable or raise RuntimeError."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} environment variable is not set")
    return value
