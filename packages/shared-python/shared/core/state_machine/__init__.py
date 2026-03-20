"""
State machine package — shared between API and Worker.

Exports:
- ``AsyncStateMachineService`` — for FastAPI (async DB sessions)
- ``SyncStateMachineService``  — for Celery worker (sync / gevent)
- ``JobStatus``                — canonical status enum
- ``is_valid_transition``      — transition validation helper
- ``is_upload_expired``        — upload expiry check
"""
from shared.core.state_machine.states import (
    JobStatus,
    get_state_timeout,
    is_terminal_state,
    is_valid_transition,
)
from shared.core.state_machine.upload_expiry import is_upload_expired

__all__ = [
    "JobStatus",
    "get_state_timeout",
    "is_terminal_state",
    "is_valid_transition",
    "is_upload_expired",
]