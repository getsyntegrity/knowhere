#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${REPO_ROOT}/scripts/test-public-shared.sh"
"${REPO_ROOT}/scripts/test-public-api.sh"
"${REPO_ROOT}/scripts/test-public-worker.sh"
