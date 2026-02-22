#!/usr/bin/env bash
set -euo pipefail

aws s3 cp dist/searcher.zip "s3://${DEPLOYMENT_BUCKET}/searcher.zip"

aws cloudformation deploy \
  --stack-name "${STACK_NAME}-searcher" \
  --template-file infra/searcher.yaml \
  --parameter-overrides \
    DeploymentBucket="${DEPLOYMENT_BUCKET}" \
    NeonDatabaseUrl="${NEON_DATABASE_URL}" \
    ApiKey="${API_KEY}" \
    PhotosBucket="${S3_BUCKET}" \
  --capabilities CAPABILITY_IAM

# Push the new code to Lambda (CloudFormation doesn't detect S3 object changes)
FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}-searcher" \
  --query "Stacks[0].Outputs[?OutputKey=='SearcherFunctionName'].OutputValue" \
  --output text)

echo "Updating Lambda function code: ${FUNCTION_NAME}"
aws lambda update-function-code \
  --function-name "${FUNCTION_NAME}" \
  --s3-bucket "${DEPLOYMENT_BUCKET}" \
  --s3-key searcher.zip \
  --output text \
  --query 'LastModified'
