# Knowhere API

Knowhere API is the backend repository for document ingestion, parsing,
retrieval, and MCP-oriented knowledge access.

This publication-preparation branch keeps only the backend application surface:

- the FastAPI application under `apps/api`
- the Celery worker under `apps/worker`
- shared Python models and services under `packages/shared-python`
- local Docker-based development services under `deploy/local-dev`
- Docker build assets under `deploy/docker`
- repository-owned validation scripts under `scripts/`

This repository does not own runtime infrastructure, operator runbooks, or
environment-specific rollout state. Dashboard, docs-site, and SDK distribution
surfaces should stay in their dedicated repositories instead of being folded
back into this backend source tree.

## Project Governance

- Licensed under Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
- Contribution workflow and branch expectations live in
  [CONTRIBUTING.md](CONTRIBUTING.md).
- Security reporting guidance lives in [SECURITY.md](SECURITY.md).
- Community behavior expectations live in
  [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- The root [pyproject.toml](pyproject.toml) declares the retained Python
  workspace members used for publication preparation.

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
├── scripts/
│   ├── check-public.sh
│   ├── lint-public.sh
│   ├── test-public.sh
│   └── typecheck-public.sh
└── .github/workflows/
    ├── build-images.yml
    └── ci.yml
```

## Prerequisites

- Python 3.11+
- `uv`
- Docker with `docker compose`
- a local Chrome or Chromium driver if you plan to run document layout parsing
  flows

## Quick Start

1. Sync the Python environments:

```bash
cd packages/shared-python && uv sync
cd ../../apps/api && uv sync
cd ../worker && uv sync
```

2. Copy the environment examples:

```bash
cp apps/api/env.example apps/api/.env
cp apps/worker/env.example apps/worker/.env
```

3. Update the copied `.env` files with the values you need for local work:

- database and Redis connection settings
- S3-compatible storage credentials
- `SECRET_KEY`
- `USERS_DATA_PATH`
- `DS_KEY`
- any optional LLM, billing, or webhook providers you want to enable

4. Start the local infrastructure stack:

```bash
cd deploy/local-dev
./start-dev.sh
```

If you also want the helper to initialize the local API user state, rerun it
with `--init-user`:

```bash
cd deploy/local-dev
./start-dev.sh --init-user
```

5. Start the API and worker in separate terminals:

```bash
cd apps/api && uv run uvicorn main:app --host 0.0.0.0 --port 5005 --reload
cd apps/worker && uv run python worker.py
```

## Local Development Notes

- Use the shell helpers under `deploy/local-dev/` for start and stop instead of
  calling Compose directly from docs.
- The `--init-user` path is idempotent and can be rerun safely against an
  existing local database.
- The `--init-user` path forces
  `DATABASE_URL=postgresql+asyncpg://root:root123@localhost:5432/Knowhere`
  during bootstrap even if `apps/api/.env` is stale.
- The same bootstrap path forces `DB_SSL_MODE=disable`, runs local Alembic
  migrations, and seeds one deterministic local developer account.

Deterministic local developer account:

- `user_id`: `local-dev-user`
- `email`: `local-dev-user@knowhere.local`
- `tier`: `tier_5`
- `api_key`: `local_dev_demo_key_tier5_full_access`

## Local Endpoints

- API: `http://localhost:5005`
- OpenAPI docs: `http://localhost:5005/docs`
- LocalStack: `http://localhost:4566`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

## Quality Checks

Run the public lint baseline:

```bash
./scripts/lint-public.sh
```

Run the public type-check baseline:

```bash
./scripts/typecheck-public.sh
```

The current public type-check baseline targets the retained entrypoints that
define the published API contract and auth wiring:

- `app/api/v1/routes/retrieval.py`
- `app/api/v1/routes/qstash_callbacks.py`
- `app/api/v1/routes/documents.py`
- `app/api/v1/routes/api_key.py`
- `app/core/dependencies.py`
- `app/api/api_router.py`

Run the full public verification entrypoint:

```bash
./scripts/check-public.sh
```

## Tests

Run the vetted regression suites used by the public CI:

```bash
./scripts/test-public.sh
```

Run a single service suite:

```bash
./scripts/test-public-shared.sh
./scripts/test-public-api.sh
./scripts/test-public-worker.sh
```

## Additional Guides

- External dependency guide:
  [docs/external-services.md](docs/external-services.md)
- Self-hosting and local verification guide:
  [docs/self-hosting.md](docs/self-hosting.md)
- Release distribution policy:
  [docs/release-distribution.md](docs/release-distribution.md)

## Image Builds

Docker build assets live in `deploy/docker/`.

The active workflow in `.github/workflows/build-images.yml` only builds and
publishes Docker images for the `api` and `worker` services. This
publication-preparation branch keeps the registry path limited to GHCR.

- `main` and Git tags build production-tagged images
- `staging` builds staging-tagged images
- pull requests run build validation without publishing
- `workflow_dispatch` can build a selected service for `staging` or `prod`
- `docs/self-hosting.md` documents how to pull and run
  `ghcr.io/ontos-ai/knowhere-backend` and `ghcr.io/ontos-ai/knowhere-worker`

## Deployment Boundary

Runtime deployment, cloud infrastructure, rollout procedures, and live
environment references are intentionally kept out of this repository.

Use the `knowhere-api-infra` repository for:

- Kubernetes and cloud runtime ownership
- live environment snapshots
- rollout and rollback procedures
- operator-facing infrastructure documentation

Do not reintroduce cloud deployment manifests, Terraform state, SSH keys, or
runtime secrets into this repository.
