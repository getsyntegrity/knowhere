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

log_step() {
    printf '%s\n' "$1"
}

warn() {
    printf 'Warning: %s\n' "$1"
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
    if [[ -f "${API_DIR}/.env" ]]; then
        return 0
    fi

    cp "${API_DIR}/env.example" "${API_DIR}/.env"
    warn "Created apps/api/.env from env.example. Review local values before relying on external integrations."
    warn "For the local Postgres container, set DB_SSL_MODE=disable in apps/api/.env if it is still set to prefer."
}

run_local_bootstrap() {
    if ! command -v uv >/dev/null 2>&1; then
        warn "uv is not installed, so the local bootstrap helper was skipped."
        return 0
    fi

    prepare_api_env

    if ! (
        cd "${API_DIR}" &&
        uv run --python 3.11 python scripts/bootstrap_local_dev.py --mode ensure-user-table
    ); then
        warn "Failed to ensure the local development user table via the bootstrap helper. API startup will retry this in development mode."
        return 0
    fi

    if ! (
        cd "${API_DIR}" &&
        uv run --python 3.11 python scripts/bootstrap_local_dev.py --mode seed-if-ready
    ); then
        warn "Failed to seed the local development user via the bootstrap helper. API startup will retry this after migrations."
    fi
}

print_summary() {
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
  - after API migrations complete, reruns will also refresh the same dev account instead of creating duplicates

Stop services:
  docker-compose -f ${COMPOSE_FILE} down
EOF
}

main() {
    log_step "Starting Knowhere local development services..."
    require_docker

    docker-compose -f "${COMPOSE_FILE}" up -d

    wait_for_postgres
    wait_for_redis
    wait_for_localstack
    run_local_bootstrap
    print_summary
}

main "$@"
