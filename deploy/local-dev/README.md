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
