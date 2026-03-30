import os
from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

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

from shared.core.exceptions.domain_exceptions import InsufficientCreditsException
from shared.services.billing.credits_sync_service import SyncCreditsService


def test_refund_job_credits_returns_current_balance_when_already_refunded() -> None:
    session = MagicMock()
    duplicate_refund_result = MagicMock()
    duplicate_refund_result.first.return_value = object()
    session.execute.return_value = duplicate_refund_result

    service = SyncCreditsService()
    service.repository.get_balance = MagicMock(return_value=123456)
    service.add_credits = MagicMock()

    balance = service.refund_job_credits(
        session=session,
        user_id="user_123",
        amount=100,
        job_id="job_123",
    )

    assert balance == 123456
    service.repository.get_balance.assert_called_once_with(session, "user_123")
    service.add_credits.assert_not_called()


def test_deduct_credits_raises_when_balance_is_too_low() -> None:
    session = MagicMock()
    service = SyncCreditsService()
    service.ensure_user_initialized = MagicMock()
    service._check_and_expire_credits = MagicMock()
    service.get_balance = MagicMock(return_value=99)
    service._apply_transaction_and_update_balance = MagicMock()

    with pytest.raises(InsufficientCreditsException) as exc_info:
        service.deduct_credits(
            session=session,
            user_id="user_123",
            amount=100,
            reason="Document processing",
        )

    assert exc_info.value.details["required_credits"] == 100
    assert exc_info.value.details["current_balance"] == 99
    service._apply_transaction_and_update_balance.assert_not_called()


def test_expiration_sweep_preserves_refund_credits() -> None:
    session = MagicMock()
    service = SyncCreditsService()
    service.repository.get_balance = MagicMock(return_value=700)
    service.repository.get_recent_payment_credits = MagicMock(return_value=0)
    service.repository.get_positive_credit_total_by_transaction_types = MagicMock(
        return_value=200
    )
    service._apply_transaction_and_update_balance = MagicMock(return_value=200)

    expired_amount = service._check_and_expire_credits(session, "user_123")

    assert expired_amount == 500
    service._apply_transaction_and_update_balance.assert_called_once_with(
        session=session,
        user_id="user_123",
        amount=-500,
        transaction_type="expiration",
        description="Credits expired (>365 days old)",
    )


def test_ensure_user_initialized_tolerates_concurrent_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = MagicMock()
    session.begin_nested.return_value = nullcontext()
    session.flush.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
    monkeypatch.setattr(
        "shared.services.billing.credits_sync_service.UserBalance",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "shared.services.billing.credits_sync_service.CreditsTransaction",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        "shared.services.billing.credits_sync_service.PaymentRecord",
        lambda **kwargs: object(),
    )

    service = SyncCreditsService()
    service.repository.get_user_balance = MagicMock(side_effect=[None, object()])

    service.ensure_user_initialized(session, "user_123")
