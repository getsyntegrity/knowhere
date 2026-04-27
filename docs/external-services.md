# External Service Dependencies

Knowhere API is the backend for <https://knowhereto.ai/>. Public product
documentation can also link to <https://docs.knowhereto.ai/> when deeper setup
references are helpful.

## Required For Local Startup

An external contributor needs these dependencies to run the retained backend
surface locally:

- PostgreSQL for the application database
- Redis for Celery and short-lived state
- S3-compatible storage for uploads and result assets
- one OpenAI-compatible LLM provider key for retrieval and parsing flows

The repo-managed `deploy/local-dev` stack provides PostgreSQL, Redis, and
LocalStack so the default `env.example` files can use a coherent local baseline.

## Required Only For Specific Features

- MinerU:
  required only if you want MinerU-backed document parsing flows
- iLoveAPI:
  required only for conversion paths such as PPTX-to-PDF
- QStash:
  required only if you want queued outbound webhook delivery
- Stripe:
  required only if you enable billing and checkout flows
- Resend:
  required only if you enable email notifications
- OAuth provider credentials:
  required only if you run dashboard-linked auth flows

## Optional Observability And Analytics

- Logfire for distributed tracing export
- Moesif for API analytics
- PostHog for product analytics

These integrations are intentionally optional. Leaving them empty should not
block a local backend bootstrap.

## Minimum Viable Local Configuration

The smallest supported local setup is:

1. copy `apps/api/env.example` and `apps/worker/env.example`
2. keep the default local PostgreSQL, Redis, and LocalStack values
3. add one real LLM provider key such as `DS_KEY`
4. run `deploy/local-dev/start-dev.sh`
5. start the API and worker with `uv run`

That path is the baseline public developer workflow. Additional providers should
only be configured when you need the matching feature set.
