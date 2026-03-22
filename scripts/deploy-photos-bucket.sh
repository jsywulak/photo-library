#!/usr/bin/env bash
set -euo pipefail

aws cloudformation deploy \
  --stack-name "${STACK_NAME}-photos" \
  --template-file infra/photos-bucket.yaml \
  --parameter-overrides \
    PhotosBucketName="${S3_BUCKET}"
