#!/bin/bash

# Usage: ./delete-si-test.sh <namespace>

set -e

NAMESPACE="$1"

if [[ -z "$NAMESPACE" ]]; then
  echo "Usage: $0 <namespace>"
  exit 1
fi

# Get deployments containing "si-test"
DEPLOYMENTS=$(kubectl get deployments -n "$NAMESPACE" \
  --no-headers \
  | grep si-test \
  | awk '{print $1}')

if [[ -z "$DEPLOYMENTS" ]]; then
  echo "No si-test deployments found in namespace '$NAMESPACE'."
  exit 0
fi

echo "Deleting deployments in namespace '$NAMESPACE':"
echo "$DEPLOYMENTS"

kubectl delete deployment -n "$NAMESPACE" $DEPLOYMENTS
