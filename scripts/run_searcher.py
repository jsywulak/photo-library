#!/usr/bin/env python3
"""Run the photo searcher against the database and print ranked results."""

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

sys.path.insert(0, str(Path(__file__).parents[1] / "lambda"))
import searcher

TAGS = [
    "floral",
    "marigold",
    "mandap",
    "purple"
]

conn = psycopg2.connect(os.environ["DATABASE_URL"])
try:
    results = searcher.search(TAGS, conn)
    if not results:
        print("No results found.")
    else:
        print(f"{'s3_key':<40} matches")
        print("-" * 50)
        for r in results:
            print(f"{r['s3_key']:<40} {r['match_count']}")
finally:
    conn.close()
