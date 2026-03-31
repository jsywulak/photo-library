"""Shared helpers for BDD step definitions."""

import os
from pathlib import Path

import psycopg2


def thumbnail_key(s3_key: str) -> str:
    """Derive the thumbnail S3 key from a source s3_key."""
    return f"thumbnails/{Path(s3_key).stem}.webp"


def neon_conn():
    """Open a new connection to the Neon database."""
    return psycopg2.connect(os.environ["NEON_DATABASE_URL"])


def seed_photo(conn, s3_key, tags, bucket="photo-tagging-photos", content_hash=None):
    """Insert a photo and its tags. Does NOT commit — caller owns the transaction.

    Args:
        conn: psycopg2 connection
        s3_key: unique S3 key / filename for the photo
        tags: iterable of tag name strings (normalised to lowercase before insert)
        bucket: source bucket name (defaults to 'photo-tagging-photos')
        content_hash: optional SHA256 hex digest of the photo bytes

    Returns:
        The inserted photo id.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO photos (s3_key, bucket, processed_at, content_hash) VALUES (%s, %s, NOW(), %s) RETURNING id",
            (s3_key, bucket, content_hash),
        )
        photo_id = cur.fetchone()[0]
        for tag_name in tags:
            cur.execute(
                """
                INSERT INTO tags (name) VALUES (%s)
                ON CONFLICT (LOWER(name)) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (tag_name.strip().lower(),),
            )
            tag_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO photo_tags (photo_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (photo_id, tag_id),
            )
    return photo_id
