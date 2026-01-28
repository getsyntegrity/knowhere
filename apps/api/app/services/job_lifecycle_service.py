"""
Job Lifecycle Service
Encapsulates complex transaction logic for Job completion and failure.
Ensures atomicity of Job Result/Status, KB Records, and Webhook Event creation (Transactional Outbox Pattern).
"""
from typing import Any, Dict, List, Optional
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.job_repository import JobRepository
from app.repositories.job_result_repository import JobResultRepository
from app.repositories.knowledge_base_repository import create_update_kb
from app.services.state_machine.manager import JobStateMachine
from app.services.webhook_service import get_webhook_service
from app.services.email.job_email_service import JobEmailService
from app.services.billing.credits_service import CreditsService

from shared.models.schemas.messages import JobResultMessage
from shared.models.database.knowledge_base import KBPydantic
from shared.services.redis import RedisServiceFactory
from shared.services.redis.chunks_redis_service import ChunksRedisService


class JobLifecycleService:
    """
    Manages the lifecycle transitions of a Job (Completion, Failure).
    Handles Transaction Boundaries (Unit of Work).
    """

    def __init__(self):
        self.state_machine = JobStateMachine()
        self.job_result_repo = JobResultRepository()
        self.job_repo = JobRepository()

    async def finalize_job_success(
        self,
        db: AsyncSession,
        message: JobResultMessage,
        chunks: List[Dict[str, Any]],
        inline_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Finalize a successful job:
        1. Save KB Records (if any)
        2. Save JobResult & Chunks
        3. Update Job Status (DONE)
        4. Create Webhook Event
        5. COMMIT (Atomic)
        6. Post-Commit: Publish Webhook, Email, Clear Redis
        """
        job_id = message.job_id
        logger.info(f"Finalizing job success: job_id={job_id}")

        try:
            # 1. Save KB Records (No Commit)
            if message.kb_records:
                kb_records = [KBPydantic(**rec) for rec in message.kb_records]
                if kb_records:
                    await create_update_kb(kb_records, db=db)
                    logger.info(f"Job {job_id} KB records prepared for commit: count={len(kb_records)}")

            # 2. Upsert JobResult (No Commit)
            job_result = await self.job_result_repo.upsert_job_result(
                db,
                job_id=job_id,
                delivery_mode=message.delivery_mode,
                document_metadata=None,
                inline_payload=inline_payload,
                result_s3_key=message.result_s3_key,
                result_size=message.zip_size
            )

            # 3. Save Chunks (No Commit)
            await self.job_result_repo.replace_chunks(db, job_result.id, chunks)

            # 4. Mark Completed in State Machine (No Commit)
            await self.state_machine.mark_completed(
                db,
                job_id,
                {
                    "storage_completed": True,
                    "stored_count": message.stored_count,
                    "delivery_mode": message.delivery_mode
                },
                auto_commit=False  # Defer commit
            )

            # 5. Prepare Webhook Event (No Commit)
            webhook_event = None
            job = await self.job_repo.get_job_by_id(db, job_id)
            webhook_url = getattr(job, "webhook_url", None)
            
            if job and job.webhook_enabled and webhook_url:
                webhook_service = get_webhook_service()
                webhook_event = await webhook_service.create_job_completion_event(
                    db=db,
                    job_id=job_id,
                    webhook_url=webhook_url
                )

            # 6. ATOMIC COMMIT (The Unit of Work)
            await db.commit()
            logger.info(f"Job {job_id} transaction committed successfully.")

            # 7. Post-Commit Side Effects
            
            # 7a. Clear Redis Chunks
            try:
                redis_service = RedisServiceFactory.get_service()
                chunks_redis_service = ChunksRedisService(redis_service)
                await chunks_redis_service.delete_chunks(message.chunks_job_id)
            except Exception as e:
                logger.warning(f"Failed to clear chunks from Redis for {job_id}: {e}")

            # 7b. Publish Webhook (Best Effort)
            if webhook_event:
                try:
                    webhook_service = get_webhook_service()
                    await webhook_service.publish_to_queue(webhook_event.id)
                except Exception as e:
                    logger.error(f"Failed to publish completion webhook (Event persisted): {e}")

            # 7c. Send Email (Best Effort)
            await self._send_completion_email(db, job_id, job_result)

            return {
                "status": "success",
                "job_id": job_id,
                "stored_count": message.stored_count
            }

        except Exception as e:
            logger.error(f"Failed to finalize job success {job_id}: {e}")
            await db.rollback()
            raise e

    async def finalize_job_failure(
        self,
        db: AsyncSession,
        job_id: str,
        error_message: str,
        error_code: str,
        error_details: Optional[Dict[str, Any]],
        should_refund: bool = False,
        refund_amount: float = 0
    ) -> bool:
        """
        Finalize a failed job:
        1. Mark Failed
        2. Refund Credits (if needed)
        3. Create Webhook Event
        4. COMMIT (Atomic)
        5. Publish Webhook & Send Email
        """
        logger.info(f"Finalizing job failure: job_id={job_id}")
        
        try:
            # 1. Mark Failed (No Commit)
            await self.state_machine.mark_failed(
                db,
                job_id,
                error_message,
                error_code=error_code,
                error_details=error_details,
                auto_commit=False
            )

            # 2. Refund Credits (No Commit logic)
            job = await self.job_repo.get_job_by_id(db, job_id)
            
            if should_refund:
                amount_to_refund = refund_amount
                if amount_to_refund <= 0 and job:
                    amount_to_refund = getattr(job, "credits_charged", 0) or 0
                
                if amount_to_refund > 0:
                    billing_status = getattr(job, "billing_status", "")
                    if billing_status != "refunded":
                        credits_service = CreditsService()
                        await credits_service.refund_job_credits(
                            db,
                            user_id=str(job.user_id),
                            amount=amount_to_refund,
                            job_id=job_id
                        )
                        logger.info(f"Refunded {amount_to_refund} credits for job {job_id}")

            # 3. Prepare Webhook (No Commit)
            webhook_event = None
            # Need fresh reference if changed by refund? refund_job_credits might flush updates to 'job' instance if attached.
            # safe to ensure job is attached.
            if job and job.webhook_enabled and job.webhook_url:
                webhook_service = get_webhook_service()
                webhook_event = await webhook_service.create_job_failure_event(
                    db=db, 
                    job_id=job_id,
                    error_message=error_message,
                    error_type="JobFailure",
                    error_code=error_code,
                    error_details=error_details,
                    webhook_url=job.webhook_url
                )

            # 4. ATOMIC COMMIT
            await db.commit()
            logger.info(f"Job {job_id} failure transaction committed.")

            # 5. Post-Commit Actions
            if webhook_event:
                try:
                    webhook_service = get_webhook_service()
                    await webhook_service.publish_to_queue(webhook_event.id)
                except Exception as e:
                    logger.error(f"Failed to publish failure webhook: {e}")

            await self._send_failure_email(db, job_id, error_message)

            return True

        except Exception as e:
            logger.error(f"Failed to finalize job failure {job_id}: {e}")
            await db.rollback()
            raise e

    async def _send_completion_email(self, db: AsyncSession, job_id: str, job_result: Any):
        """Send job completion email (Best effort)"""
        try:
            from shared.models.database.user import User
            from sqlalchemy import select
            
            # Re-fetch or reuse job. db is now clean (new transaction or same session after commit).
            # Accessing properties should be safe.
            job = await self.job_repo.get_job_by_id(db, job_id)
            if not job: 
                return

            result = await db.execute(select(User).where(User.id == job.user_id))
            user = result.scalar_one_or_none()
            
            if user and user.email:
                email_service = JobEmailService()
                await email_service.send_job_completion_email(
                    db=db,
                    job_id=job_id,
                    job_result=job_result,
                    user_email=user.email,
                    user_name=getattr(user, 'full_name', None) or user.email,
                    job_type=job.job_type or "kb_management"
                )
        except Exception as e:
            logger.error(f"Failed to send job completion email: {e}")
        
    async def _send_failure_email(self, db: AsyncSession, job_id: str, error_message: str):
        """Send job failure email (Best effort)"""
        try:
            from shared.models.database.user import User
            from sqlalchemy import select
            
            job = await self.job_repo.get_job_by_id(db, job_id)
            if not job:
                return

            result = await db.execute(select(User).where(User.id == job.user_id))
            user = result.scalar_one_or_none()
            
            if user and user.email:
                email_service = JobEmailService()
                await email_service.send_job_failure_email(
                    db=db,
                    job_id=job_id,
                    user_email=user.email,
                    error_message=error_message,
                    user_name=getattr(user, 'full_name', None) or user.email,
                    job_type=job.job_type or "kb_management"
                )
        except Exception as e:
            logger.error(f"Failed to send job failure email: {e}")
