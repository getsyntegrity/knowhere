"""
Compatibility shim for OpenTelemetry context under gevent.

gevent's monkey-patched contextvars uses greenlet-local storage, so OTel
tokens created in one greenlet cannot be detached in another. The resulting
ValueError is harmless — spans are still created and exported correctly —
but it pollutes logs on every Celery task completion.

This module patches context.detach() to silently swallow that specific error.
"""

import opentelemetry.context

_original_detach = opentelemetry.context.detach


def _safe_detach(token: object) -> None:
    try:
        _original_detach(token)
    except ValueError:
        pass  # greenlet context mismatch — span already exported


def patch_otel_context_for_gevent() -> None:
    """Patch opentelemetry.context.detach to tolerate greenlet context switches."""
    opentelemetry.context.detach = _safe_detach
