"""
State machine package — shared between API and Worker.

Exports:
- ``AsyncStateMachineService`` — for FastAPI (async DB sessions)
- ``SyncStateMachineService``  — for Celery worker (sync / gevent)
- ``JobStatus``                — canonical status enum
- ``is_valid_transition``      — transition validation helper
- ``is_job_expired``           — global job expiry check
"""
from shared.core.state_machine.states import (
    JobStatus,
    get_state_timeout,
    is_terminal_state,
    is_valid_transition,
    is_job_expired,
)

__all__ = [
    "JobStatus",
    "get_state_timeout",
    "is_terminal_state",
    "is_valid_transition",
    "is_job_expired",
]