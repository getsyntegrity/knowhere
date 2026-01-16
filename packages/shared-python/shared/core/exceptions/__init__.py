"""Exceptions module for shared exception classes."""

from shared.core.exceptions.knowhere_exception import KnowhereException
from shared.core.exceptions.domain_exceptions import (
    ValidationException,
    AuthException,
    PermissionDeniedException,
    NotFoundException,
    ConflictException,
    RateLimitException,
    QuotaExceededException,
    UnavailableException,
    TimeoutException,
    UnknownException,
)

__all__ = [
    # Base (do not raise directly)
    "KnowhereException",
    # Client Errors (4xx)
    "ValidationException",
    "AuthException",
    "PermissionDeniedException",
    "NotFoundException",
    "ConflictException",
    "RateLimitException",
    "QuotaExceededException",
    # Server Errors (5xx)
    "UnavailableException",
    "TimeoutException",
    "UnknownException",
]

