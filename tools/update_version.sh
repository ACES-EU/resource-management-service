#!/bin/bash

set -euo pipefail

APP_NAME="resource-management-service"
VERSION_TAG="$(cat ./VERSION)"

# Validate the version format (e.g., 1.2.3)
if [[ ! "$VERSION_TAG" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid version format. Use semantic versioning (e.g., 1.2.3)."
  exit 1
fi

echo "Version tag '$VERSION_TAG' is valid."

sed -i "s/^version: .*/version: \"$VERSION_TAG\"/" charts/$APP_NAME/Chart.yaml
echo "Updated Chart.yaml version to $VERSION_TAG"