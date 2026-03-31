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


def _thumbnail_url(s3_key: str, thumbnail_bucket: str) -> str:
    return f"https://{thumbnail_bucket}.s3.amazonaws.com/{_thumbnail_key(s3_key)}"


def _normalise_tags(tags: list[str]) -> list[str]:
    return [t.strip().lower() for t in tags if t.strip()]


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


_DEFAULT_SEARCH_LIMIT = 200


def search(tags: list[str], db_conn, s3_client=None, bucket: str = None, thumbnail_bucket: str = None, limit: int = _DEFAULT_SEARCH_LIMIT) -> list[dict]:
    normalised = _normalise_tags(tags)
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
            LIMIT %s
            """,
            (normalised, normalised, limit),
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
