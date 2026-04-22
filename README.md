# Knowhere Monorepo

Knowhere application source code lives in this repository.

This repository owns:

- application code under `apps/` and `packages/`
- local development infrastructure under `deploy/local-dev/`
- container image build assets under `deploy/docker/`
- CI workflows that build and publish Docker images

This repository does not own runtime deployment state.

## Repository Layout

```text
knowhere/
├── apps/
│   ├── api/
│   ├── worker/
│   ├── web/
│   └── docs/
├── packages/
│   ├── sdk-typescript/
│   ├── sdk-python/
│   ├── shared-types/
│   └── openapi-specs/
├── deploy/
│   ├── docker/
│   └── local-dev/
└── .github/workflows/build-images.yml
```

## Prerequisites

- Node.js 18+
- `pnpm`
- Python 3.11+
- `uv`
- Docker

## Install Dependencies

```bash
pnpm install

cd apps/api
uv sync

cd ../worker
uv sync
```

## Local Development

Start local infrastructure services:

```bash
cd deploy/local-dev
./start-dev.sh
```

Initialize the local user/auth state too when needed:

```bash
cd deploy/local-dev
./start-dev.sh --init-user
```

Start application processes in separate terminals:

```bash
pnpm dev:api
pnpm dev:worker
pnpm dev:web
pnpm dev:docs
```

Local API development bootstrap:

- Use the shell helpers under `deploy/local-dev/` for start/stop instead of calling Compose directly from docs.
- Pass `--init-user` when you want the helper to prepare local API auth state:
  - `cd deploy/local-dev && ./start-dev.sh --init-user`
- The `--init-user` path is idempotent. It can be rerun safely against an existing local database.
- The `--init-user` path now prepares the local API database before you start the API process:
  - forces `DATABASE_URL=postgresql+asyncpg://root:root123@localhost:5432/Knowhere` for the bootstrap commands even if `apps/api/.env` is stale
  - forces `DB_SSL_MODE=disable` for the same bootstrap path
  - creates a dashboard-compatible local `user` table needed by API foreign keys
  - runs local API Alembic migrations
  - seeds one deterministic local developer account

Deterministic local developer account:

- `user_id`: `local-dev-user`
- `email`: `local-dev-user@knowhere.local`
- `tier`: `tier_5`
- `api_key`: `sk_local_dev_tier5_full_access`

Stop local infrastructure services:

```bash
cd deploy/local-dev
./stop-dev.sh
```

Common local endpoints:

- API: `http://localhost:5005`
- API docs: `http://localhost:5005/docs`
- Web: `http://localhost:3000`
- Docs: `http://localhost:3001`
- LocalStack: `http://localhost:4566`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`

## Image Builds

Docker build assets live in `deploy/docker/`.

The active GitHub Actions workflow in `.github/workflows/build-images.yml` only builds and publishes Docker images for the `api` and `worker` services.

- `main` and Git tags build production-tagged images
- `staging` builds staging-tagged images
- pull requests run build validation without publishing
- `workflow_dispatch` can build a selected service for `staging` or `prod`

## Deployment Boundary

Runtime deployment, cloud infrastructure, rollout procedures, and live environment references are intentionally kept out of this repository.

Use the `knowhere-api-infra` repository for:

- Kubernetes and cloud runtime ownership
- live environment snapshots
- rollout and rollback procedures
- operator-facing infrastructure documentation

Do not reintroduce cloud deployment manifests, Terraform state, SSH keys, or runtime secrets into this repository.
