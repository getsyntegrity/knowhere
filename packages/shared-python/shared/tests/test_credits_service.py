import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

os.environ.setdefault("DS_KEY", "test-key")
os.environ.setdefault("DS_URL", "https://example.com")
os.environ.setdefault("S3_BUCKET_NAME", "test-bucket")
os.environ.setdefault("S3_ACCESS_KEY_ID", "test-access-key")
os.environ.setdefault("S3_SECRET_ACCESS_KEY", "test-secret-key")
os.environ.setdefault("S3_TEMP_PATH", "/tmp")
os.environ.setdefault("USERS_DATA_PATH", "/tmp")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/testdb"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TMP_PATH", "/tmp")
os.environ.setdefault("FONT_PATH", "/tmp/font.ttf")
os.environ.setdefault("CHROMEDRIVER_PATH", "/tmp/chromedriver")

from shared.services.billing.credits_service import CreditsService


class _AsyncNullContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return False


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


@pytest.mark.asyncio
async def test_expiration_sweep_preserves_refund_credits():
    session = AsyncMock()
    service = CreditsService()
    service.repository.get_balance = AsyncMock(return_value=700)
    service.repository.get_recent_payment_credits = AsyncMock(return_value=0)
    service.repository.get_positive_credit_total_by_transaction_types = AsyncMock(
        return_value=200
    )
    service._apply_transaction_and_update_balance = AsyncMock(return_value=200)

    expired_amount = await service._check_and_expire_credits(session, "user_123")

    assert expired_amount == 500
    service._apply_transaction_and_update_balance.assert_awaited_once_with(
        session=session,
        user_id="user_123",
        amount=-500,
        transaction_type="expiration",
        description="Credits expired (>365 days old)",
    )


@pytest.mark.asyncio
async def test_ensure_user_initialized_tolerates_concurrent_insert(
    monkeypatch: pytest.MonkeyPatch,
):
    session = MagicMock()
    session.begin_nested.return_value = _AsyncNullContext()
    session.flush = AsyncMock(
        side_effect=IntegrityError("insert", {}, Exception("duplicate"))
    )
    monkeypatch.setattr(
        "shared.services.billing.credits_service.UserBalance",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "shared.services.billing.credits_service.CreditsTransaction",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "shared.services.billing.credits_service.PaymentRecord",
        lambda **kwargs: object(),
    )

    service = CreditsService()
    service.repository.get_user_balance = AsyncMock(side_effect=[None, object()])

    await service.ensure_user_initialized(session, "user_123")
