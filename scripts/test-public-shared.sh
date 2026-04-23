#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${REPO_ROOT}/packages/shared-python"
uv run --python 3.11 pytest \
  shared/tests/test_retrieval_publication_sync.py \
  shared/tests/test_retrieval_cache_service.py \
  shared/tests/test_retrieval_app_service.py \
  shared/tests/test_graph_publication_sync.py \
  shared/tests/test_retrieval_hit_stats.py \
  -q
