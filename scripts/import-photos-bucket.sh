#!/usr/bin/env bash
set -euo pipefail

STACK_NAME="photo-tagging-photos"
BUCKET_NAME="photo-tagging-photos"
CHANGE_SET_NAME="import-photos-bucket"

echo "Creating import change set..."
aws cloudformation create-change-set \
  --stack-name "${STACK_NAME}" \
  --change-set-name "${CHANGE_SET_NAME}" \
  --change-set-type IMPORT \
  --template-body file://infra/photos-bucket.yaml \
  --parameters ParameterKey=PhotosBucketName,ParameterValue="${BUCKET_NAME}" \
  --resources-to-import "[{\"ResourceType\":\"AWS::S3::Bucket\",\"LogicalResourceId\":\"PhotosBucket\",\"ResourceIdentifier\":{\"BucketName\":\"${BUCKET_NAME}\"}}]"

echo "Waiting for change set to be created..."
aws cloudformation wait change-set-create-complete \
  --stack-name "${STACK_NAME}" \
  --change-set-name "${CHANGE_SET_NAME}"

echo "Executing import change set..."
aws cloudformation execute-change-set \
  --stack-name "${STACK_NAME}" \
  --change-set-name "${CHANGE_SET_NAME}"

echo "Waiting for import to complete..."
aws cloudformation wait stack-import-complete \
  --stack-name "${STACK_NAME}"

echo "Import complete."
aws cloudformation list-stack-resources \
  --stack-name "${STACK_NAME}" \
  --query 'StackResourceSummaries[*].{Type:ResourceType,LogicalId:LogicalResourceId,Status:ResourceStatus}' \
  --output table
