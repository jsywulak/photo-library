#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-phototagger-db}"

if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null)" = "true" ]; then
    echo "$CONTAINER_NAME is already running."
    exit 0
fi

if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    echo "Removing stopped container $CONTAINER_NAME..."
    docker rm "$CONTAINER_NAME"
fi

docker run -d \
    --name "$CONTAINER_NAME" \
    -e POSTGRES_PASSWORD="${DB_PASSWORD}" \
    -e POSTGRES_DB="${DB_NAME}" \
    -e POSTGRES_USER="${DB_USER}" \
    -p "${DB_PORT}":5432 \
    postgres:16
