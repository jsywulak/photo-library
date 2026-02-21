#!/usr/bin/env python3
"""Run the photo processor against a local directory and commit the results."""

import os
import sys
from pathlib import Path

import anthropic
import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

sys.path.insert(0, str(Path(__file__).parents[1] / "lambda"))
import processor

location = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parents[1] / "images")

conn = psycopg2.connect(os.environ["DATABASE_URL"])
try:
    result = processor.process(location, conn, anthropic.Anthropic())
    conn.commit()
    print(f"discovered: {result['discovered']}")
    print(f"processed:  {result['processed']}")
    print(f"skipped:    {result['skipped']}")
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
