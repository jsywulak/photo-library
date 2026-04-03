#!/usr/bin/env bash
set -euo pipefail

BUILD_DIR=$(mktemp -d)
trap 'rm -rf "$BUILD_DIR"' EXIT
mkdir -p dist

echo "Installing dependencies..."
pip install -r requirements-image-lambda.txt \
  --target "$BUILD_DIR" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --quiet

echo "Copying Lambda code..."
cp lambda/image_handler.py lambda/thumbnailer.py lambda/utils.py "$BUILD_DIR"

echo "Zipping..."
(cd "$BUILD_DIR" && zip -qr - . ) > dist/image.zip

rm -rf "$BUILD_DIR"
echo "Built dist/image.zip ($(du -h dist/image.zip | cut -f1))"
