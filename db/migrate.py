#!/usr/bin/env python3
"""Apply pending SQL migrations from db/migrations/ in order."""

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

CREATE_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   TEXT        PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def get_connection(dsn: str):
    return psycopg2.connect(dsn)


def applied_migrations(cur) -> set[str]:
    cur.execute("SELECT filename FROM schema_migrations ORDER BY filename")
    return {row[0] for row in cur.fetchall()}


def migration_files() -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print("No migration files found.")
    return files


def apply(dsn: str) -> None:
    conn = get_connection(dsn)
    try:
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(CREATE_MIGRATIONS_TABLE)
            conn.commit()

            done = applied_migrations(cur)
            pending = [f for f in migration_files() if f.name not in done]

            if not pending:
                print("Nothing to migrate.")
                return

            for path in pending:
                print(f"Applying {path.name} ...", end=" ", flush=True)
                sql = path.read_text()
                cur.execute(sql)
                cur.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)",
                    (path.name,),
                )
                conn.commit()
                print("done")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    load_dotenv(Path(__file__).parent.parent / ".env")
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)
    apply(dsn)
