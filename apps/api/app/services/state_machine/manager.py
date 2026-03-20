"""
Job state machine manager — thin facade over shared state machine + timeout listener.

Callers use ``JobStateMachine`` as the single entry point for state transitions.
Core logic lives in ``shared.core.state_machine.service.AsyncStateMachineService``.
"""
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.state_machine.service import AsyncStateMachineService


class JobStateMachine:
    """Thin facade: delegates transitions to shared service, manages timeout listener."""

    def __init__(self, redis_service=None):
        self.redis = redis_service or RedisServiceFactory.get_service()
        self.state_machine = AsyncStateMachineService(self.redis)

    # ── State transitions ───────────────────────────────────────────────

    async def transition(
        self,
        db: AsyncSession,
        job_id: str,
        to_state: str,
        transition_reason: str = "normal_transition",
        operator_id: Optional[str] = None,
        operator_type: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Execute a CAS-protected state transition."""
        try:
            return await self.state_machine.transition(
                db, job_id, to_state, transition_reason,
                operator_id, operator_type, metadata,
            )
        except Exception as e:
            logger.error(f"Job {job_id} transition failed: {e}")
            return False

    async def mark_failed(
        self,
        db: AsyncSession,
        job_id: str,
        error_message: str,
        error_code: str = "UNKNOWN",
        error_details: Optional[Dict[str, Any]] = None,
        operator_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auto_commit: bool = True,
    ) -> bool:
        """Mark a job as failed."""
        try:
            return await self.state_machine.mark_failed(
                db, job_id, error_message, error_code,
                error_details, operator_id, metadata,
                auto_commit=auto_commit,
            )
        except Exception as e:
            logger.error(f"Failed to mark Job {job_id} as failed: {e}")
            return False

    async def mark_completed(
        self,
        db: AsyncSession,
        job_id: str,
        result_metadata: Optional[Dict[str, Any]] = None,
        operator_id: Optional[str] = None,
        auto_commit: bool = True,
    ) -> bool:
        """Mark a job as completed."""
        try:
            return await self.state_machine.mark_completed(
                db, job_id, result_metadata, operator_id,
                auto_commit=auto_commit,
            )
        except Exception as e:
            logger.error(f"Failed to mark Job {job_id} as completed: {e}")
            return False