<img width="2000" height="466" alt="20260506-100355" src="https://github.com/user-attachments/assets/d969e304-71eb-4610-8d94-0ea9706fec11" />


Knowhere API is the backend repository for document ingestion, parsing,
retrieval, and MCP-oriented knowledge access.

## Features

## Project Governance

- Licensed under Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
- Contribution workflow and branch expectations live in
  [CONTRIBUTING.md](CONTRIBUTING.md).
- Security reporting guidance lives in [SECURITY.md](SECURITY.md).
- Community behavior expectations live in
  [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Repository Layout

```text
knowhere-api/
├── apps/
│   ├── api/
│   └── worker/
├── packages/
│   └── shared-python/
├── deploy/
│   ├── docker/
│   └── local-dev/
└── .github/workflows/
    └── build-images.yml
```

## Architecture Overview

## Prerequisites

- Python 3.11+
- `uv`
- Docker with `docker compose`
- a local Chrome or Chromium driver if you plan to run document layout parsing
  flows

## Configuration

## Quick Start

1. Sync the workspace dependencies:

```bash
uv sync --all-packages
```

2. Copy the environment examples:

```bash
cp apps/api/.env.example apps/api/.env
cp apps/worker/.env.example apps/worker/.env
```

3. Update the copied `.env` files with the values you need for local work:

- database and Redis connection settings
- S3-compatible storage credentials
- `SECRET_KEY`
- `USERS_DATA_PATH`
- `DS_KEY`
- any optional LLM, billing, or webhook providers you want to enable

The example files default to the open-source/self-hosted behavior:

- `API_STANDALONE_MODE_ENABLED=false` for the combined dashboard + API flow, where
  the dashboard initializes Better Auth tables before API migrations.
- `BILLING_ENABLED=false`, so Stripe and credit deduction are not required.
- `RATE_LIMIT_ENABLED=false` for local/self-hosted convenience; set it to
  `true` when you want API rate limits enforced.

For API-only development without the dashboard, set `API_STANDALONE_MODE_ENABLED=true`,
run API migrations, then create an API-only user/key:

```bash
cd apps/api
uv run --python 3.11 python -m alembic upgrade heads
uv run --python 3.11 python scripts/init_user.py --email you@example.com
```

If you plan to use the dashboard, start the combined self-hosted stack and
register through the dashboard instead of using `scripts/init_user.py`.

4. Start the local infrastructure stack:

```bash
./deploy/local-dev/start-dev.sh
```

If you also want the helper to initialize the local API user state, rerun it
with `--init-user`:

```bash
./deploy/local-dev/start-dev.sh --init-user
```

5. Start the API and worker in separate terminals:

```bash
cd apps/api && uv run main.py
cd apps/worker && uv run worker.py
```

## Quality Checks

Run lint checks from the repository root:

```bash
make lint
```

Apply safe Ruff fixes:

```bash
make lint-fix
```

Run type checks across the API, worker, and shared source code:

```bash
make typecheck
```

Run both lint and type checks:

```bash
make check
```

## Local Endpoints

- API: `http://localhost:5005`
- OpenAPI docs: `http://localhost:5005/docs`
- LocalStack: `http://localhost:4566`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

## Quick Example Request

## Additional Guides

- External dependency guide:
  [docs/external-services.md](docs/external-services.md)
