#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_ROOT="$(mktemp -d)"
FAKE_BIN_DIR="${TEST_ROOT}/bin"
TEST_REPO_ROOT="${TEST_ROOT}/repo"
LOG_FILE="${TEST_ROOT}/commands.log"

cleanup() {
    rm -rf "${TEST_ROOT}"
}

assert_contains() {
    local expected="$1"

    if ! grep -Fq "${expected}" "${LOG_FILE}"; then
        printf 'Expected to find %s in %s\n' "${expected}" "${LOG_FILE}" >&2
        exit 1
    fi
}

create_fake_commands() {
    mkdir -p "${FAKE_BIN_DIR}"

    cat > "${FAKE_BIN_DIR}/docker" <<EOF
#!/usr/bin/env bash
set -euo pipefail
printf 'docker:%s\n' "\$*" >> "${LOG_FILE}"
if [[ "\${1:-}" == "info" ]]; then
    exit 0
fi
if [[ "\${1:-}" == "exec" ]]; then
    exit 0
fi
if [[ "\${1:-}" == "compose" ]]; then
    exit 0
fi
exit 0
EOF
    chmod +x "${FAKE_BIN_DIR}/docker"

    cat > "${FAKE_BIN_DIR}/curl" <<EOF
#!/usr/bin/env bash
set -euo pipefail
printf 'curl:%s\n' "\$*" >> "${LOG_FILE}"
exit 0
EOF
    chmod +x "${FAKE_BIN_DIR}/curl"

    cat > "${FAKE_BIN_DIR}/sleep" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exit 0
EOF
    chmod +x "${FAKE_BIN_DIR}/sleep"

    cat > "${FAKE_BIN_DIR}/uv" <<EOF
#!/usr/bin/env bash
set -euo pipefail
printf 'uv:DATABASE_URL=%s DB_SSL_MODE=%s ARGS=%s\n' "\${DATABASE_URL:-}" "\${DB_SSL_MODE:-}" "\$*" >> "${LOG_FILE}"
exit 0
EOF
    chmod +x "${FAKE_BIN_DIR}/uv"
}

prepare_test_repo() {
    mkdir -p "${TEST_REPO_ROOT}/deploy/local-dev" "${TEST_REPO_ROOT}/apps/api"
    cp "${SCRIPT_DIR}/start-dev.sh" "${TEST_REPO_ROOT}/deploy/local-dev/start-dev.sh"
    cp "${SCRIPT_DIR}/stop-dev.sh" "${TEST_REPO_ROOT}/deploy/local-dev/stop-dev.sh"
    chmod +x "${TEST_REPO_ROOT}/deploy/local-dev/start-dev.sh" "${TEST_REPO_ROOT}/deploy/local-dev/stop-dev.sh"

    printf 'services: {}\n' > "${TEST_REPO_ROOT}/deploy/local-dev/docker-compose.dev.yml"
    printf 'DATABASE_URL=postgresql+asyncpg://root:root123@localhost:5432/Knowhere\n' > "${TEST_REPO_ROOT}/apps/api/env.example"
    printf 'DATABASE_URL=postgresql+asyncpg://remote-user:remote-pass@remote-host:5432/Remote\nDB_SSL_MODE=require\n' > "${TEST_REPO_ROOT}/apps/api/.env"
}

test_start_dev_forces_local_database_settings() {
    : > "${LOG_FILE}"
    PATH="${FAKE_BIN_DIR}:${PATH}" "${TEST_REPO_ROOT}/deploy/local-dev/start-dev.sh" --init-user >/dev/null

    assert_contains 'uv:DATABASE_URL=postgresql+asyncpg://root:root123@localhost:5432/Knowhere DB_SSL_MODE=disable'
}

test_stop_dev_falls_back_to_docker_compose_plugin() {
    rm -f "${FAKE_BIN_DIR}/docker-compose"
    : > "${LOG_FILE}"
    PATH="${FAKE_BIN_DIR}:${PATH}" "${TEST_REPO_ROOT}/deploy/local-dev/stop-dev.sh" >/dev/null

    assert_contains 'docker:compose -f'
}

main() {
    trap cleanup EXIT
    create_fake_commands
    prepare_test_repo
    test_start_dev_forces_local_database_settings
    test_stop_dev_falls_back_to_docker_compose_plugin
    printf 'local-dev tooling checks passed\n'
}

main "$@"
