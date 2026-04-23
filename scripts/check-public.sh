#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${REPO_ROOT}/scripts/scan-public-safety.sh"
"${REPO_ROOT}/scripts/typecheck-public.sh"
"${REPO_ROOT}/scripts/test-public.sh"
