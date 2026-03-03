# Structured Logging Plan (API + Worker)

## Objective
Define and roll out one structured log schema across:
- `apps/api`
- `apps/worker`
- shared exception layer in `packages/shared-python/shared/core/exceptions` (highest priority)

The schema must keep a stable base field set for every log line, then add contextual fields (request/task/job/exception) depending on execution path.

## Scope
- In scope:
  - Shared logger schema and output format.
  - Request/task context propagation.
  - Exception-centric logging contract (`KnowhereException` and wrappers).
  - API and worker boundary integration points.
  - Validation plan and rollout strategy.
- Out of scope (for this phase):
  - Full refactor of all existing message strings.
  - Distributed tracing vendor integration.
  - Metrics pipeline redesign.

## Target Schema
### Base fields (always present)
- `timestamp` (ISO8601 UTC)
- `level` (`DEBUG|INFO|WARNING|ERROR|CRITICAL`)
- `event` (stable event name)
- `message` (human-readable summary)
- `schema_version` (e.g. `1.0`)
- `service` (e.g. `knowhere-api`, `knowhere-worker`)
- `component` (`api|worker|shared`)
- `environment` (`dev|staging|prod`)
- `logger` (module path)
- `function`
- `line`
- `process_id`
- `thread_id`

### Correlation fields (present, nullable)
- `request_id`
- `correlation_id`
- `trace_id`
- `span_id`
- `user_id`
- `job_id`
- `task_id`

### HTTP context (API only, nullable in worker)
- `http_method`
- `http_path`
- `status_code`
- `duration_ms`

### Exception context (only for failures)
- `error_code` (from `ErrorCode`)
- `http_status`
- `error_category` (`client|system`)
- `exception_class`
- `internal_message` (logs only)
- `user_message` (safe client text)
- `details` (structured, safe subset)
- `original_exception` (`type`, `message`) when wrapped
- `exception.stacktrace` for 5xx / unexpected failures

## Event Naming Convention
- `http.request.start`
- `http.request.complete`
- `exception.client`
- `exception.system`
- `worker.task.start`
- `worker.task.complete`
- `worker.task.retry`
- `worker.task.failure`
- `logging.configured`

Rules:
- Event names are dot-separated and stable.
- `message` can evolve; `event` should not.

## How Structured Logging Works
1. `setup_logging()` configures one shared sink format (JSON by default) and one schema version.
2. Boundary code (API middleware, Celery task entry) sets correlation context once:
   - API: `request_id`, `http_method`, `http_path`, optionally `user_id`
   - Worker: `task_id`, `job_id`, optionally `user_id`
3. Every log call emits:
   - Stable machine key: `event`
   - Human summary: `message`
   - Base fields + context fields
   - If caller does not set `event`, logger uses default `event="app.log"`
   - Caller can override with `logger.bind(event="...")`
4. On exceptions:
   - `KnowhereException.to_log()` contributes canonical error fields (`error_code`, `http_status`, `error_category`, `exception_class`)
   - API/worker handlers emit `exception.client` or `exception.system`
   - 5xx records include stacktrace in logs only
5. API responses remain unchanged in shape and continue to hide internal details.

## Caller Changes (What Changes for Developers)
Minimal caller changes are required at boundaries and exception points.
Preferred pattern for custom fields is `logger.bind(...)`.

### 1) Service bootstrap
Before:
```python
from shared.core.logging import setup_logging
setup_logging()
```

After:
```python
from shared.core.logging import setup_logging
setup_logging(service_name="knowhere-api", component="api")
```

Worker:
```python
setup_logging(service_name="knowhere-worker", component="worker")
```

### 2) API request middleware
Before:
```python
logger.info(f"请求完成: {request.method} {request.url} 状态码: {response.status_code}")
```

After:
```python
from shared.core.logging import log_context

request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
with log_context(
    request_id=request_id,
    correlation_id=request_id,
    http_method=request.method,
    http_path=request.url.path,
):
    logger.bind(event="http.request.start").info("HTTP request started")
    response = await call_next(request)
    logger.bind(
        event="http.request.complete",
        status_code=response.status_code,
        duration_ms=duration_ms
    ).info("HTTP request completed")
```

### 3) Exception handlers (API/Worker)
Before:
```python
logger.bind(**exc.to_log()).error(f"System Error: {exc.code.value} - {exc.internal_message}")
```

After (preferred):
```python
exc.logging()
```

With extra context:
```python
exc.logging(job_id=job_id, task_id=task_id, user_id=user_id)
```

Behavior contract of `exc.logging()`:
- Default log `message` is `internal_message`.
- Structured fields include both `internal_message` and `user_message`.
- Default event/level:
  - 4xx -> `event="exception.client"`, `WARNING`
  - 5xx -> `event="exception.system"`, `ERROR`
- 5xx includes traceback via `opt(exception=exc)`.
- API response payload still uses `user_message` only.

Equivalent expanded form (reference only):
```python
data = exc.to_log()  # contains error_code/http_status/internal_message/user_message/etc.
if exc.http_status_code >= 500:
    logger.bind(event="exception.system", **data).opt(exception=exc).error(exc.internal_message)
else:
    logger.bind(event="exception.client", **data).warning(exc.internal_message)
```

### 4) Worker task boundaries
Before:
```python
logger.info(f"Task started: task_id={self.request.id}, job_id={job_id}")
```

After:
```python
with log_context(task_id=self.request.id, job_id=job_id, user_id=user_id):
    logger.bind(event="worker.task.start").info("Worker task started")
```

### 5) Existing calls can stay unchanged
Current call:
```python
logger.warning(f"WebhookEvent not found: {event_id}")
```

Behavior under new schema:
- Works without rewrite.
- Emits default `event="app.log"`.
- Still includes boundary context (`request_id`, `task_id`, `job_id`, etc.) if set by middleware/task wrapper.

### 6) Developer-provided custom event and extra context
One-off custom event:
```python
logger.bind(
    event="webhook.event.not_found",
    event_id=event_id,
    webhook_id=webhook_id,
).warning("WebhookEvent not found")
```

Reuse same context for multiple lines:
```python
with log_context(task_id=task_id, job_id=job_id, event_id=event_id):
    logger.bind(event="worker.task.start").info("Task started")
    logger.warning("WebhookEvent not found")
```

## Example Log Records
### HTTP success
```json
{
  "timestamp": "2026-03-03T09:21:43.512Z",
  "level": "INFO",
  "event": "http.request.complete",
  "message": "HTTP request completed",
  "schema_version": "1.0",
  "service": "knowhere-api",
  "component": "api",
  "environment": "staging",
  "request_id": "req_123",
  "correlation_id": "req_123",
  "http_method": "POST",
  "http_path": "/api/v1/jobs",
  "status_code": 201,
  "duration_ms": 87
}
```

### Client error (4xx)
```json
{
  "timestamp": "2026-03-03T09:22:01.107Z",
  "level": "WARNING",
  "event": "exception.client",
  "message": "Client Error: INVALID_ARGUMENT - Missing required field source_type",
  "schema_version": "1.0",
  "service": "knowhere-api",
  "component": "api",
  "request_id": "req_124",
  "error_code": "INVALID_ARGUMENT",
  "http_status": 400,
  "error_category": "client",
  "exception_class": "ValidationException"
}
```

### System error (5xx, worker)
```json
{
  "timestamp": "2026-03-03T09:24:10.901Z",
  "level": "ERROR",
  "event": "exception.system",
  "message": "System Error: INTERNAL_ERROR - Failed to create directory: /data/kb_42/job_77",
  "schema_version": "1.0",
  "service": "knowhere-worker",
  "component": "worker",
  "task_id": "celery_abc",
  "job_id": "job_77",
  "error_code": "INTERNAL_ERROR",
  "http_status": 500,
  "error_category": "system",
  "exception_class": "FileSystemException",
  "exception": {
    "type": "PermissionError",
    "message": "[Errno 13] Permission denied"
  }
}
```

## Implementation Plan
### Phase 1: Shared Logging Foundation
1. Centralize schema in `packages/shared-python/shared/core/logging.py`.
2. Add context propagation utilities (`set/clear/context manager`) using `contextvars`.
3. Ensure every emitted line includes base + nullable correlation keys.
4. Keep configurable output format, with structured JSON as default.

### Phase 2: Exception Contract (Priority)
1. Extend `KnowhereException.to_log()` in `packages/shared-python/shared/core/exceptions/knowhere_exception.py`:
   - Include stable error fields (`error_category`, `exception_class`, `http_status`, `error_code`).
   - Preserve current fields for backward compatibility.
2. Define one logging path for exception emission:
   - API global handlers.
   - Worker task failure hooks.
3. Enforce security rule:
   - `internal_message` in logs only.
   - `user_message` in API response only.

### Phase 3: API Integration
1. Update request logging middleware:
   - Generate/propagate `request_id`.
   - Bind request context once per request.
   - Emit start/complete events with latency and status.
2. Update `apps/api/app/core/exception_handlers.py`:
   - Use schema-compliant exception events.
   - Include wrapped exception context for 5xx.
   - Keep current response format unchanged.

### Phase 4: Worker Integration
1. Update shared Celery task boundaries:
   - `on_success`, `on_retry`, `on_failure` emit schema-compliant events.
2. Propagate `task_id`, `job_id`, and `user_id` through task context.
3. Ensure worker exception events mirror API fields for cross-service querying.

### Phase 5: Verification
1. Add tests:
   - `KnowhereException.to_log()` field contract.
   - API exception logs include required schema keys.
   - Worker failure logs include task/job correlation keys.
2. Validate compatibility:
   - Existing error response tests must still pass.
   - Existing log parsers should tolerate additive fields.

## Migration: Existing Logging Invocation
Goal: normalize current logging usage without forcing a full rewrite.

### Migration Rule 1: Remove useless logging
Definition of "useless" in this project:
- Repeated progress noise with no decision value (especially tight-loop debug spam).
- Logs that duplicate adjacent logs with the same meaning.
- Logs that only restate obvious control flow without identifiers/context.
- Success logs for very high-frequency trivial operations where metrics already exist.

Action:
1. Inventory high-volume log locations (API middleware, worker tasks, parser flow, webhook retries).
2. Remove noisy lines first.
3. Keep logs that represent:
   - state transitions
   - external calls (I/O, storage, network, billing)
   - failures/retries/fallbacks
   - completion checkpoints

### Migration Rule 2: Add required context for critical logging
Critical logs must include enough context to trace a failure end-to-end.

Critical categories:
- `ERROR` / `CRITICAL`
- `WARNING` for retry/fallback/security/rate-limit conditions
- business-critical lifecycle logs (`worker.task.start`, `worker.task.complete`, billing events, webhook delivery events)

Required context fields (when available):
- API path: `request_id`, `http_method`, `http_path`, `user_id`
- Worker path: `task_id`, `job_id`, `user_id`
- Exception path: `error_code`, `http_status`, `exception_class`, `internal_message`, `user_message`

Action:
1. Ensure boundary context is set once (`log_context(...)` in middleware/task entry).
2. Ensure critical logs use `logger.bind(event=..., ...)` to attach identifiers.
3. For exceptions, use `exc.logging(...)` so event/level/message and exception fields are standardized.

### Migration Workflow (Practical)
1. Baseline:
   - Capture current log volume and top noisy messages in staging.
2. Cleanup pass:
   - Apply Rule 1 in target modules (`apps/api`, `apps/worker`, shared exception paths).
3. Context pass:
   - Apply Rule 2 for all critical logs.
4. Verify:
   - Confirm every critical log is queryable by `request_id|job_id|task_id|error_code`.
5. Lock-in:
   - Add reviewer checklist item: "no new critical log without required context."

### Baseline Procedure (Kubernetes Staging)

### Staging Sample Findings (2026-03-03)
Top API noise:
- `GET /health` access logs dominate (about 2/3 of API baseline lines).
- Root path `GET /` probe logs are the next largest chunk.

Top worker noise:
- Frequent DeepSeek HTTP request start/completion info lines.
- Parser/debug content dumps (table fragments, progress bars).

Critical context gap observed:
- Worker live window warnings: `total=15`, `with_context=0`, `missing_context=15`.
- This confirms migration Rule 2 is mandatory for warning/error paths.

## Validation Checklist
- Every log line has base schema keys.
- 4xx exceptions log at warning level with `error_category=client`.
- 5xx exceptions log at error level with stacktrace and `error_category=system`.
- API and worker logs are queryable by `request_id|job_id|task_id|error_code`.
- No internal stack or `internal_message` is exposed in API responses.

## Risks and Mitigations
- Risk: field drift between API and worker.
  - Mitigation: one shared schema source in `shared/core/logging.py`.
- Risk: duplicate/verbose exception logs.
  - Mitigation: one canonical exception logging call per boundary.
- Risk: breaking downstream dashboards.
  - Mitigation: additive rollout; keep legacy fields during migration window.

## Deliverables
1. Shared schema utilities in `shared/core/logging.py`.
2. Exception contract update in `KnowhereException`.
3. API middleware + exception handler alignment.
4. Worker task boundary alignment.
5. Basic contract tests and rollout checklist.
