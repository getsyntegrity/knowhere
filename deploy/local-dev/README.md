# Local Development Stack

This directory contains the Docker Compose stack used for local development.

## Services

- Redis
- PostgreSQL
- LocalStack

## Start the Stack

From the repository root:

```bash
pnpm dev:services
```

Or run the helper directly:

```bash
cd deploy/local-dev
./start-dev.sh
```

The helper is idempotent and can be rerun safely. It now:

- waits for PostgreSQL, Redis, and LocalStack
- ensures the minimal local `user` table needed by API migrations exists without relying on dashboard migrations
- runs API Alembic migrations in the local environment
- seeds the deterministic local developer account after the local schema is ready

Deterministic local developer account:

- `user_id`: `local-dev-user`
- `email`: `local-dev-user@knowhere.local`
- `tier`: `tier_5`
- `api_key`: `sk_local_dev_tier5_full_access`

## Stop the Stack

From the repository root:

```bash
pnpm dev:services:down
```

Or run Docker Compose directly:

```bash
cd deploy/local-dev
docker-compose -f docker-compose.dev.yml down
```

## Service Endpoints

- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- LocalStack: `http://localhost:4566`

## Notes

- The Compose file is `deploy/local-dev/docker-compose.dev.yml`.
- Local development infrastructure belongs here; remote deployment assets do not.
