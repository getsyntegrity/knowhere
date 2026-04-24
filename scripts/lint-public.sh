#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYPROJECT_PATH="${REPO_ROOT}/packages/shared-python/pyproject.toml"

LINT_PATHS=(
  "${REPO_ROOT}/apps/api/app"
  "${REPO_ROOT}/apps/worker/app"
  "${REPO_ROOT}/packages/shared-python/shared"
  "${REPO_ROOT}/packages/shared-python/shared/tests"
)

uv tool run --python 3.11 isort \
  --settings-path "${PYPROJECT_PATH}" \
  --check-only \
  "${LINT_PATHS[@]}"

uv tool run --python 3.11 black \
  --config "${PYPROJECT_PATH}" \
  --check \
  "${LINT_PATHS[@]}"
