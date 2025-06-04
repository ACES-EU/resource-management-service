#!/bin/bash

set -euo pipefail

echo "Performing tests..."
poetry run mypy .
poetry run isort . --check --diff
poetry run flake8 .
poetry run black . --check --diff
poetry run pytest
echo "Tests successfull..."
