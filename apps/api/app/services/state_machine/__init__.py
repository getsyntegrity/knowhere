"""
API-side compatibility layer for the shared state machine.

The canonical implementation now lives under ``shared.core.state_machine``.
This package keeps stable imports for API callers while avoiding duplicate
state machine logic inside ``apps/api``.
"""
from shared.core.state_machine.service import AsyncStateMachineService
from shared.core.state_machine.states import JobStatus

from .manager import JobStateMachine

StateMachineService = AsyncStateMachineService

__all__ = [
    "AsyncStateMachineService",
    "JobStateMachine",
    "JobStatus",
    "StateMachineService",
]
