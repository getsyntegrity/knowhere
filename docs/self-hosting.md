# Self-Hosting And Local Verification

This repository keeps the simplest supported backend-only local workflow.

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

## 3. Start The API And Worker

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

## 5. Stop Local Infrastructure

```bash
cd deploy/local-dev
./stop-dev.sh
```

That start and stop flow is the documented public local baseline. Anything more
complex should build on top of these helpers instead of replacing them.
