#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-phototagger-db}"
DB_USER="${DB_USER:-postgres}"
DB_NAME="${DB_NAME:-phototagger}"

read -p "Drop all tables in ${DB_NAME}? [y/N] " confirm
[ "$confirm" = "y" ] || exit 0

docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -c \
    "DROP TABLE IF EXISTS photo_tags, schema_migrations, photos, tags CASCADE;"

echo "All tables dropped."
