#!/usr/bin/env bash
set -euo pipefail

aws s3 cp dist/inbox.zip "s3://${DEPLOYMENT_BUCKET}/inbox.zip"

aws cloudformation deploy \
  --stack-name "${STACK_NAME}-inbox" \
  --template-file infra/inbox-lambda.yaml \
  --parameter-overrides \
    DeploymentBucket="${DEPLOYMENT_BUCKET}" \
    NeonDatabaseUrl="${NEON_DATABASE_URL}" \
    ApiKey="${API_KEY}" \
    PhotosBucket="${S3_BUCKET}" \
    ThumbnailBucket="${THUMBNAIL_BUCKET}" \
    InboxBucket="${INBOX_BUCKET}" \
    FrontendDomain="${FRONTEND_DOMAIN}" \
  --capabilities CAPABILITY_IAM

# Push the new code to Lambda (CloudFormation doesn't detect S3 object changes)
FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}-inbox" \
  --query "Stacks[0].Outputs[?OutputKey=='InboxFunctionName'].OutputValue" \
  --output text)

echo "Updating Lambda function code: ${FUNCTION_NAME}"
aws lambda update-function-code \
  --function-name "${FUNCTION_NAME}" \
  --s3-bucket "${DEPLOYMENT_BUCKET}" \
  --s3-key inbox.zip \
  --output text \
  --query 'LastModified'  | cat
