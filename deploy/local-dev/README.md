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
