#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${REPO_ROOT}"

SCAN_PATHS=(
  README.md
  LICENSE
  NOTICE
  CONTRIBUTING.md
  SECURITY.md
  CODE_OF_CONDUCT.md
  pyproject.toml
  docs
  .github
  apps
  packages/shared-python
  deploy
  scripts
)

RG_EXCLUDES=(
  --glob=!**/uv.lock
  --glob=!**/requirements.txt
  --glob=!**/__pycache__/**
  --glob=!**/tests/**
  --glob=!**/__tests__/**
)

run_pattern_scan() {
  local description="$1"
  local pattern="$2"

  if rg -n --pcre2 --color=never "${RG_EXCLUDES[@]}" "${pattern}" "${SCAN_PATHS[@]}"; then
    echo "Public safety scan failed: ${description}" >&2
    exit 1
  fi
}

if [ -d "${REPO_ROOT}/apps/api/alembic/versions_archive_20260305" ]; then
  echo "Public safety scan failed: remove apps/api/alembic/versions_archive_20260305 from the publication branch" >&2
  exit 1
fi

run_pattern_scan \
  "patch markers leaked into tracked files" \
  "\\*\\*\\* Add File:|\\*\\*\\* Update File:|\\*\\*\\* Delete File:|\\*\\*\\* Begin Patch|\\*\\*\\* End Patch"
run_pattern_scan \
  "credential-like material" \
  "github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}"
run_pattern_scan \
  "private placeholder domains or emails" \
  "dev-placeholder@knowhere\\.internal|knowhere\\.internal"

echo "Public safety scan passed."
