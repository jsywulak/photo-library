"""
searcher.py — photo search logic.

search() queries photos that match any of the given tags, ranked by how many
of the searched tags each photo has. Photos with no matching tags are excluded.

Each result includes:
  - url: a presigned S3 URL valid for 1 hour for full-size image display
  - thumbnail_url: a public URL to the WebP thumbnail in the thumbnail bucket

Returns a paginated envelope:
  {"items": [...], "next_cursor": str | None, "total": int}
"""

import base64
import json

from utils import record_event, thumbnail_key as _thumbnail_key

_PRESIGNED_URL_EXPIRY = 3600  # seconds
_DEFAULT_TAG_COUNT = 20
_SEARCH_PAGE_SIZE = 200


def _thumbnail_url(s3_key: str, thumbnail_bucket: str) -> str:
    return f"https://{thumbnail_bucket}.s3.amazonaws.com/{_thumbnail_key(s3_key)}"


def _normalise_tags(tags: list[str]) -> list[str]:
    return [t.strip().lower() for t in tags if t.strip()]


def _encode_cursor(match_count: int, row_id: int) -> str:
    return base64.urlsafe_b64encode(
        json.dumps({"mc": match_count, "id": row_id}).encode()
    ).decode().rstrip("=")


def _decode_cursor(cursor) -> tuple:
    if cursor is None:
        return None, None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return decoded["mc"], decoded["id"]
    except Exception:
        raise ValueError(f"Invalid cursor: {cursor!r}")


def get_random_tags(db_conn, count: int = _DEFAULT_TAG_COUNT) -> list[str]:
    with db_conn.cursor() as cur:
        cur.execute("SELECT name FROM tags ORDER BY RANDOM() LIMIT %s", (count,))
        return [row[0] for row in cur.fetchall()]


def add_tags(s3_key: str, tags: list[str], db_conn) -> int | None:
    """Add tags to a photo, creating them if needed and restoring any that were removed.

    Returns the number of associations added or restored, or None if the photo was not found.
    """
    normalised = _normalise_tags(tags)
    if not normalised:
        return 0

    with db_conn.cursor() as cur:
        cur.execute("SELECT id, bucket FROM photos WHERE s3_key = %s", (s3_key,))
        row = cur.fetchone()
        if not row:
            return None
        photo_id, bucket = row

        count = 0
        for tag_name in normalised:
            cur.execute(
                """
                INSERT INTO tags (name) VALUES (%s)
                ON CONFLICT (LOWER(name)) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (tag_name,),
            )
            tag_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO photo_tags (photo_id, tag_id)
                VALUES (%s, %s)
                ON CONFLICT (photo_id, tag_id) DO UPDATE SET removed_at = NULL
                """,
                (photo_id, tag_id),
            )
            count += cur.rowcount
            record_event(
                cur, s3_key, bucket, "tag_added", "searcher",
                photo_id=photo_id, details={"tag": tag_name},
            )

    return count


def remove_tag(s3_key: str, tag: str, db_conn) -> bool:
    """Logically remove a tag from a photo. Returns True if the association was found and updated."""
    normalised = tag.strip().lower()
    with db_conn.cursor() as cur:
        cur.execute(
            """
            UPDATE photo_tags pt
            SET removed_at = NOW()
            FROM photos p, tags t
            WHERE pt.photo_id = p.id
              AND pt.tag_id = t.id
              AND p.s3_key = %s
              AND t.name = %s
              AND pt.removed_at IS NULL
            RETURNING p.id, p.bucket
            """,
            (s3_key, normalised),
        )
        rows = cur.fetchall()
        if not rows:
            return False
        photo_id, bucket = rows[0]
        record_event(
            cur, s3_key, bucket, "tag_removed", "searcher",
            photo_id=photo_id, details={"tag": normalised},
        )
    return True


def archive_photo(s3_key: str, db_conn) -> bool:
    """Set archived_at on a photo. Returns False if not found or already archived."""
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE photos SET archived_at = NOW() WHERE s3_key = %s AND archived_at IS NULL "
            "RETURNING id, bucket",
            (s3_key,),
        )
        row = cur.fetchone()
        if row is None:
            return False
        photo_id, bucket = row
        record_event(cur, s3_key, bucket, "archived", "searcher", photo_id=photo_id)
    return True


def search(tags: list[str], db_conn, s3_client=None, bucket: str = None, thumbnail_bucket: str = None,
           limit: int = _SEARCH_PAGE_SIZE, cursor=None) -> dict:
    """Search for photos matching any of the given tags.

    Returns a paginated envelope: {"items": [...], "next_cursor": str | None, "total": int}
    """
    normalised = _normalise_tags(tags)
    cursor_mc, cursor_id = _decode_cursor(cursor)

    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT p.id FROM photos p
                JOIN photo_tags pt ON pt.photo_id = p.id AND pt.removed_at IS NULL
                JOIN tags t ON t.id = pt.tag_id
                WHERE p.archived_at IS NULL
                GROUP BY p.id
                HAVING COUNT(CASE WHEN t.name = ANY(%s) THEN 1 END) > 0
            ) AS sub
            """,
            (normalised,),
        )
        total = cur.fetchone()[0]

        cur.execute(
            """
            WITH ranked AS (
                SELECT p.id, p.s3_key,
                       COUNT(CASE WHEN t.name = ANY(%s) THEN 1 END) AS match_count,
                       array_agg(t.name ORDER BY t.name) AS tags
                FROM photos p
                JOIN photo_tags pt ON pt.photo_id = p.id AND pt.removed_at IS NULL
                JOIN tags t        ON t.id = pt.tag_id
                WHERE p.archived_at IS NULL
                GROUP BY p.id, p.s3_key
                HAVING COUNT(CASE WHEN t.name = ANY(%s) THEN 1 END) > 0
            )
            SELECT id, s3_key, match_count, tags FROM ranked
            WHERE %s IS NULL
               OR match_count < %s
               OR (match_count = %s AND id > %s)
            ORDER BY match_count DESC, id ASC
            LIMIT %s
            """,
            (normalised, normalised, cursor_id, cursor_mc, cursor_mc, cursor_id, limit + 1),
        )
        rows = cur.fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]
    last = rows[-1] if (has_more and rows) else None
    next_cursor = _encode_cursor(last[2], last[0]) if last else None

    items = []
    for row_id, key, _match_count, row_tags in rows:
        entry = {"s3_key": key, "match_count": _match_count, "tags": row_tags}
        if s3_client and bucket:
            entry["url"] = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=_PRESIGNED_URL_EXPIRY,
            )
        if thumbnail_bucket:
            entry["thumbnail_url"] = _thumbnail_url(key, thumbnail_bucket)
        items.append(entry)

    return {"items": items, "next_cursor": next_cursor, "total": total}
