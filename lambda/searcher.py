"""
searcher.py — photo search logic.

search() queries photos that match any of the given tags, ranked by how many
of the searched tags each photo has. Photos with no matching tags are excluded.

Each result includes:
  - url: a presigned S3 URL valid for 1 hour for full-size image display
  - thumbnail_url: a public URL to the WebP thumbnail in the thumbnail bucket
"""

from utils import thumbnail_key as _thumbnail_key

_PRESIGNED_URL_EXPIRY = 3600  # seconds
_DEFAULT_TAG_COUNT = 20
_INBOX_PAGE_SIZE = 50


def _thumbnail_url(s3_key: str, thumbnail_bucket: str) -> str:
    return f"https://{thumbnail_bucket}.s3.amazonaws.com/{_thumbnail_key(s3_key)}"


def list_inbox(db_conn, s3_client, inbox_bucket: str, thumbnail_bucket: str,
               limit: int = _INBOX_PAGE_SIZE, cursor: int | None = None) -> dict:
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM photos WHERE bucket = %s AND archived_at IS NULL",
            (inbox_bucket,),
        )
        total = cur.fetchone()[0]
        cur.execute(
            """
            SELECT id, s3_key FROM photos
            WHERE bucket = %s AND archived_at IS NULL AND (%s IS NULL OR id < %s)
            ORDER BY id DESC LIMIT %s
            """,
            (inbox_bucket, cursor, cursor, limit + 1),
        )
        rows = cur.fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = rows[-1][0] if has_more else None

    items = []
    for row_id, key in rows:
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": inbox_bucket, "Key": key},
            ExpiresIn=_PRESIGNED_URL_EXPIRY,
        )
        items.append({
            "s3_key": key,
            "url": url,
            "thumbnail_url": _thumbnail_url(key, thumbnail_bucket),
        })
    return {"items": items, "next_cursor": next_cursor, "total": total}


def process_inbox_photo(s3_key: str, db_conn, s3_client, inbox_bucket: str, photos_bucket: str) -> bool:
    """Copy photo from inbox to photos bucket, delete from inbox, remove DB record.
    Returns False if the photo was not found in the DB.
    """
    with db_conn.cursor() as cur:
        cur.execute("SELECT id FROM photos WHERE s3_key = %s AND bucket = %s", (s3_key, inbox_bucket))
        if not cur.fetchone():
            return False
    s3_client.copy_object(
        CopySource={"Bucket": inbox_bucket, "Key": s3_key},
        Bucket=photos_bucket,
        Key=s3_key,
    )
    s3_client.delete_object(Bucket=inbox_bucket, Key=s3_key)
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM photos WHERE s3_key = %s AND bucket = %s", (s3_key, inbox_bucket))
    return True


def archive_inbox_photo(s3_key: str, db_conn, inbox_bucket: str) -> bool:
    """Set archived_at on the inbox photo record. Returns False if not found."""
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE photos SET archived_at = NOW() WHERE s3_key = %s AND bucket = %s",
            (s3_key, inbox_bucket),
        )
        return cur.rowcount > 0


def get_random_tags(db_conn, count: int = _DEFAULT_TAG_COUNT) -> list[str]:
    with db_conn.cursor() as cur:
        cur.execute("SELECT name FROM tags ORDER BY RANDOM() LIMIT %s", (count,))
        return [row[0] for row in cur.fetchall()]


def add_tags(s3_key: str, tags: list[str], db_conn) -> int | None:
    """Add tags to a photo, creating them if needed and restoring any that were removed.

    Returns the number of associations added or restored, or None if the photo was not found.
    """
    normalised = [t.strip().lower() for t in tags if t.strip()]
    if not normalised:
        return 0

    with db_conn.cursor() as cur:
        cur.execute("SELECT id FROM photos WHERE s3_key = %s", (s3_key,))
        row = cur.fetchone()
        if not row:
            return None
        photo_id = row[0]

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
            """,
            (s3_key, normalised),
        )
        updated = cur.rowcount
    return updated > 0


def search(tags: list[str], db_conn, s3_client=None, bucket: str = None, thumbnail_bucket: str = None) -> list[dict]:
    normalised = [t.strip().lower() for t in tags]
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.s3_key,
                   COUNT(CASE WHEN t.name = ANY(%s) THEN 1 END) AS match_count,
                   array_agg(t.name ORDER BY t.name) AS tags
            FROM photos p
            JOIN photo_tags pt ON pt.photo_id = p.id AND pt.removed_at IS NULL
            JOIN tags t        ON t.id = pt.tag_id
            GROUP BY p.id, p.s3_key
            HAVING COUNT(CASE WHEN t.name = ANY(%s) THEN 1 END) > 0
            ORDER BY match_count DESC
            """,
            (normalised, normalised),
        )
        rows = cur.fetchall()

    results = []
    for row in rows:
        entry = {"s3_key": row[0], "match_count": row[1], "tags": row[2]}
        if s3_client and bucket:
            entry["url"] = s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": row[0]},
                ExpiresIn=_PRESIGNED_URL_EXPIRY,
            )
        if thumbnail_bucket:
            entry["thumbnail_url"] = _thumbnail_url(row[0], thumbnail_bucket)
        results.append(entry)
    return results
