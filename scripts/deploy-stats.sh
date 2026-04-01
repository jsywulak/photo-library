#!/usr/bin/env bash
set -euo pipefail

aws s3 cp dist/stats.zip "s3://${DEPLOYMENT_BUCKET}/stats.zip"

aws cloudformation deploy \
  --stack-name "${STACK_NAME}-stats" \
  --template-file infra/stats-lambda.yaml \
  --parameter-overrides \
    DeploymentBucket="${DEPLOYMENT_BUCKET}" \
    NeonDatabaseUrl="${NEON_DATABASE_URL}" \
    ApiKey="${API_KEY}" \
    InboxBucket="${INBOX_BUCKET}" \
    PhotosBucket="${S3_BUCKET}" \
    ThumbnailBucket="${THUMBNAIL_BUCKET}" \
    FrontendDomain="${FRONTEND_DOMAIN}" \
  --capabilities CAPABILITY_IAM

# Push the new code to Lambda (CloudFormation doesn't detect S3 object changes)
FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}-stats" \
  --query "Stacks[0].Outputs[?OutputKey=='StatsFunctionName'].OutputValue" \
  --output text)

echo "Updating Lambda function code: ${FUNCTION_NAME}"
aws lambda update-function-code \
  --function-name "${FUNCTION_NAME}" \
  --s3-bucket "${DEPLOYMENT_BUCKET}" \
  --s3-key stats.zip \
  --output text \
  --query 'LastModified' | cat
