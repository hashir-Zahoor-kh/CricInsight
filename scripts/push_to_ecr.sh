#!/usr/bin/env bash
# Build the backend Docker image and push it to ECR.
# Creates the repository if it does not exist.
#
# Required env vars:
#   AWS_ACCOUNT_ID   — 12-digit AWS account number
#   AWS_REGION       — e.g. us-east-1
#
# Optional:
#   IMAGE_TAG        — defaults to "latest"
set -euo pipefail

: "${AWS_ACCOUNT_ID:?AWS_ACCOUNT_ID must be set}"
: "${AWS_REGION:?AWS_REGION must be set}"

REPO_NAME="cricinsight-backend"
IMAGE_TAG="${IMAGE_TAG:-latest}"
REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_URI="${REGISTRY}/${REPO_NAME}"

echo "→ Authenticating with ECR..."
aws ecr get-login-password --region "$AWS_REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"

echo "→ Ensuring ECR repository exists..."
aws ecr describe-repositories \
    --repository-names "$REPO_NAME" \
    --region "$AWS_REGION" \
    > /dev/null 2>&1 \
  || aws ecr create-repository \
       --repository-name "$REPO_NAME" \
       --region "$AWS_REGION" \
       --image-scanning-configuration scanOnPush=true \
       > /dev/null

echo "→ Building image (tag: ${IMAGE_TAG})..."
# Run from repo root so the build context is backend/
docker build \
  --tag "${REPO_NAME}:${IMAGE_TAG}" \
  --file backend/Dockerfile \
  backend/

echo "→ Tagging for ECR..."
docker tag "${REPO_NAME}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"

echo "→ Pushing to ECR..."
docker push "${ECR_URI}:${IMAGE_TAG}"

echo "✓ Pushed ${ECR_URI}:${IMAGE_TAG}"
