# API Contract Backlog

Last updated: 2026-04-26
Owner: Codex + repository maintainers
Status: Complete

## Purpose

Track the remaining API-surface contract coverage work for the routers mounted from `apps/api/app/api/v1/api_v1.py`.

This backlog is intentionally route-group oriented:

- It follows the public API shape, not internal services.
- It records what is already covered vs what is still missing.
- It gives the next concrete contract cases to add for each surface.

## Current Coverage Snapshot

| Route group | Mounted surface | Status | Notes |
| --- | --- | --- | --- |
| `api_key` | `/api/v1/auth/*` | `Full` | Contract coverage includes `create`, `list`, `revoke`, `regenerate`, `detail`, `toggle`, and revoked/disabled-key rejection. |
| `guest` | `/api/v1/guest` | `Full` | Guest registration and duplicate-device conflict are covered. |
| `billing` | `/api/v1/billing/*` | `Full` | Credits balance, usage, parse usage, history, price configs, checkout, payment intent, and Stripe webhook rejection are covered. |
| `knowledge_base` | `/api/v1/kb/*` | `Full` | Directory CRUD, first-read bootstrap, content listing, root KB creation, and delete branches are covered. |
| `jobs` | `/api/v1/jobs/*` | `Full` | File mode, URL mode, reads, confirm-upload, and all live jobs `429` layers are covered. |
| `retrieval` | `/api/v1/retrieval/query` | `Full` | Query results, default namespace fallback, empty-query short circuit, validation, and exclusion filters are covered. |
| `documents` | `/api/v1/documents/*` | `Full` | Listing, detail, missing-document, and both archive route forms are covered. |
| `s3_events` | `/api/v1/internal/s3-events` | `Full` | SNS-confirmation GET, direct upload events, SNS-wrapped upload events, workflow handoff, and malformed payload handling are covered. |
| `webhook` | `/api/v1/webhooks/*` | `Full` | Log pagination/filtering and manual trigger success plus 400/403/404 error paths are covered. |
| `webhook_secrets` | `/api/v1/webhooks/secrets/*` | `Full` | Secret creation, dedupe, masking, revoke, and missing-secret behavior are covered. |
| `qstash_callbacks` | `/api/v1/webhooks/qstash/*` | `Full` | Signature rejection, success/failure callbacks, webhook-log persistence, and missing-correlation behavior are covered. |
| `health` | `/api/v1/health/database/*` | `Full` | `health`, `info`, `performance`, and `prewarm` are covered. |
| `version` | `/api/v1/version`, `/api/v1/` | `Full` | Both version endpoints return the expected payload shape. |

## Completion Update

- The contract suite now covers every mounted router group in `apps/api/app/api/v1/api_v1.py`.
- Latest verification on 2026-04-26: `uv run pytest apps/api/tests/contract -q` -> `78 passed`.
- The detailed checklists below are retained as the original planning record. The coverage snapshot above is the authoritative current status.

## Suggested Execution Order

1. `billing`
2. `documents`
3. `retrieval`
4. `webhook`
5. `webhook_secrets`
6. `qstash_callbacks`
7. `api_key` remainder
8. `s3_events`
9. `version`
10. `health`
11. `knowledge_base`

## Shared Harness Work To Unblock The Next Surfaces

- [ ] Add direct DB seed helpers for credits ledger rows, `user_balance`, and `stripe_price_configs`.
- [ ] Add direct DB seed helpers for `documents`, `job_results`, `document_sections`, and `document_chunks`.
- [ ] Add direct DB seed helpers for `webhook_events`, `webhook_logs`, `webhook_secrets`, `file_directory`, and `knowledge_base`.
- [ ] Add narrow edge-boundary stubs for Stripe payment-intent and checkout-session creation.
- [ ] Add a narrow webhook-dispatch stub for `POST /api/v1/webhooks/trigger` so the contract suite can assert the HTTP surface without depending on outbound delivery.
- [ ] Add a narrow QStash-signature verification seam for callback tests instead of depending on live QStash signing material.

## Behavior Decisions To Make Before Locking Coverage

- [ ] Decide whether `POST /api/v1/billing/webhook` should keep returning `500 INTERNAL_ERROR` for a missing `stripe-signature` header or be normalized to `400 INVALID_ARGUMENT`.
- [ ] Decide whether the current `GET /api/v1/billing/usage` placeholder fields (`success_rate = 95.0`, `average_response_time = 0.0`, `top_endpoints = []`) are contractual or temporary.
- [ ] Decide whether knowledge-base directory read/update/delete routes must enforce ownership by `current_user.user_id`; the current repository calls are ID-based.
- [ ] Decide whether `POST /api/v1/webhooks/trigger` should remain log-free (`delivery_id = null`) for manual dispatches or persist a `webhook_logs` row.

## Priority 1

### [ ] Billing

Suggested file: `apps/api/tests/contract/test_billing_contract.py`

Routes:

- `POST /api/v1/billing/buy-credits`
- `GET /api/v1/billing/credits`
- `GET /api/v1/billing/usage`
- `GET /api/v1/billing/parse-usage`
- `GET /api/v1/billing/history`
- `GET /api/v1/billing/price-configs`
- `POST /api/v1/billing/buy-credits-package`
- `POST /api/v1/billing/webhook`

First contract cases:

- [ ] `GET /credits` should return the initialized credits balance for the authenticated user.
- [ ] `GET /usage` should return the seeded usage total and transaction count for the requested period, plus the current placeholder fields.
- [ ] `GET /history` should return only that user’s credit transactions in response shape.
- [ ] `GET /parse-usage` should compute `credits_used`, `success_rate`, and `avg_processing_time` from seeded jobs and transactions.
- [ ] `GET /price-configs` should split subscriptions and credits packages correctly.
- [ ] `POST /webhook` should reject a missing `stripe-signature` header.
- [ ] `POST /buy-credits-package` should return a checkout URL when the Stripe boundary succeeds.
- [ ] `POST /buy-credits` should return a payment-intent payload when the Stripe boundary succeeds.

### [ ] Documents

Suggested file: `apps/api/tests/contract/test_documents_contract.py`

Routes:

- `GET /api/v1/documents`
- `GET /api/v1/documents/{document_id}`
- `POST /api/v1/documents/{document_id}/archive`
- `POST /api/v1/documents/{document_id}:archive`

First contract cases:

- [ ] `GET /documents` should return the effective namespace and only that user’s documents.
- [ ] `GET /documents/{document_id}` should return document detail for an owned document.
- [ ] `GET /documents/{document_id}` should return `404 NOT_FOUND` for a missing document.
- [ ] `POST /documents/{document_id}/archive` should persist the archived state.
- [ ] `POST /documents/{document_id}:archive` should behave identically to the canonical archive route.

### [ ] Retrieval

Suggested file: `apps/api/tests/contract/test_retrieval_contract.py`

Routes:

- `POST /api/v1/retrieval/query`

First contract cases:

- [ ] A seeded retrieval query should return results for the authenticated user.
- [ ] Omitting `namespace` should fall back to `default`.
- [ ] An empty `query` should return `200` with `router_used = empty_query_filtered` and an empty `results` list.
- [ ] An invalid `channels` value should return request validation failure.
- [ ] `exclude_document_ids` should remove matching results from the response.
- [ ] `exclude_sections` should remove matching section results from the response.

## Priority 2

### [ ] Webhook

Suggested file: `apps/api/tests/contract/test_webhook_contract.py`

Routes:

- `GET /api/v1/webhooks/logs`
- `POST /api/v1/webhooks/trigger`

First contract cases:

- [ ] `GET /webhooks/logs` should return paginated webhook delivery logs.
- [ ] `GET /webhooks/logs?job_id=...` should filter logs by job.
- [ ] `POST /webhooks/trigger` should succeed for an owned terminal job with a configured webhook and an existing event.
- [ ] `POST /webhooks/trigger` should return `400 INVALID_ARGUMENT` for a non-terminal job.
- [ ] `POST /webhooks/trigger` should return `404 NOT_FOUND` when the webhook event does not exist.
- [ ] `POST /webhooks/trigger` should return `403 PERMISSION_DENIED` across an ownership boundary.

### [ ] Webhook Secrets

Suggested file: `apps/api/tests/contract/test_webhook_secret_contract.py`

Routes:

- `GET /api/v1/webhooks/secrets`
- `POST /api/v1/webhooks/secrets`
- `DELETE /api/v1/webhooks/secrets/{secret_id}`

First contract cases:

- [ ] `POST /webhooks/secrets` should create a secret and return the full one-time secret value.
- [ ] A second `POST /webhooks/secrets` for the same endpoint should return the existing masked secret instead of creating a duplicate.
- [ ] `GET /webhooks/secrets` should return only masked secret values.
- [ ] `DELETE /webhooks/secrets/{secret_id}` should revoke the secret.
- [ ] `DELETE /webhooks/secrets/{secret_id}` should return `404 NOT_FOUND` for a missing secret.

### [ ] QStash Callbacks

Suggested file: `apps/api/tests/contract/test_qstash_callback_contract.py`

Routes:

- `POST /api/v1/webhooks/qstash/callback`
- `POST /api/v1/webhooks/qstash/failure`

First contract cases:

- [ ] Invalid callback signature should return `401`.
- [ ] Success callback should mark the matching webhook event as delivered and persist a webhook log row.
- [ ] Failure callback should mark the matching webhook event as failed and persist a webhook log row with the error.
- [ ] Missing correlated event ID should return `200` without mutating persisted state.

### [ ] API Key Remainder

Suggested file: `apps/api/tests/contract/test_api_key_contract.py`

Remaining routes:

- `POST /api/v1/auth/regenerate`
- `GET /api/v1/auth/{api_key_id}`
- `PUT /api/v1/auth/{api_key_id}/toggle`

First contract cases:

- [ ] `POST /auth/regenerate` should return a new raw API key and invalidate the old key.
- [ ] `GET /auth/{api_key_id}` should return the owned key metadata.
- [ ] `GET /auth/{api_key_id}` should return `404 NOT_FOUND` for a missing key.
- [ ] `PUT /auth/{api_key_id}/toggle` should disable a key so it no longer authenticates.
- [ ] Toggling the key again should re-enable it.

### [ ] S3 Events

Suggested file: `apps/api/tests/contract/test_s3_event_contract.py`

Routes:

- `GET /api/v1/internal/s3-events`
- `POST /api/v1/internal/s3-events`

First contract cases:

- [ ] `GET /internal/s3-events` should acknowledge SNS subscription confirmation requests.
- [ ] `POST /internal/s3-events` should accept a direct or SNS-wrapped upload-complete event and advance a waiting-file job.
- [ ] `POST /internal/s3-events` should start workflow handoff after the upload-complete event is processed.
- [ ] An unknown or malformed event payload should still return `200` without unsafe retries.

## Priority 3

### [ ] Version

Suggested file: `apps/api/tests/contract/test_version_contract.py`

Routes:

- `GET /api/v1/version`
- `GET /api/v1/`

First contract cases:

- [ ] `GET /version` should return the version payload shape with `service = knowhere-api`.
- [ ] `GET /` under v1 should return the same version payload as `/version`.

### [ ] Health

Suggested file: `apps/api/tests/contract/test_database_health_contract.py`

Routes:

- `GET /api/v1/health/database/health`
- `GET /api/v1/health/database/info`
- `GET /api/v1/health/database/performance`
- `POST /api/v1/health/database/prewarm`

First contract cases:

- [ ] `GET /health/database/health` should return the database health payload shape.
- [ ] `GET /health/database/info` should return the database info payload shape.
- [ ] `GET /health/database/performance` should return the performance payload shape.
- [ ] `POST /health/database/prewarm` should return the prewarm completion message.

### [ ] Knowledge Base

Suggested file: `apps/api/tests/contract/test_knowledge_base_contract.py`

Routes:

- `POST /api/v1/kb/create_directory`
- `POST /api/v1/kb/delete_directory`
- `POST /api/v1/kb/update_directory`
- `POST /api/v1/kb/get_directory`
- `POST /api/v1/kb/list_directory`
- `POST /api/v1/kb/add_kb`
- `DELETE /api/v1/kb/contents/{content_id}`

First contract cases:

- [ ] `POST /kb/get_directory` should create a default root directory on first access.
- [ ] `POST /kb/create_directory` should create a directory for the authenticated user.
- [ ] `POST /kb/delete_directory` should delete the selected directory and make it disappear from subsequent tree reads.
- [ ] `POST /kb/update_directory` should return `400 INVALID_ARGUMENT` when `id` is missing.
- [ ] `POST /kb/update_directory` should persist the updated directory attributes.
- [ ] `POST /kb/list_directory` should return content for the selected directory.
- [ ] `POST /kb/add_kb` should create a root knowledge-base path.
- [ ] `DELETE /kb/contents/{content_id}` should cover both directory deletion and content deletion branches.

## Done Definition For This Backlog

This backlog is complete when:

- Every mounted router group in `apps/api/app/api/v1/api_v1.py` has either full contract coverage or an explicit decision to remove the route.
- Remaining API contract files describe endpoint behavior and durable side effects rather than helper choreography.
- The route-group status table at the top of this file can be updated to `Full` for every retained public surface.
