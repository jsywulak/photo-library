"""
stats.py — Core logic for the stats Lambda.

Returns counts and data-integrity metrics for the stats dashboard.
"""

from pathlib import Path


def get_stats(db_conn, s3_client, inbox_bucket, photos_bucket, thumbnail_bucket):
    """Return a dict of all stats metrics."""
    inbox_count = count_db_photos(db_conn, inbox_bucket)
    db_count = count_db_photos(db_conn, photos_bucket)
    archived_count = count_archived_photos(db_conn, inbox_bucket)
    total_photos = inbox_count + db_count + archived_count

    inbox_s3_count = count_s3_objects(s3_client, inbox_bucket)
    processed_s3_count = count_s3_objects(s3_client, photos_bucket)
    thumbnail_count = count_s3_objects(s3_client, thumbnail_bucket, prefix="thumbnails/")

    orphaned_thumbnails = count_orphaned_thumbnails(db_conn, s3_client, thumbnail_bucket)
    orphaned_processed = count_orphaned_processed(db_conn, s3_client, photos_bucket)
    orphaned_inbox = count_orphaned_inbox(db_conn, s3_client, inbox_bucket)

    top_tags = get_top_tags(db_conn)

    return {
        "inbox_count": inbox_count,
        "photos_count": processed_s3_count,  # kept for backwards compat
        "db_count": db_count,
        "archived_count": archived_count,
        "total_photos": total_photos,
        "inbox_s3_count": inbox_s3_count,
        "processed_s3_count": processed_s3_count,
        "thumbnail_count": thumbnail_count,
        "orphaned_thumbnails": orphaned_thumbnails,
        "orphaned_processed": orphaned_processed,
        "orphaned_inbox": orphaned_inbox,
        "top_tags": top_tags,
    }


def count_s3_objects(s3_client, bucket, prefix=""):
    paginator = s3_client.get_paginator("list_objects_v2")
    kwargs = {"Bucket": bucket}
    if prefix:
        kwargs["Prefix"] = prefix
    total = 0
    for page in paginator.paginate(**kwargs):
        total += page.get("KeyCount", 0)
    return total


def count_db_photos(db_conn, bucket):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM photos WHERE bucket = %s AND archived_at IS NULL",
            (bucket,),
        )
        return cur.fetchone()[0]


def count_archived_photos(db_conn, inbox_bucket):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM photos WHERE bucket = %s AND archived_at IS NOT NULL",
            (inbox_bucket,),
        )
        return cur.fetchone()[0]


def count_orphaned_thumbnails(db_conn, s3_client, thumbnail_bucket):
    with db_conn.cursor() as cur:
        cur.execute("SELECT content_hash FROM photos WHERE content_hash IS NOT NULL")
        known_hashes = {row[0] for row in cur.fetchall()}

    paginator = s3_client.get_paginator("list_objects_v2")
    orphaned = 0
    for page in paginator.paginate(Bucket=thumbnail_bucket, Prefix="thumbnails/"):
        for obj in page.get("Contents", []):
            stem = Path(obj["Key"]).stem
            if stem not in known_hashes:
                orphaned += 1
    return orphaned


def count_orphaned_processed(db_conn, s3_client, photos_bucket):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT content_hash FROM photos WHERE bucket = %s AND content_hash IS NOT NULL",
            (photos_bucket,),
        )
        known_hashes = {row[0] for row in cur.fetchall()}

    paginator = s3_client.get_paginator("list_objects_v2")
    orphaned = 0
    for page in paginator.paginate(Bucket=photos_bucket):
        for obj in page.get("Contents", []):
            stem = Path(obj["Key"]).stem
            if stem not in known_hashes:
                orphaned += 1
    return orphaned


def count_orphaned_inbox(db_conn, s3_client, inbox_bucket):
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT s3_key FROM photos WHERE bucket = %s",
            (inbox_bucket,),
        )
        known_keys = {row[0] for row in cur.fetchall()}

    paginator = s3_client.get_paginator("list_objects_v2")
    orphaned = 0
    for page in paginator.paginate(Bucket=inbox_bucket):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.lower().endswith((".jpg", ".jpeg")):
                continue
            if key not in known_keys:
                orphaned += 1
    return orphaned


def check_inbox_count_mismatch(db_conn, s3_client, inbox_bucket):
    s3_count = count_s3_objects(s3_client, inbox_bucket)
    db_total = count_db_photos(db_conn, inbox_bucket) + count_archived_photos(db_conn, inbox_bucket)
    return {"s3_count": s3_count, "db_count": db_total}


def get_top_tags(db_conn):
    with db_conn.cursor() as cur:
        cur.execute("""
            SELECT t.name, COUNT(pt.photo_id) AS photo_count
            FROM tags t
            JOIN photo_tags pt ON pt.tag_id = t.id
            GROUP BY t.name
            ORDER BY photo_count DESC, t.name
            LIMIT 5
        """)
        return [{"name": row[0], "count": row[1]} for row in cur.fetchall()]
