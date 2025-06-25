#!/bin/bash

# Exit on error
set -euo pipefail

# Check for commit message argument
if [ -z "${1:-}" ]; then
  echo "USAGE: $0 \"Your commit message\""
  exit 1
fi

COMMIT_MSG="$1"

# Read version from VERSION file
if [ ! -f VERSION ]; then
  echo "VERSION file not found!"
  exit 1
fi

VERSION_TAG=$(cat VERSION)

# Validate the version format (e.g., 1.2.3)
if [[ ! "$VERSION_TAG" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid version format. Use semantic versioning (e.g., 1.2.3)."
  exit 1
fi

echo "Version tag '$VERSION_TAG' is valid."

tools/perform_tests.sh

# Create commit
git add .
git commit -m "$COMMIT_MSG"

# Create annotated tag
git tag -a "$VERSION_TAG" -m "Release $VERSION_TAG"

# Push commit and tag
git push --follow-tags

echo "Pushed commit and tag $VERSION_TAG"
