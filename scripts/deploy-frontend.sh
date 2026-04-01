#!/usr/bin/env bash
set -euo pipefail

aws cloudformation deploy \
  --stack-name "${STACK_NAME}-frontend" \
  --template-file infra/frontend.yaml \
  --parameter-overrides \
    DomainName="${FRONTEND_BUCKET}" \
    HostedZoneId="${HOSTED_ZONE_ID}"

BUCKET_NAME="${FRONTEND_BUCKET}"

echo "Uploading frontend to s3://${BUCKET_NAME}/"
aws s3 cp frontend/index.html "s3://${BUCKET_NAME}/index.html" --content-type text/html
aws s3 cp frontend/inbox.html "s3://${BUCKET_NAME}/inbox"      --content-type text/html
aws s3 cp frontend/stats.html "s3://${BUCKET_NAME}/stats"      --content-type text/html
aws s3 cp frontend/config.js  "s3://${BUCKET_NAME}/config.js"  --content-type application/javascript

echo "Deployed: ${FRONTEND_DOMAIN}"
