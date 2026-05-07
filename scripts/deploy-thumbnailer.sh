#!/usr/bin/env bash
set -euo pipefail

aws s3 cp dist/thumbnailer.zip "s3://${DEPLOYMENT_BUCKET}/thumbnailer.zip"

aws cloudformation deploy \
  --stack-name "${STACK_NAME}-thumbnailer" \
  --template-file infra/thumbnailer.yaml \
  --parameter-overrides \
    DeploymentBucket="${DEPLOYMENT_BUCKET}" \
    PhotosBucket="${S3_BUCKET}" \
    InboxBucket="${INBOX_BUCKET}" \
    NeonDatabaseUrl="${NEON_DATABASE_URL}" \
  --capabilities CAPABILITY_IAM

# Push the new code to Lambda (CloudFormation doesn't detect S3 object changes)
FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}-thumbnailer" \
  --query "Stacks[0].Outputs[?OutputKey=='ThumbnailerFunctionName'].OutputValue" \
  --output text)

echo "Updating Lambda function code: ${FUNCTION_NAME}"
aws lambda update-function-code \
  --function-name "${FUNCTION_NAME}" \
  --s3-bucket "${DEPLOYMENT_BUCKET}" \
  --s3-key thumbnailer.zip \
  --output text \
  --query 'LastModified'
