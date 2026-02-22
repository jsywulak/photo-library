#!/usr/bin/env python3
"""Orchestrate photo processing: list images, call the processor, print status."""

import os
import sys
from pathlib import Path

import anthropic
import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

sys.path.insert(0, str(Path(__file__).parents[1] / "lambda"))
import processor

location = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parents[1] / "images"
filenames = [f for f in os.listdir(location) if not f.startswith(".")]
total = len(filenames)

print(f"Found {total} images.")

conn = psycopg2.connect(os.environ["DATABASE_URL"])
client = anthropic.Anthropic()
processed = skipped = 0

try:
    for i, filename in enumerate(filenames, 1):
        image_bytes = (location / filename).read_bytes()
        status = processor.process_one(filename, image_bytes, conn, client)
        if status == "skipped":
            skipped += 1
            print(f"[{i}/{total}] Skipped   {filename}")
        else:
            processed += 1
            print(f"[{i}/{total}] Processed {filename}")
    conn.commit()
    print(f"\nDone. Processed: {processed}, skipped: {skipped}.")
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
