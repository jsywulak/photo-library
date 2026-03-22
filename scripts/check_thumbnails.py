#!/usr/bin/env python3
"""Report thumbnail coverage: missing thumbnails and orphaned thumbnails.

  Missing  — photos in the DB with no corresponding thumbnail in S3.
  Orphaned — thumbnails in S3 with no corresponding photo in the DB.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from helpers import db_connection, list_s3_keys, thumbnail_key

load_dotenv(Path(__file__).parents[1] / ".env")

NEON_DATABASE_URL = os.environ["NEON_DATABASE_URL"]
THUMBNAIL_BUCKET = os.environ["THUMBNAIL_BUCKET"]


def list_db_photos(conn) -> list[tuple[str, str]]:
    """Return list of (s3_key, bucket) for all tracked photos."""
    with conn.cursor() as cur:
        cur.execute("SELECT s3_key, bucket FROM photos ORDER BY bucket, s3_key")
        return cur.fetchall()


def main():
    print(f"Listing thumbnails in s3://{THUMBNAIL_BUCKET} ...", flush=True)
    existing_thumbs = list_s3_keys(THUMBNAIL_BUCKET, prefix="thumbnails/")

    print("Querying DB ...", flush=True)
    with db_connection(NEON_DATABASE_URL) as conn:
        photos = list_db_photos(conn)

    # Photos missing a thumbnail
    missing = [
        (s3_key, bucket)
        for s3_key, bucket in photos
        if thumbnail_key(s3_key) not in existing_thumbs
    ]

    # Thumbnails with no matching photo (matched by stem)
    known_stems = {Path(s3_key).stem for s3_key, _ in photos}
    orphaned = sorted(
        key for key in existing_thumbs
        if Path(key).stem not in known_stems
    )

    print()
    print(f"Total photos in DB:    {len(photos):>6}")
    print(f"Thumbnails in bucket:  {len(existing_thumbs):>6}")
    print(f"Missing thumbnails:    {len(missing):>6}")
    print(f"Orphaned thumbnails:   {len(orphaned):>6}")

    if missing:
        print()
        print("MISSING THUMBNAILS:")
        for s3_key, bucket in missing:
            print(f"  [{bucket}] {s3_key}")
        print("Run `make backfill-thumbnails` or `make backfill-inbox-thumbnails` to fix.")

    if orphaned:
        print()
        print("ORPHANED THUMBNAILS (no matching photo in DB):")
        for key in orphaned:
            print(f"  {key}")
        print("Run `make neon-clean-thumbnail-orphans` to delete them.")


if __name__ == "__main__":
    main()
