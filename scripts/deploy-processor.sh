#!/usr/bin/env bash
set -euo pipefail

aws s3 cp dist/processor.zip "s3://${DEPLOYMENT_BUCKET}/processor.zip"

aws cloudformation deploy \
  --stack-name "${STACK_NAME}" \
  --template-file infra/processor.yaml \
  --parameter-overrides \
    DeploymentBucket="${DEPLOYMENT_BUCKET}" \
    NeonDatabaseUrl="${NEON_DATABASE_URL}" \
    AnthropicApiKey="${ANTHROPIC_API_KEY}" \
  --capabilities CAPABILITY_IAM

# Push the new code to Lambda (CloudFormation doesn't detect S3 object changes)
FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name "${STACK_NAME}" \
  --query "Stacks[0].Outputs[?OutputKey=='ProcessorFunctionName'].OutputValue" \
  --output text)

echo "Updating Lambda function code: ${FUNCTION_NAME}"
aws lambda update-function-code \
  --function-name "${FUNCTION_NAME}" \
  --s3-bucket "${DEPLOYMENT_BUCKET}" \
  --s3-key processor.zip \
  --output text \
  --query 'LastModified'
