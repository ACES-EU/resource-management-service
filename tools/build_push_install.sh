#!/bin/bash

set -euo pipefail

./tools/perform_tests.sh

APP_NAME="resource-management-service"
VERSION_TAG="$(cat ./VERSION)"
IMAGE_REPO="k3d-registry.localhost:50000/$APP_NAME"
NAMESPACE="lake"

./tools/update_version.sh

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
