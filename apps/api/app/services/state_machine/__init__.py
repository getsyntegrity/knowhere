"""
State machine service module (API-side facade).

The core state machine logic now lives in ``shared.core.state_machine``.
This module re-exports the symbols that API code expects so that existing
``from app.services.state_machine import ...`` statements keep working.
"""
from shared.core.state_machine.states import JobStatus
from shared.core.state_machine.service import AsyncStateMachineService

from .concurrency_control_service import ConcurrencyControlService
from .manager import JobStateMachine
from .monitoring_service import StateMachineMonitoringService
from .state_sync_service import StateSyncService
from .state_timeout_service import StateTimeoutService

# Backwards-compatible alias
StateMachineService = AsyncStateMachineService

__all__ = [
    "JobStateMachine",
    "AsyncStateMachineService",
    "StateMachineService",
    "StateSyncService",
    "StateTimeoutService",
    "ConcurrencyControlService",
    "StateMachineMonitoringService",
    "JobStatus",
]
