#!/usr/bin/env bash
set -euo pipefail

aws cloudformation deploy \
  --stack-name "${STACK_NAME}-frontend" \
  --template-file infra/frontend.yaml \
  --parameter-overrides \
    DomainName="${FRONTEND_DOMAIN}" \
    HostedZoneId="${HOSTED_ZONE_ID}"

BUCKET_NAME=$(aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}-frontend" \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" \
  --output text)

echo "Uploading frontend to s3://${BUCKET_NAME}/"
aws s3 cp frontend/index.html "s3://${BUCKET_NAME}/index.html" --content-type text/html
aws s3 cp frontend/config.js  "s3://${BUCKET_NAME}/config.js"  --content-type application/javascript

echo "Deployed: http://${FRONTEND_DOMAIN}"
