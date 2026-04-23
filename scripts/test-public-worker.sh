#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${REPO_ROOT}/apps/worker"
cp env.example .env
uv run --python 3.11 pytest tests/tasks/test_kb_tasks.py -q
