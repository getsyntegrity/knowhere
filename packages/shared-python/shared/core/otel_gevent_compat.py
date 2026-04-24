"""
Workaround for OTel context.detach() under gevent.

CeleryInstrumentor's signal handlers call attach() and detach() in different
greenlets — a fundamental mismatch with gevent's greenlet-local contextvars.
There is no upstream fix for this (see open-telemetry/opentelemetry-python#2606).

Suppressing the ValueError is a pragmatic choice: span creation and export are
independent of detach(), and the unpopped context is GC'd with the greenlet.
"""

import contextvars

import opentelemetry.context
from opentelemetry.context import Context

_original_detach = opentelemetry.context.detach


def _safe_detach(token: contextvars.Token[Context]) -> None:
    try:
        _original_detach(token)
    except ValueError:
        pass  # greenlet context mismatch — span still exported


def patch_otel_context_for_gevent() -> None:
    """Patch opentelemetry.context.detach to tolerate greenlet context switches."""
    opentelemetry.context.detach = _safe_detach
