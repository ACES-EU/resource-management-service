#!/bin/bash

set -euo pipefail

./perform_tests.sh

APP_NAME="resource-management-service"
VERSION_TAG="$(cat ./VERSION)"
IMAGE_REPO="k3d-registry.localhost:50000/$APP_NAME"
NAMESPACE="lake"

# Validate the version format (e.g., 1.2.3)
if [[ ! "$VERSION_TAG" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid version format. Use semantic versioning (e.g., 1.2.3)."
  exit 1
fi

echo "Version tag '$VERSION_TAG' is valid."

sed -i "s/^version: .*/version: \"$VERSION_TAG\"/" charts/$APP_NAME/Chart.yaml
echo "Updated Chart.yaml version to $VERSION_TAG"

echo "Building Docker image..."
docker build -t $IMAGE_REPO:$VERSION_TAG .

echo "Pushing Docker image to local repository..."
docker push $IMAGE_REPO:$VERSION_TAG

if ! kubectl get namespace "$NAMESPACE" > /dev/null 2>&1; then
  echo "Namespace '$NAMESPACE' does not exist. Creating it..."
  kubectl create namespace "$NAMESPACE"
else
  echo "Namespace '$NAMESPACE' already exists."
fi

helm upgrade --install $APP_NAME ./charts/$APP_NAME --set image.repository=$IMAGE_REPO --set image.tag=$VERSION_TAG --version $VERSION_TAG --namespace $NAMESPACE

echo "Done."
