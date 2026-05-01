# Local Development Stack

This directory contains the Docker Compose stack used for local development.

## Services

- Redis
- PostgreSQL
- LocalStack

## Start the Stack

From the repository root:

```bash
cd deploy/local-dev
./start-dev.sh
```

Or run the helper directly:

```bash
cd deploy/local-dev
./start-dev.sh
```

To initialize the local user/auth state too:

```bash
cd deploy/local-dev
./start-dev.sh --init-user
```

The `--init-user` path is idempotent and can be rerun safely. It now:

- waits for PostgreSQL, Redis, and LocalStack
- forces the bootstrap connection to the local PostgreSQL DSN even if `apps/api/.env` still points somewhere else
- forces `DB_SSL_MODE=disable` for the local bootstrap path
- ensures the local `user` table matches the dashboard-owned schema needed by API migrations
- runs API Alembic migrations in the local environment
- seeds the deterministic local developer account after the local schema is ready

Deterministic local developer account:

- `user_id`: `local-dev-user`
- `email`: `local-dev-user@knowhere.local`
- `tier`: `tier_5`
- `local_developer_key_seeded`: `true`

## Verify the Local API

After you start the API process locally, confirm the service is reachable:

```bash
curl http://localhost:5005/health
```

You can also open the local OpenAPI docs at
`http://localhost:5005/docs`.

## Stop the Stack

From the repository root:

```bash
cd deploy/local-dev
./stop-dev.sh
```

Or run the helper directly:

```bash
cd deploy/local-dev
./stop-dev.sh
```

## Service Endpoints

- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- LocalStack: `http://localhost:4566`

## Notes

- The Compose file is `deploy/local-dev/docker-compose.dev.yml`.
- `stop-dev.sh` automatically uses `docker-compose` when available and falls back to `docker compose` otherwise.
- Local development infrastructure belongs here; remote deployment assets do not.
