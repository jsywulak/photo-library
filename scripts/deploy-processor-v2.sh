#!/usr/bin/env bash
set -euo pipefail

aws s3 cp dist/processor-v2.zip "s3://${DEPLOYMENT_BUCKET}/processor-v2.zip"

aws cloudformation deploy \
  --stack-name "${STACK_NAME}-processor-v2" \
  --template-file infra/processor-v2.yaml \
  --parameter-overrides \
    DeploymentBucket="${DEPLOYMENT_BUCKET}" \
    NeonDatabaseUrl="${NEON_DATABASE_URL}" \
    AnthropicApiKey="${ANTHROPIC_API_KEY}" \
    PhotosBucket="${S3_BUCKET}" \
    InboxBucket="${INBOX_BUCKET}" \
  --capabilities CAPABILITY_IAM

# Push the new code to Lambda (CloudFormation doesn't detect S3 object changes)
FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}-processor-v2" \
  --query "Stacks[0].Outputs[?OutputKey=='ProcessorV2FunctionName'].OutputValue" \
  --output text)

echo "Updating Lambda function code: ${FUNCTION_NAME}"
aws lambda update-function-code \
  --function-name "${FUNCTION_NAME}" \
  --s3-bucket "${DEPLOYMENT_BUCKET}" \
  --s3-key processor-v2.zip \
  --output text \
  --query 'LastModified'
