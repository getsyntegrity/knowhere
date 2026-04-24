# Self-Hosting And Local Verification

This repository keeps two supported backend-only workflows:

- run from source with `uv` for local development
- run the published GHCR images for container-based self-hosting validation

Both paths require the same environment configuration and external services.

## 1. Prepare Configuration

```bash
cp apps/api/env.example apps/api/.env
cp apps/worker/env.example apps/worker/.env
```

Add one real LLM provider key before you start the application processes.

## 2. Start Local Infrastructure

```bash
cd deploy/local-dev
./start-dev.sh
```

If you also want the helper to initialize the local API user state, rerun it
with:

```bash
cd deploy/local-dev
./start-dev.sh --init-user
```

## 3. Start The API And Worker From Source

```bash
cd apps/api && uv run uvicorn main:app --host 0.0.0.0 --port 5005 --reload
cd apps/worker && uv run python worker.py
```

## 4. Verify The Local Server

```bash
curl http://localhost:5005/health
```

If the API is healthy, you can also open:

- `http://localhost:5005/docs` for the local OpenAPI docs
- `http://localhost:4566/_localstack/health` for LocalStack health

## 5. Run The Published GHCR Images

If you want to verify the public container path instead of running from source,
pull the published API and worker images first:

```bash
docker pull ghcr.io/ontos-ai/knowhere-backend:staging-latest
docker pull ghcr.io/ontos-ai/knowhere-worker:staging-latest
```

The easiest local validation path is still to keep the repo-managed PostgreSQL,
Redis, and LocalStack stack running via `deploy/local-dev/start-dev.sh`, then
reuse the same `.env` files with `docker run`.

Start the API container:

```bash
docker run --rm \
  --name knowhere-api \
  --env-file apps/api/.env \
  -p 5005:5005 \
  ghcr.io/ontos-ai/knowhere-backend:staging-latest
```

Start the worker container in a second terminal:

```bash
docker run --rm \
  --name knowhere-worker \
  --env-file apps/worker/.env \
  ghcr.io/ontos-ai/knowhere-worker:staging-latest
```

If you are not using the local-dev stack, point the copied `.env` files at your
own PostgreSQL, Redis, and S3-compatible storage before launching the images.
For long-lived deployments, pin an explicit published tag instead of relying on
`staging-latest`.

## 6. Deploy Your Own Server

The public images are designed for self-hosted API and worker deployments, not
for bundled managed infrastructure. A minimal deployment should:

- run the API and worker as separate containers
- provide PostgreSQL, Redis, and S3-compatible storage outside the images
- inject configuration only through environment variables or your orchestrator's
  secret management
- pin explicit image tags during rollout and upgrade deliberately

This repository does not ship Kubernetes manifests, Terraform state, or cloud
operator runbooks. Use your own container platform, VM, or orchestrator to run
the published images with the environment settings described in
`apps/api/env.example`, `apps/worker/env.example`, and
`docs/external-services.md`.

## 7. Stop Local Infrastructure

```bash
cd deploy/local-dev
./stop-dev.sh
```

That start and stop flow is the documented public local baseline. Anything more
complex should build on top of these helpers or the published GHCR images
instead of assuming private infrastructure.
