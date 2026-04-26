"""
Retryable Exceptions for Celery Tasks.

This module defines which exceptions should trigger automatic retries in Celery tasks.
Only TRANSIENT errors that may succeed on retry should be included here.

Principle:
- 4xx errors (ValidationException, NotFoundException) → NEVER retry (user must fix input)
- 5xx transient errors (timeout, service unavailable) → RETRY with backoff
- 5xx permanent errors (code bugs, config errors) → NEVER retry (developer must fix)
"""

from shared.core.exceptions.domain_exceptions import (
    LLMServiceException,
    MinerUServiceException,
    RedisServiceException,
    StorageServiceException,
    TimeoutException,
    UnavailableException,
)

# Transient errors that may succeed on retry
RETRYABLE_EXCEPTIONS = (
    # Domain exceptions (5xx transient)
    TimeoutException,  # Network/service timeout
    UnavailableException,  # Service temporarily down
    LLMServiceException,  # LLM API transient failures
    StorageServiceException,  # S3/MinIO transient failures
    RedisServiceException,  # Redis transient failures
    MinerUServiceException,  # MinerU service transient failures
)
