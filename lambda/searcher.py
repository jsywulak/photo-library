"""
searcher.py — photo search logic.

search() queries photos that match any of the given tags, ranked by how many
of the searched tags each photo has. Photos with no matching tags are excluded.

Each result includes:
  - url: a presigned S3 URL valid for 1 hour for full-size image display
  - thumbnail_url: a public URL to the WebP thumbnail in the thumbnail bucket
"""

from thumbnailer import thumbnail_key as _thumbnail_key

_PRESIGNED_URL_EXPIRY = 3600  # seconds
_DEFAULT_TAG_COUNT = 20


def _thumbnail_url(s3_key: str, thumbnail_bucket: str) -> str:
    return f"https://{thumbnail_bucket}.s3.amazonaws.com/{_thumbnail_key(s3_key)}"


def list_inbox(db_conn, s3_client, inbox_bucket: str, thumbnail_bucket: str) -> list[dict]:
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT s3_key FROM photos WHERE bucket = %s ORDER BY id DESC",
            (inbox_bucket,),
        )
        keys = [row[0] for row in cur.fetchall()]

    results = []
    for key in keys:
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": inbox_bucket, "Key": key},
            ExpiresIn=_PRESIGNED_URL_EXPIRY,
        )
        results.append({
            "s3_key": key,
            "url": url,
            "thumbnail_url": _thumbnail_url(key, thumbnail_bucket),
        })
    return results


def get_random_tags(db_conn, count: int = _DEFAULT_TAG_COUNT) -> list[str]:
    with db_conn.cursor() as cur:
        cur.execute("SELECT name FROM tags ORDER BY RANDOM() LIMIT %s", (count,))
        return [row[0] for row in cur.fetchall()]


def search(tags: list[str], db_conn, s3_client=None, bucket: str = None, thumbnail_bucket: str = None) -> list[dict]:
    normalised = [t.strip().lower() for t in tags]
    with db_conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.s3_key, COUNT(pt.tag_id) AS match_count
            FROM photos p
            JOIN photo_tags pt ON pt.photo_id = p.id
            JOIN tags t        ON t.id = pt.tag_id
            WHERE t.name = ANY(%s)
            GROUP BY p.id, p.s3_key
            ORDER BY match_count DESC
            """,
            (normalised,),
        )
        rows = cur.fetchall()

    results = []
    for row in rows:
        entry = {"s3_key": row[0], "match_count": row[1]}
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
