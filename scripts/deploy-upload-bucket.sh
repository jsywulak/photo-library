#!/usr/bin/env bash
set -euo pipefail

aws cloudformation deploy \
  --stack-name "${STACK_NAME}-upload-bucket" \
  --template-file infra/upload-bucket.yaml \
  --parameter-overrides \
    UploadBucketName="${UPLOAD_BUCKET}"
