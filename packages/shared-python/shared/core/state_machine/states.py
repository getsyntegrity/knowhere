"""State-machine statuses and transition rules."""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Set


class JobStatus(str, Enum):
    """PRD job status enum."""

    PENDING = "pending"
    WAITING_FILE = "waiting-file"
    RUNNING = "running"
    CONVERTING = "converting"
    DONE = "done"
    FAILED = "failed"


# Terminal states.
TERMINAL_STATES: Set[str] = {JobStatus.DONE.value, JobStatus.FAILED.value}


def is_terminal_state(state: str) -> bool:
    """Return whether the given state is terminal."""
    return state in TERMINAL_STATES


# Valid state transitions — prevents illegal jumps (e.g. done → running).
# Any transition to FAILED is always allowed (not listed per-state).
VALID_TRANSITIONS: Dict[str, Set[str]] = {
    JobStatus.PENDING.value: {JobStatus.RUNNING.value, JobStatus.WAITING_FILE.value},
    JobStatus.WAITING_FILE.value: {JobStatus.PENDING.value},
    JobStatus.RUNNING.value: {JobStatus.CONVERTING.value, JobStatus.DONE.value},
    JobStatus.CONVERTING.value: {JobStatus.DONE.value},
    JobStatus.DONE.value: set(),
    JobStatus.FAILED.value: {JobStatus.PENDING.value},  # retry
}


def is_valid_transition(from_state: str, to_state: str) -> bool:
    """Check whether a state transition is allowed.

    Transitions to FAILED are always valid from any non-terminal state.
    """
    if from_state == to_state:
        return True
    if to_state == JobStatus.FAILED.value:
        return from_state not in TERMINAL_STATES
    allowed = VALID_TRANSITIONS.get(from_state, set())
    return to_state in allowed


def is_job_expired(created_at: datetime | None, max_age_seconds: int) -> bool:
    """Return True if a job has exceeded its maximum allowed life.

    Args:
        created_at: Job creation timestamp (tz-aware or naive-UTC).
        max_age_seconds: Maximum allowed age in seconds.
            If <= 0, expiry checking is disabled.

    Returns:
        True when the job should be considered expired.
    """
    if max_age_seconds <= 0 or created_at is None:
        return False

    created_utc = (
        created_at.replace(tzinfo=timezone.utc)
        if created_at.tzinfo is None
        else created_at
    )
    age = (datetime.now(timezone.utc) - created_utc).total_seconds()
    return age > max_age_seconds
