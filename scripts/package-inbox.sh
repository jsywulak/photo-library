#!/usr/bin/env bash
set -euo pipefail

BUILD_DIR=$(mktemp -d)
trap 'rm -rf "$BUILD_DIR"' EXIT
mkdir -p dist

echo "Installing dependencies..."
pip install -r requirements-inbox-lambda.txt \
  --target "$BUILD_DIR" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --quiet

echo "Copying Lambda code..."
cp lambda/inbox_handler.py lambda/inbox.py lambda/utils.py "$BUILD_DIR"

echo "Zipping..."
(cd "$BUILD_DIR" && zip -qr - . ) > dist/inbox.zip

rm -rf "$BUILD_DIR"
echo "Built dist/inbox.zip ($(du -h dist/inbox.zip | cut -f1))"
