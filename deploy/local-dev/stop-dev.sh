#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.dev.yml"

print_usage() {
    cat <<EOF
Usage: ./stop-dev.sh [compose down args...]

Stop the local development Docker Compose stack.
EOF
}

run_compose() {
    if command -v docker-compose >/dev/null 2>&1; then
        docker-compose "$@"
        return 0
    fi

    docker compose "$@"
}

main() {
    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
        print_usage
        exit 0
    fi

    run_compose -f "${COMPOSE_FILE}" down "$@"
}

main "$@"
