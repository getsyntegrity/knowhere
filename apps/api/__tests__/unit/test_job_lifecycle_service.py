from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.job_lifecycle_service import JobLifecycleService


@pytest.mark.asyncio
async def test_finalize_job_failure_marks_job_refunded_after_idempotent_refund():
    db = AsyncMock()
    service = JobLifecycleService()

    job = SimpleNamespace(
        user_id="user_123",
        credits_charged=100,
        billing_status="charged",
        webhook_enabled=False,
        webhook_url=None,
    )

    service.state_machine.mark_failed = AsyncMock(return_value=True)
    service.job_repo.get_job_by_id = AsyncMock(return_value=job)

    with patch("app.services.job_lifecycle_service.CreditsService") as credits_cls:
        credits_service = MagicMock()
        credits_service.refund_job_credits = AsyncMock(return_value=999)
        credits_cls.return_value = credits_service

        success = await service.finalize_job_failure(
            db=db,
            job_id="job_123",
            error_message="failure",
            error_code="INVALID_ARGUMENT",
            error_details={"reason": "PARSING_FAILED"},
            should_refund=True,
        )

    assert success is True
    assert job.billing_status == "refunded"
    credits_service.refund_job_credits.assert_awaited_once_with(
        session=db,
        user_id="user_123",
        amount=100,
        job_id="job_123",
    )
    db.commit.assert_awaited_once()
