#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${REPO_ROOT}/apps/api"
cp env.example .env
uv run --python 3.11 pytest \
  __tests__/unit/test_jobs_retrieval_contract.py \
  __tests__/unit/test_retrieval_routes.py \
  __tests__/unit/test_graph_routing_routes.py \
  __tests__/unit/test_mcp_query_tool.py \
  __tests__/unit/test_retrieval_migration_layout.py \
  __tests__/unit/test_auth_dependencies.py \
  -q
