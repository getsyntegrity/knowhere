#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${REPO_ROOT}/apps/api"
uv run --python 3.11 pyright \
  app/api/v1/routes/retrieval.py \
  app/api/v1/routes/qstash_callbacks.py \
  app/api/v1/routes/documents.py \
  app/api/v1/routes/api_key.py \
  app/core/dependencies.py \
  app/api/api_router.py
