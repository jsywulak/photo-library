#!/usr/bin/env bash
set -euo pipefail

aws cloudformation deploy \
  --stack-name "${STACK_NAME}-inbox" \
  --template-file infra/inbox-bucket.yaml \
  --parameter-overrides \
    InboxBucketName="${INBOX_BUCKET}"
