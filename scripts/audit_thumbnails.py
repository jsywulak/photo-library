#!/usr/bin/env python3
"""Three-way audit: photos buckets, thumbnail bucket, and DB.

Reports gaps across all three sources:
  - Photos in S3 with no thumbnail (regardless of DB state)
  - Photos in DB with no thumbnail
  - Photos in DB not found in S3
  - Thumbnails with no matching photo in S3 or DB
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from helpers import db_connection, is_valid_image, list_s3_keys, thumbnail_key

load_dotenv(Path(__file__).parents[1] / ".env")

S3_BUCKET = os.environ["S3_BUCKET"]
INBOX_BUCKET = os.environ["INBOX_BUCKET"]
THUMBNAIL_BUCKET = os.environ["THUMBNAIL_BUCKET"]
NEON_DATABASE_URL = os.environ["NEON_DATABASE_URL"]


def main():
    print(f"Listing s3://{S3_BUCKET} ...", flush=True)
    photos_s3 = list_s3_keys(S3_BUCKET, filter_fn=is_valid_image)

    print(f"Listing s3://{INBOX_BUCKET} ...", flush=True)
    inbox_s3 = list_s3_keys(INBOX_BUCKET, filter_fn=is_valid_image)

    print(f"Listing s3://{THUMBNAIL_BUCKET}/thumbnails/ ...", flush=True)
    thumbs = list_s3_keys(THUMBNAIL_BUCKET, prefix="thumbnails/")

    print("Querying DB ...", flush=True)
    with db_connection(NEON_DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT s3_key, bucket FROM photos ORDER BY bucket, s3_key")
            db_rows = cur.fetchall()

    # Key on (s3_key, bucket) — the actual unique constraint since migration 004.
    # The same filename can exist in both buckets independently.
    db_photos = list(db_rows)  # [(s3_key, bucket), ...]
    all_s3 = photos_s3 | inbox_s3
    thumb_stems = {Path(k).stem for k in thumbs}
    all_s3_stems = {Path(k).stem for k in all_s3}

    # ── S3 → thumbnail gap ────────────────────────────────────────────────────
    s3_no_thumb = sorted(k for k in all_s3 if Path(k).stem not in thumb_stems)
    photos_s3_no_thumb = [k for k in s3_no_thumb if k in photos_s3]
    inbox_s3_no_thumb  = [k for k in s3_no_thumb if k in inbox_s3]

    # ── DB → thumbnail gap ────────────────────────────────────────────────────
    db_no_thumb = sorted(
        (s3_key, bucket) for s3_key, bucket in db_photos
        if Path(s3_key).stem not in thumb_stems
    )

    # ── DB → S3 gap (in DB but missing from the corresponding bucket) ─────────
    db_not_in_s3 = sorted(
        (s3_key, bucket) for s3_key, bucket in db_photos
        if s3_key not in (photos_s3 if bucket == S3_BUCKET else inbox_s3)
    )

    # ── Orphaned thumbnails (no matching S3 photo) ────────────────────────────
    orphaned_thumbs = sorted(k for k in thumbs if Path(k).stem not in all_s3_stems)

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print(f"{'=' * 60}")
    print(f"  Photos in S3 (processed):   {len(photos_s3):>6}")
    print(f"  Photos in S3 (inbox):       {len(inbox_s3):>6}")
    print(f"  Total photos in S3:         {len(all_s3):>6}")
    print(f"  Photos in DB:               {len(db_photos):>6}")
    print(f"  Thumbnails in bucket:       {len(thumbs):>6}")
    print(f"{'=' * 60}")
    print(f"  S3 photos missing thumb:    {len(s3_no_thumb):>6}  (processed: {len(photos_s3_no_thumb)}, inbox: {len(inbox_s3_no_thumb)})")
    print(f"  DB photos missing thumb:    {len(db_no_thumb):>6}")
    print(f"  DB photos not in S3:        {len(db_not_in_s3):>6}")
    print(f"  Orphaned thumbnails:        {len(orphaned_thumbs):>6}")
    print()

    if photos_s3_no_thumb:
        print(f"PROCESSED PHOTOS WITH NO THUMBNAIL ({len(photos_s3_no_thumb)}):")
        for key in photos_s3_no_thumb:
            print(f"  {key}")
        print()

    if inbox_s3_no_thumb:
        print(f"INBOX PHOTOS WITH NO THUMBNAIL ({len(inbox_s3_no_thumb)}):")
        for key in inbox_s3_no_thumb:
            print(f"  {key}")
        print()

    if db_not_in_s3:
        print(f"DB RECORDS WITH NO MATCHING S3 OBJECT ({len(db_not_in_s3)}):")
        for s3_key, bucket in db_not_in_s3:
            print(f"  [{bucket}] {s3_key}")
        print()

    if orphaned_thumbs:
        print(f"ORPHANED THUMBNAILS — no matching S3 photo ({len(orphaned_thumbs)}):")
        for key in orphaned_thumbs:
            print(f"  {key}")
        print()

    if not any([s3_no_thumb, db_not_in_s3, orphaned_thumbs]):
        print("All photos have thumbnails and all records are consistent.")


if __name__ == "__main__":
    main()
