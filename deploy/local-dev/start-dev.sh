#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
API_DIR="${REPO_ROOT}/apps/api"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.dev.yml"

LOCAL_DEV_USER_ID="local-dev-user"
LOCAL_DEV_USER_EMAIL="local-dev-user@knowhere.local"
LOCAL_DEV_USER_TIER="tier_5"
LOCAL_DEV_API_KEY="sk_local_dev_tier5_full_access"
RUN_USER_INIT=0

log_step() {
    printf '%s\n' "$1"
}

warn() {
    printf 'Warning: %s\n' "$1"
}

print_usage() {
    cat <<EOF
Usage: ./start-dev.sh [--init-user]

Options:
  --init-user   Create the dashboard-compatible local user table, run API migrations,
                and seed the deterministic local developer account.
  -h, --help    Show this help message.
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --init-user)
                RUN_USER_INIT=1
                ;;
            -h|--help)
                print_usage
                exit 0
                ;;
            *)
                printf 'Unknown option: %s\n' "$1" >&2
                print_usage >&2
                exit 1
                ;;
        esac
        shift
    done
}

run_compose() {
    if command -v docker-compose >/dev/null 2>&1; then
        docker-compose "$@"
        return 0
    fi

    docker compose "$@"
}

require_uv() {
    if ! command -v uv >/dev/null 2>&1; then
        printf 'uv is required for local bootstrap. Install uv first.\n' >&2
        exit 1
    fi
}

require_docker() {
    if ! docker info >/dev/null 2>&1; then
        printf 'Docker is not running. Start Docker first.\n' >&2
        exit 1
    fi
}

wait_for_postgres() {
    log_step "Waiting for PostgreSQL..."

    for _attempt in $(seq 1 30); do
        if docker exec knowhere_postgres pg_isready -U root -d Knowhere >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done

    printf 'PostgreSQL did not become ready in time.\n' >&2
    exit 1
}

wait_for_redis() {
    log_step "Waiting for Redis..."

    for _attempt in $(seq 1 30); do
        if docker exec knowhere_redis redis-cli ping >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done

    printf 'Redis did not become ready in time.\n' >&2
    exit 1
}

wait_for_localstack() {
    log_step "Waiting for LocalStack..."

    for _attempt in $(seq 1 30); do
        if curl -fsS http://localhost:4566/_localstack/health >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done

    printf 'LocalStack did not become ready in time.\n' >&2
    exit 1
}

prepare_api_env() {
    if [[ ! -f "${API_DIR}/.env" ]]; then
        cp "${API_DIR}/env.example" "${API_DIR}/.env"
        warn "Created apps/api/.env from env.example for local development."
    fi

    if grep -q '^DB_SSL_MODE=' "${API_DIR}/.env"; then
        python3 - <<'PY' "${API_DIR}/.env"
from pathlib import Path
import sys

env_path = Path(sys.argv[1])
lines = env_path.read_text().splitlines()
updated_lines = []
for line in lines:
    if line.startswith("DB_SSL_MODE="):
        updated_lines.append("DB_SSL_MODE=disable")
    else:
        updated_lines.append(line)
env_path.write_text("\n".join(updated_lines) + "\n")
PY
    else
        printf '\nDB_SSL_MODE=disable\n' >> "${API_DIR}/.env"
    fi
}

run_local_bootstrap() {
    require_uv
    prepare_api_env

    log_step "Ensuring local development user table..."
    (
        cd "${API_DIR}" &&
        uv run --python 3.11 python scripts/bootstrap_local_dev.py --mode ensure-user-table
    )

    log_step "Running local API migrations..."
    (
        cd "${API_DIR}" &&
        uv run --python 3.11 python -m alembic upgrade heads
    )

    log_step "Seeding deterministic local development user..."
    (
        cd "${API_DIR}" &&
        uv run --python 3.11 python scripts/bootstrap_local_dev.py --mode seed
    )
}

print_summary() {
    if [[ "${RUN_USER_INIT}" -eq 1 ]]; then
        cat <<EOF

Local development services are ready.

Service endpoints:
  - LocalStack: http://localhost:4566
  - PostgreSQL: localhost:5432 (root/root123)
  - Redis: localhost:6379

Next steps:
  1. Start the API: pnpm dev:api
  2. Start the worker: pnpm dev:worker

Deterministic local developer account:
  - user_id: ${LOCAL_DEV_USER_ID}
  - email: ${LOCAL_DEV_USER_EMAIL}
  - tier: ${LOCAL_DEV_USER_TIER}
  - api_key: ${LOCAL_DEV_API_KEY}

The helper is idempotent:
  - rerunning this script will safely re-check the local user table
  - rerunning this script will reapply local API migrations safely
  - rerunning this script will refresh the same dev account instead of creating duplicates

Stop services:
  docker-compose -f ${COMPOSE_FILE} down
EOF
        return 0
    fi

    cat <<EOF

Local development services are ready.

Service endpoints:
  - LocalStack: http://localhost:4566
  - PostgreSQL: localhost:5432 (root/root123)
  - Redis: localhost:6379

Next steps:
  1. Start the API: pnpm dev:api
  2. Start the worker: pnpm dev:worker

Optional user bootstrap:
  - rerun this script with --init-user to create the dashboard-compatible local user table
  - the same --init-user path also runs API migrations and seeds the deterministic local developer account

Stop services:
  docker-compose -f ${COMPOSE_FILE} down
EOF
}

main() {
    parse_args "$@"
    log_step "Starting Knowhere local development services..."
    require_docker

    run_compose -f "${COMPOSE_FILE}" up -d

    wait_for_postgres
    wait_for_redis
    wait_for_localstack
    if [[ "${RUN_USER_INIT}" -eq 1 ]]; then
        run_local_bootstrap
    fi
    print_summary
}

main "$@"
