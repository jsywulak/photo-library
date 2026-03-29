#!/usr/bin/env python3
"""Look up the database status of a photo by filename.

Usage:
    python scripts/photo_status.py 2Q4A8707
    python scripts/photo_status.py 2Q4A8707.JPG
"""

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

if len(sys.argv) != 2:
    print("Usage: python scripts/photo_status.py <filename>")
    sys.exit(1)

query = sys.argv[1]

conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
try:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.id, p.s3_key, p.bucket, p.processed_at, p.archived_at, p.last_error,
                   array_agg(t.name ORDER BY t.name)
                       FILTER (WHERE t.name IS NOT NULL AND pt.removed_at IS NULL) AS tags
            FROM photos p
            LEFT JOIN photo_tags pt ON pt.photo_id = p.id
            LEFT JOIN tags t        ON t.id = pt.tag_id
            WHERE p.s3_key ILIKE %s
            GROUP BY p.id, p.s3_key, p.bucket, p.processed_at, p.archived_at, p.last_error
            ORDER BY p.bucket, p.id
            """,
            (f"%{query}%",),
        )
        rows = cur.fetchall()
finally:
    conn.close()

if not rows:
    print(f"No records found for '{query}'.")
    sys.exit(0)

for row in rows:
    id_, s3_key, bucket, processed_at, archived_at, last_error, tags = row
    print(f"s3_key:       {s3_key}")
    print(f"bucket:       {bucket}")
    print(f"id:           {id_}")
    print(f"processed_at: {processed_at or '—'}")
    print(f"archived_at:  {archived_at or '—'}")
    print(f"last_error:   {last_error or '—'}")
    print(f"tags ({len(tags) if tags else 0}): {', '.join(tags) if tags else '—'}")
    print()
