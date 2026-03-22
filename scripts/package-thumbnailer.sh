#!/usr/bin/env bash
set -euo pipefail

BUILD_DIR=$(mktemp -d)
trap 'rm -rf "$BUILD_DIR"' EXIT
mkdir -p dist

echo "Installing dependencies..."
pip install -r requirements-thumbnailer-lambda.txt \
  --target "$BUILD_DIR" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --quiet

echo "Copying Lambda code..."
cp lambda/thumbnailer.py lambda/thumbnailer_handler.py lambda/utils.py "$BUILD_DIR"

echo "Zipping..."
(cd "$BUILD_DIR" && zip -qr - . ) > dist/thumbnailer.zip

rm -rf "$BUILD_DIR"
echo "Built dist/thumbnailer.zip ($(du -h dist/thumbnailer.zip | cut -f1))"
