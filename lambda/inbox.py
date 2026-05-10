"""
inbox.py — inbox management logic.

Handles listing, processing, and archiving unprocessed photos in the inbox
S3 bucket. Photos live in the `photos` table with bucket = INBOX_BUCKET.
"""

import base64
import json

from utils import record_event

_PRESIGNED_URL_EXPIRY = 3600  # seconds
_INBOX_PAGE_SIZE = 50


def _encode_cursor(captured_at, row_id: int) -> str:
    """Encode (captured_at, id) as an opaque URL-safe base64 JSON cursor.

    Padding (=) is stripped so the value is safe in query strings without
    percent-encoding. _decode_cursor re-adds padding before decoding.
    """
    c = captured_at.isoformat() if captured_at is not None else None
    return base64.urlsafe_b64encode(json.dumps({"c": c, "id": row_id}).encode()).decode().rstrip("=")


def _decode_cursor(cursor) -> tuple:
    """Decode cursor → (captured_at_str_or_none, id).

    Accepts the new base64-JSON format or a legacy bare integer (for
    backwards compatibility with any in-flight cursors from before the
    ordering change).
    """
    if cursor is None:
        return None, None
    # Legacy integer cursor
    if isinstance(cursor, int):
        return None, cursor
    try:
        # Re-add stripped padding
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return decoded["c"], decoded["id"]
    except Exception:
        raise ValueError(f"Invalid cursor: {cursor!r}")


def list_inbox(db_conn, s3_client, inbox_bucket: str, thumbnail_bucket: str,
               limit: int = _INBOX_PAGE_SIZE, cursor=None) -> dict:
    cursor_c, cursor_id = _decode_cursor(cursor)

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM photos WHERE bucket = %s AND archived_at IS NULL",
            (inbox_bucket,),
        )
        total = cur.fetchone()[0]
        cur.execute(
            """
            SELECT id, s3_key, captured_at, content_hash FROM photos
            WHERE bucket = %s AND archived_at IS NULL AND (
                %s IS NULL AND %s IS NULL  -- no cursor: first page
                OR (captured_at IS NOT NULL AND %s IS NULL)  -- dated before undated tail
                OR (captured_at = %s AND id > %s)            -- same date, advance by id
                OR (captured_at > %s)                         -- later date
                OR (captured_at IS NULL AND %s IS NULL AND id > %s)  -- both null tail
            )
            ORDER BY captured_at ASC NULLS LAST, id ASC
            LIMIT %s
            """,
            (inbox_bucket,
             cursor_c, cursor_id,
             cursor_c,
             cursor_c, cursor_id,
             cursor_c,
             cursor_c, cursor_id,
             limit + 1),
        )
        rows = cur.fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]
    last = rows[-1] if (has_more and rows) else None
    next_cursor = _encode_cursor(last[2], last[0]) if last else None

    items = []
    for row_id, key, _captured_at, content_hash in rows:
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": inbox_bucket, "Key": key},
            ExpiresIn=_PRESIGNED_URL_EXPIRY,
        )
        items.append({
            "s3_key": key,
            "url": url,
            "thumbnail_url": f"https://{thumbnail_bucket}.s3.amazonaws.com/thumbnails/{content_hash}.webp",
        })
    return {"items": items, "next_cursor": next_cursor, "total": total}


def process_inbox_photo(s3_key: str, db_conn, s3_client, inbox_bucket: str, photos_bucket: str) -> bool:
    """Copy photo from inbox to photos bucket using content hash as the destination key.

    The content_hash stored on the inbox record becomes the permanent S3 key
    in the photos bucket ({hash}.jpg), giving collision-free identity regardless
    of original filename. Returns False if the photo was not found in the DB.
    """
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT id, content_hash FROM photos WHERE s3_key = %s AND bucket = %s",
            (s3_key, inbox_bucket),
        )
        row = cur.fetchone()
        if not row:
            return False
        content_hash = row[1]

    dest_key = f"{content_hash}.jpg"
    s3_client.copy_object(
        CopySource={"Bucket": inbox_bucket, "Key": s3_key},
        Bucket=photos_bucket,
        Key=dest_key,
    )
    s3_client.delete_object(Bucket=inbox_bucket, Key=s3_key)
    with db_conn.cursor() as cur:
        cur.execute("DELETE FROM photos WHERE s3_key = %s AND bucket = %s", (s3_key, inbox_bucket))
        # photo_id intentionally NULL: the row above was just deleted, and a
        # FK photo_id would cascade-delete this audit row. Slice 4 will replace
        # the DELETE+re-INSERT pattern with an in-place UPDATE that preserves id.
        record_event(
            cur, s3_key, inbox_bucket, "promoted", "inbox",
            photo_id=None,
            details={"content_hash": content_hash, "dest_bucket": photos_bucket, "dest_key": dest_key},
        )
    return True


def archive_inbox_photo(s3_key: str, db_conn, inbox_bucket: str) -> bool:
    """Set archived_at on the inbox photo record. Returns False if not found."""
    with db_conn.cursor() as cur:
        cur.execute(
            "UPDATE photos SET archived_at = NOW(), state = 'archived'"
            " WHERE s3_key = %s AND bucket = %s "
            "RETURNING id",
            (s3_key, inbox_bucket),
        )
        row = cur.fetchone()
        if row is None:
            return False
        record_event(cur, s3_key, inbox_bucket, "archived", "inbox", photo_id=row[0])
    return True
