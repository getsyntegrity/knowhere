import os
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("DS_KEY", "test-key")
os.environ.setdefault("DS_URL", "https://example.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("S3_ACCESS_KEY_ID", "test-access-key")
os.environ.setdefault("S3_SECRET_ACCESS_KEY", "test-secret-key")
os.environ.setdefault("S3_TEMP_PATH", "/tmp")
os.environ.setdefault("USERS_DATA_PATH", "/tmp")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/testdb")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TMP_PATH", "/tmp")
os.environ.setdefault("FONT_PATH", "/tmp/font.ttf")
os.environ.setdefault("CHROMEDRIVER_PATH", "/tmp/chromedriver")

from shared.services.billing.credits_service import CreditsService


@pytest.mark.asyncio
async def test_refund_job_credits_returns_current_balance_when_already_refunded():
    session = AsyncMock()
    duplicate_refund_result = MagicMock()
    duplicate_refund_result.first.return_value = object()
    session.execute = AsyncMock(return_value=duplicate_refund_result)

    service = CreditsService()
    service.repository.get_balance = AsyncMock(return_value=123456)
    service.add_credits = AsyncMock()

    balance = await service.refund_job_credits(
        session=session,
        user_id="user_123",
        amount=100,
        job_id="job_123",
    )

    assert balance == 123456
    service.repository.get_balance.assert_awaited_once_with(session, "user_123")
    service.add_credits.assert_not_awaited()
