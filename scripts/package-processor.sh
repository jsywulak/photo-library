#!/usr/bin/env bash
set -euo pipefail

BUILD_DIR=$(mktemp -d)
mkdir -p dist

echo "Installing dependencies..."
pip install anthropic Pillow psycopg2-binary \
  --target "$BUILD_DIR" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --quiet

echo "Copying Lambda code..."
cp lambda/handler.py lambda/processor.py "$BUILD_DIR"

echo "Zipping..."
(cd "$BUILD_DIR" && zip -qr - . ) > dist/processor.zip

rm -rf "$BUILD_DIR"
echo "Built dist/processor.zip ($(du -h dist/processor.zip | cut -f1))"
