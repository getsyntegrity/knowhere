# Design

## 1. Goal

*   **DX Friendly:** Easy to understand error messages and predictable structures for SDK consumers.
*   **Documented:** Strongly typed error codes that can be exported for SDK.
*   **Reliable:** Clear distinction between retriable and non-retriable errors.

## 2. The 3 Rules of API Errors

1.  **Be Explicit**: Never return a generic "Error". Return `invalid_parameter` vs `missing_parameter`.
2.  **Machine Readable**: Use a consistent JSON schema. Clients shouldn't have to parse HTML error pages.
3.  **Security First**: Don't leak stack traces or internal DB IDs in 500 errors.

## 3. The "4xx vs 5xx" Message Rule (Security)

This is a **CRITICAL** security pattern that prevents information leakage while maintaining good developer experience.

### The Problem

When developers throw exceptions, exposing raw error messages to users creates two problems:

1.  **Security Leaks**: A developer might accidentally return `"Connect to 192.168.0.5 failed"`, exposing internal network structure.
2.  **Inconsistency**: One developer writes `"System Error"`, another writes `"Oops, something went wrong"`.

### The Solution: Dual-Message Pattern

Every `KnowhereException` has two message fields:

| Field | Purpose | Who Writes It | Where It Goes |
|-------|---------|---------------|---------------|
| `internal_message` | Technical details for debugging | Developer | **Logs ONLY** |
| `user_message` | Safe, user-friendly message | Developer (4xx) or System (5xx) | **API Response** |

### For 4xx Errors (Client Fault) → Developer Writes `user_message`

Since the user caused the error (e.g., invalid input, file too big), the message must be specific so they can fix it.

```python
# Developer code:
raise ValidationException(
    user_message="The file 'data.csv' is too large (max 5MB).",
    violations=[{"field": "file", "description": "Exceeds 5MB limit"}]
)

# User sees: "The file 'data.csv' is too large (max 5MB)."  ✅ Helpful
```

### For 5xx Errors (System Fault) → System Auto-Sanitizes

Since the system failed (e.g., disk full, DB down), the user cannot fix it. Providing details is a security risk.

```python
# Developer code:
raise FileSystemException(
    internal_message="Permission denied: cannot write to /var/lib/worker/tmp",
    operation="write"
)

# User sees: "An internal system error occurred. Please contact support."  ✅ Safe
# Logs see: "Permission denied: cannot write to /var/lib/worker/tmp"  ✅ Debuggable
```

### Key Rules

1.  **`internal_message` is NEVER returned to the client**, regardless of HTTP status code.
2.  **5xx errors auto-default** to `"An internal system error occurred. Please contact support."` if no `user_message` provided.
3.  **4xx domain exceptions require `user_message`** as a parameter (enforced by constructor).
4.  **Developers focus on debugging**: Write technically accurate `internal_message` for 5xx errors; the system handles user-facing sanitization.

## 4. Error Categories

We will categorize errors into three main domains to distinguish between client-side issues, system failures, and business logic violations.

| Category | Description | HTTP Status | Retry Strategy |
| :--- | :--- | :--- | :--- |
| **System Errors** | Unexpected internal failures (DB down, Network, Bug). | 500, 502, 504 | Exp. Backoff |
| **Business Errors** | Valid request format but violates business rules (e.g., balance check). | 400, 402, 403, 404, 409 | No Retry (usually) |
| **Request Errors** | API contract violations (Auth, Validation, Method). | 400, 401, 403, 405, 415 | No Retry |
| **Flow Control** | Rate limiting, Quota exhaustion, Load shedding. | 429, 503 | Exp. Backoff + Jitter |

## 5. Error Codes (The Source of Truth)

We will adopt a **Canonical Error Code** system (similar to Google `google.rpc.Code` but adapted).
The `code` field in the API response will be a **String Enum** (not integer) to be self-documenting.

**Example Codes:**
*   `INVALID_ARGUMENT`
*   `UNAUTHENTICATED`
*   `PERMISSION_DENIED`
*   `RESOURCE_NOT_FOUND`
*   `RESOURCE_EXHAUSTED` (Quota/RateLimit)
*   `INTERNAL_ERROR`
*   `UNAVAILABLE` (Upstream/Maintenance)
*   `DEADLINE_EXCEEDED` (Timeout)

## 6. Error Objects (API Contract)

We will use a standard "Envelope" structure for reliability and ease of parsing.

```json
{
  "success": false,
  "error": {
    "code": "RESOURCE_EXHAUSTED",
    "message": "You have exceeded your RPM limit of 60.",
    "request_id": "req_89vh123",
    "details": {
      "reason": "RATE_LIMIT_EXCEEDED",
      "quota_limit": 60,
      "quota_period": "minute",
      "retry_after": 15
    }
  }
}
```

*   **code**: (Required) The canonical string error code.
*   **message**: (Required) A human-readable English message.
*   **request_id**: (Required) For tracing and support.
*   **details**: (Optional) Structured data specific to the error type.

## 7. HTTP Status Mapping

While we define internal canonical codes, they must map predictably to HTTP standards along with correct headers (e.g., `Retry-After`).

*   `INVALID_ARGUMENT` -> **400 Bad Request**
*   `UNAUTHENTICATED` -> **401 Unauthorized**
*   `PERMISSION_DENIED` -> **403 Forbidden**
*   `RESOURCE_NOT_FOUND` -> **404 Not Found**
*   `RESOURCE_EXHAUSTED` -> **429 Too Many Requests** (add `Retry-After` header)
*   `INTERNAL_ERROR` -> **500 Internal Server Error**
*   `UNAVAILABLE` -> **503 Service Unavailable** (add `Retry-After` header)
*   `DEADLINE_EXCEEDED` -> **504 Gateway Timeout**

## 8. Monitors and Observability

*   **Logging:** All 5xx errors must be logged with `ERROR` level and full stack trace. 4xx errors logged as `WARNING` or `INFO`.
*   **Metrics:** Track `error_count` tagged by `error_code` and `service`.
*   **Tracing:** Ensure `request_id` is propagated to downstream services (DB, Redis, LLM providers).




# Implementation

## 1. Overview

**Key Components:**
1.  `ErrorCode`: Canonical string enums.
2.  `KnowhereException`: Base class for all system exceptions.
3.  `GlobalExceptionHandler`: Middleware to capture and format errors uniformly.

## 2. Directory Structure

We will implement this primarily in the `shared-python` package to ensure it's available to all apps (worker, api, etc.).

```
packages/shared-python/shared/core/
├── exceptions/
│   ├── __init__.py
│   ├── KnowhereException.py        <-- [NEW] Base Exception
│   ├── DomainExceptions.py         <-- [NEW] Specific Exceptions (Validation, Auth, etc.)
└── response/
    ├── __init__.py
    └── ErrorCode.py                <-- [NEW] Canonical Codes
```

## 3. Existing Exception Analysis

A comprehensive search of the codebase reveals the current state of exception handling:

1.  **`RequestException` (Shared)**:
    *   Defined in `packages/shared-python/shared/core/exceptions/RequestException.py`.
    *   **Status**: Unused. No references found in `apps/worker` or `apps/api`.
    *   **Action**: Remove to reduce technical debt.

2.  **`AuthError` (API App)**:
    *   Defined in `apps/api/app/core/dependencies.py` as `class AuthError(Exception)`.
    *  **Status**: Unused.
    *   **Action**: Remove to reduce technical debt.

3.  **Standard Exceptions**:
    *   `ValueError`: Used exclusively for logic/validation errors (e.g., `price_id` not found).
    *   `HTTPException` (FastAPI): Widely used in API routes for 404/401 responses.
    *   `Exception`: Caught broadly in some services (e.g., `_authenticate_api_key`). some are potentially swallowing errors, Need to identify and fix.

4.  **Goal**: Unify these into the new `KnowhereException` hierarchy to ensure consistent JSON logging and response formatting.

## 4. Communication & Data Flow

The system has two main error propagation paths:

1.  **Synchronous API Errors**:
    *   Client -> API Gateway (FastAPI) -> `exception_handlers.py` -> JSON Response.
    *   Currently returns `{"detail": "...", "status_code": ...}`.
    *   **Goal**: Return `{"success": false, "error": { "code": ..., "message": ... }}`.

2.  **Asynchronous Worker Errors**:
    *   API -> RabbitMQ -> Worker (`kb_tasks.py`).
    *   Worker catches Exception -> `message_publisher.publish_failure` -> RabbitMQ (`job_failure` queue).
    *   API (`message_consumer.py`) -> Consumes `job_failure` -> Updates DB/Socket.
    *   **Goal**: Worker raises `KnowhereException` -> Serializes to `publish_failure` metadata -> API consumes and logs structured error.

## 5. Step-by-Step Implementation

### Step 1: Define Canonical Error Codes

Create `packages/shared-python/shared/core/response/ErrorCode.py`.
Use `StrEnum` (Python 3.11+) or `Enum` with string values.

```python
from enum import Enum

class ErrorCode(str, Enum):
    # Standard Errors
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    NOT_FOUND = "NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNAVAILABLE = "UNAVAILABLE"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    
    # Domain specific can be added here but prefer using Details for sub-codes
    # e.g. PAYMENT_REQUIRED = "PAYMENT_REQUIRED"
```

### Step 2: Implement Base Exception Class

Create `packages/shared-python/shared/core/exceptions/KnowhereException.py`.

```python
from typing import Any, Dict, Optional
from shared.core.response.ErrorCode import ErrorCode

class KnowhereException(Exception):
    """
    Base class for all Knowhere API exceptions.
    Adheres to the 3 Golden Rules: Explicit, Machine Readable, Security First.
    """
    def __init__(
        self, 
        code: ErrorCode, 
        message: str, 
        details: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
        http_status_code: int = 500
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.original_exception = original_exception
        self.http_status_code = http_status_code

    def to_dict(self, request_id: str) -> Dict[str, Any]:
        """
        Returns a machine-readable JSON representation.
        """
        return {
            "success": False,
            "error": {
                "code": self.code.value,
                "message": self.message,
                "request_id": request_id,
                "details": self.details
            }
        }
```

### Step 3: Implement Domain Exceptions

Create `packages/shared-python/shared/core/exceptions/DomainExceptions.py`.

```python
from typing import Any, Dict, Optional
from shared.core.exceptions.KnowhereException import KnowhereException
from shared.core.response.ErrorCode import ErrorCode

class ValidationException(KnowhereException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            code=ErrorCode.INVALID_ARGUMENT,
            message=message,
            details=details,
            http_status_code=400
        )

class AuthException(KnowhereException):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            code=ErrorCode.UNAUTHENTICATED,
            message=message,
            http_status_code=401
        )

class PermissionException(KnowhereException):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            code=ErrorCode.PERMISSION_DENIED,
            message=message,
            http_status_code=403
        )

class NotFoundException(KnowhereException):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message=f"{resource} not found",
            details={"resource": resource, "id": resource_id},
            http_status_code=404
        )

class RateLimitException(KnowhereException):
    def __init__(self, retry_after: int):
        super().__init__(
            code=ErrorCode.RESOURCE_EXHAUSTED,
            message="Rate limit exceeded",
            details={"retry_after": retry_after},
            http_status_code=429
        )
```

### Step 4: Remove Legacy RequestException & AuthError

**Action**: Delete `packages/shared-python/shared/core/exceptions/RequestException.py`.

Since analysis confirms it is not actively used in the codebase, we will remove it entirely rather than refactoring it.
Any future "Request" related errors should use `KnowhereException` or a specific subclass like `ValidationException`.

```bash
rm packages/shared-python/shared/core/exceptions/RequestException.py
```

### Step 5: Global Exception Handler (API)

**Action**: Modify `apps/api/app/core/exception_handlers.py` to use `GlobalExceptionHandler` logic.
We will maintain the `setup_exception_handlers` pattern but delegate to the new `KnowhereException` formatting logic.

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from shared.core.exceptions.KnowhereException import KnowhereException
from shared.core.response.ErrorCode import ErrorCode
import uuid
import logging

logger = logging.getLogger(__name__)

async def knowhere_exception_handler(request: Request, exc: KnowhereException):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    if exc.http_status_code >= 500:
        logger.error(f"System Error {request_id}: {exc.message} \n{exc.details}")
    else:
        logger.warning(f"Business Error {request_id}: {exc.message}")
    
    return JSONResponse(
        status_code=exc.http_status_code,
        content=exc.to_dict(request_id)
    )

async def general_exception_handler(request: Request, exc: Exception):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    logger.error(f"Unhandled Exception {request_id}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": ErrorCode.INTERNAL_ERROR,
                "message": "An internal server error occurred.",
                "request_id": request_id
            }
        }
    )

def setup_exception_handlers(app):
    app.add_exception_handler(KnowhereException, knowhere_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
```

### Step 6: Worker Error Handling

**Action**: Update `apps/worker/app/core/tasks/kb_tasks.py`.
Catch `KnowhereException` and pass specific error codes to `publish_failure`.

```python
    except KnowhereException as e:
        # Use structured error info
        await message_publisher.publish_failure(
            job_id=job_id,
            error_message=e.message,
            error_code=e.code.value,  # New field in publish_failure? Or metadata
            metadata={"details": e.details},
            # ...
        )
        raise
```

## 6. Verification

1.  **Unit Tests:** Verify `to_dict` output matches the schema.
2.  **Integration:** Trigger `RateLimitException` and verify `429` status + `retry_after` in details.
3.  **Security:** Trigger a `ZeroDivisionError` and ensure response is generic `INTERNAL_ERROR` 500 while logs show the full stack trace.



# Error Codes


## 1. Canonical Error Codes

We adopt the standard gRPC error model mapped to HTTP status codes.

| Error Code | HTTP Status | Description | Retryable |
|------------|-------------|-------------|-----------|
| `OK` | 200 | Success | No |
| `INVALID_ARGUMENT` | 400 | Client specified an invalid argument. Check error details. | No |
| `FAILED_PRECONDITION` | 400 | System is not in a state required for the operation (e.g., directory not empty). | No |
| `OUT_OF_RANGE` | 400 | Operation was attempted past the valid range. | No |
| `UNAUTHENTICATED` | 401 | Missing or invalid authentication credentials. | Yes (after auth) |
| `PERMISSION_DENIED` | 403 | Caller does not have permission for the operation. | No |
| `NOT_FOUND` | 404 | A requested entity (file, directory, user) was not found. | No |
| `ABORTED` | 409 | Concurrency conflict (e.g., read-modify-write race). | Yes |
| `ALREADY_EXISTS` | 409 | Entity already exists (e.g., file name collision). | No |
| `RESOURCE_EXHAUSTED` | 429 | Quota or rate limit exceeded. | Yes (Backoff) |
| `CANCELLED` | 499 | Request cancelled by the client. | No |
| `DATA_LOSS` | 500 | Unrecoverable data loss or corruption. | No |
| `UNKNOWN` | 500 | Unknown error. Default for unhandled exceptions. | No |
| `INTERNAL_ERROR` | 500 | Internal server invariants broken (e.g., logic bug). | No |
| `NOT_IMPLEMENTED` | 501 | API method not implemented by the server. | No |
| `UNAVAILABLE` | 503 | Service unavailable (e.g., Redis/DB down). | Yes |
| `DEADLINE_EXCEEDED` | 504 | Request deadline exceeded. | Yes |

## 2. Decision Guide

**Rule of Thumb:** Always use the **Canonical Error Code** for the top-level `code` field. This determines the HTTP status and the client's retry strategy.

*   **Do NOT** create specific codes like `REDIS_ERROR` or `DB_CONNECTION_FAILED` that expose infrastructure internals.
*   **DO** use `UNAVAILABLE` and provide context in the log or `details`.

**Why?**
*   **Security**: Leaking "Redis" expands attack surface.
*   **Coupling**: Switching to Memcached shouldn't break clients.
*   **Actionability**: Clients can only "Retry", they can't fix Redis.

### Example: Redis Connection Failed
*   **Wrong**: `code: "REDIS_ERROR"`, `status: 500`
*   **Correct**: `code: "UNAVAILABLE"`, `status: 503`
    *   **Why?** The client doesn't care *why* it's unavailable (Redis vs DB), only that they should **retry** later.

### Example: PDF Parse Failed
*   **Wrong**: `code: "PDF_PARSE_ERROR"`, `status: 400`
*   **Correct**: `code: "INVALID_ARGUMENT"`, `status: 400`
    *   **Details**: `{"reason": "MALFORMED_PDF", "location": "header"}`

### 2.1 Debugging Generic Codes (The Trace ID Pattern)

If clients only see `UNAVAILABLE`, how do we debug? **Bridge the gap with a Request ID.**

**The Workflow:**
1.  Generate UUID (`req_abc123`) for every request.
2.  Log specific internal error tagged with UUID.
3.  Return Generic Code + UUID to client.

**Client View (Public):**
```json
// HTTP 503
{
  "error": {
    "code": "UNAVAILABLE",
    "message": "Service temporarily unavailable.",
    "request_id": "req_59283019283"
  }
}
```

**Internal Log (Datadog/Splunk):**
```json
{
  "level": "ERROR",
  "request_id": "req_59283019283",
  "error_code": "REDIS_CONNECTION_TIMEOUT",
  "stack_trace": "Redis::CannotConnectError..."
}
```

## 3. Existing Exception Mapping Examples

This table maps existing codebase exceptions (from `apps/api`, `apps/worker`, `shared`) to the new canonical codes.

### Authentication & Authorization (Apps/API)

| Existing Exception | Location | Target Code | Notes |
|-------------------|----------|-------------|-------|
| `HTTPException(401)` | `app/middleware/auth_middleware.py` | `UNAUTHENTICATED` | Missing/Invalid Token |
| `AuthError` | `app/core/dependencies.py` | `UNAUTHENTICATED` | User auth failure |
| `HTTPException(403)` | `app/core/permissions.py` | `PERMISSION_DENIED` | Role/Scope mismatch |
| `ValueError("Invalid audience")` | `app/services/auth/google.py` | `UNAUTHENTICATED` | OAuth validation fail |

### Validation & Requests (Apps/API & Shared)

| Existing Exception | Location | Target Code | Notes |
|-------------------|----------|-------------|-------|
| `ValueError("Unsupported task type")` | `app/services/messaging` | `INVALID_ARGUMENT` | |
| `ValueError("Invalid path...")` | `shared/services/common` | `INVALID_ARGUMENT` | |
| `RequestException` | `shared/.../RequestException.py` | *REMOVE* | Replace with specific |
| `RequestValidationError` | FastAPI Default | `INVALID_ARGUMENT` | Pydantic validation |
| `ValueError("path must be abs")` | `user_config_service.py` | `FAILED_PRECONDITION` | Server config issue |

### Resource Management (Apps/API)

| Existing Exception | Location | Target Code | Notes |
|-------------------|----------|-------------|-------|
| `HTTPException(404)` | `app/routers/...` | `NOT_FOUND` | User/Job/File not found |
| `Exception("Unable to get lock")` | `concurrency_control_service.py` | `ABORTED` | Lock contention |
| `Exception("Retry limit exceeded")` | `concurrency_control_service.py` | `RESOURCE_EXHAUSTED` | Or `ABORTED` |
| `Exception("Failed to get job lock")` | `concurrency_control_service.py` | `ABORTED` | Job concurrency |

### Worker & Processing (Apps/Worker)

| Existing Exception | Location | Target Code | Notes |
|-------------------|----------|-------------|-------|
| `TimeoutError` | `pdf_parser.py` | `DEADLINE_EXCEEDED` | PDF parsing timeout |
| `Exception("MinerU API Error")` | `pdf_parser.py` | `UNAVAILABLE` | External dependency down |
| `ValueError("File size exceed")` | `kb_tasks.py` | `INVALID_ARGUMENT` | File too large |
| `ValueError("Unsupported file type")` | `kb_tasks.py` | `INVALID_ARGUMENT` | |
| `Exception("PDF parsing failed")` | `pdf_parser.py` | `INTERNAL_ERROR` | Parser crash/failure |
| `ValueError("S3 file verification failed")` | `kb_tasks.py` | `NOT_FOUND` | S3 consistency issue |
| `Exception("只能返回html或者md")` | `knowledge_base_service.py` | `INVALID_ARGUMENT` | Unsupported doc type |
| `Exception("Path mismatch...")` | `kb_encoder_service.py` | `INTERNAL_ERROR` | Data consistency error |

### External Dependencies (AI & Payment)

| Existing Exception | Location | Target Code | Notes |
|-------------------|----------|-------------|-------|
| `Exception("STRIPE_SECRET_KEY...")` | `stripe_service.py` | `FAILED_PRECONDITION` | Missing Env Config |
| `Exception("Invalid payload/signature")` | `stripe_service.py` | `INVALID_ARGUMENT` | Webhook Validation |
| `Exception("创建支付会话失败")` | `stripe_service.py` | `UNAVAILABLE` | Stripe API Error |
| `Exception("AI返回结果为空")` | `DeepSeekClient.py` | `INTERNAL_ERROR` | Model Provider Issue |
| `Exception("API请求失败")` | `DeepSeekClient.py` | `UNAVAILABLE` | AI API Down |
| `Exception("Celery任务失败")` | `ai_query_service.py` | `INTERNAL_ERROR` | Async Task Failure |

### Infrastructure & System (Shared/System)

| Existing Exception | Location | Target Code | Notes |
|-------------------|----------|-------------|-------|
| `RuntimeError("Event loop closed")` | `kb_tasks.py` | `INTERNAL_ERROR` | Asyncio lifecycle bug |
| `ValueError("USERS_DATA_PATH...")` | `user_config_service.py` | `FAILED_PRECONDITION` | Server misconfiguration |
| `Exception("无法创建数据目录...")` | `user_directory_service.py` | `INTERNAL_ERROR` | Filesystem Permissions |
| `Exception("Database migration failed")` | `main.py` | `INTERNAL_ERROR` | Startup failure |
| `Exception("无法确保存储桶存在")` | `file_upload_service.py` | `INTERNAL_ERROR` | S3 Configuration |
| `Exception("从S3下载文件失败")` | `file_upload_service.py` | `UNAVAILABLE` | Network/S3 Issue |


Related Issues:
https://github.com/Ontos-AI/knowhere-api/issues/11