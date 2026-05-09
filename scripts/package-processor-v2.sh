#!/usr/bin/env bash
set -euo pipefail

BUILD_DIR=$(mktemp -d)
trap 'rm -rf "$BUILD_DIR"' EXIT
mkdir -p dist

echo "Installing dependencies..."
pip install -r requirements-processor-v2-lambda.txt \
  --target "$BUILD_DIR" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --quiet

echo "Copying Lambda code..."
cp lambda/handler.py lambda/processor.py lambda/utils.py lambda/exif.py "$BUILD_DIR"

echo "Zipping..."
(cd "$BUILD_DIR" && zip -qr - . ) > dist/processor-v2.zip

rm -rf "$BUILD_DIR"
echo "Built dist/processor-v2.zip ($(du -h dist/processor-v2.zip | cut -f1))"
