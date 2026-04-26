"""
API-side state machine facade.

Core transition logic lives in ``shared.core.state_machine.service``. This
module keeps the ``JobStateMachine`` entry point that API code already uses.
"""

from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from shared.core.state_machine.service import AsyncStateMachineService
from shared.services.redis import RedisServiceFactory


class JobStateMachine:
    """Compatibility facade over ``AsyncStateMachineService``."""

    def __init__(self, redis_service: Optional[Any] = None) -> None:
        self.redis = redis_service or RedisServiceFactory.get_service()
        self.state_machine = AsyncStateMachineService(self.redis)

    async def transition(
        self,
        db: AsyncSession,
        job_id: str,
        to_state: str,
        transition_reason: str = "normal_transition",
        operator_id: Optional[str] = None,
        operator_type: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
        auto_commit: bool = True,
    ) -> bool:
        """Execute a CAS-protected state transition."""
        try:
            return await self.state_machine.transition(
                db=db,
                job_id=job_id,
                to_state=to_state,
                transition_reason=transition_reason,
                operator_id=operator_id,
                operator_type=operator_type,
                metadata=metadata,
                auto_commit=auto_commit,
            )
        except Exception as err:
            logger.error(f"Job {job_id} transition failed: {err}")
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
                db=db,
                job_id=job_id,
                error_message=error_message,
                error_code=error_code,
                error_details=error_details,
                operator_id=operator_id,
                metadata=metadata,
                auto_commit=auto_commit,
            )
        except Exception as err:
            logger.error(f"Failed to mark Job {job_id} as failed: {err}")
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
                db=db,
                job_id=job_id,
                result_metadata=result_metadata,
                operator_id=operator_id,
                auto_commit=auto_commit,
            )
        except Exception as err:
            logger.error(f"Failed to mark Job {job_id} as completed: {err}")
            return False

    async def handle_retry(
        self,
        db: AsyncSession,
        job_id: str,
        retry_metadata: Optional[Dict[str, Any]] = None,
        operator_id: Optional[str] = None,
    ) -> bool:
        """Retry a job through the shared state machine."""
        try:
            return await self.state_machine.handle_retry(
                db=db,
                job_id=job_id,
                retry_metadata=retry_metadata,
                operator_id=operator_id,
            )
        except Exception as err:
            logger.error(f"Failed to retry Job {job_id}: {err}")
            return False

    async def get_current_state(
        self,
        db: AsyncSession,
        job_id: str,
    ) -> Optional[str]:
        """Read the current state through the shared service."""
        try:
            return await self.state_machine.get_current_state(db=db, job_id=job_id)
        except Exception as err:
            logger.error(f"Failed to read Job {job_id} state: {err}")
            return None
