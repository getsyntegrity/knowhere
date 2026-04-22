from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.local_dev_bootstrap_service import LocalDevelopmentBootstrapService
from shared.models.database.api_key import APIKey
from shared.models.database.credits_transaction import CreditsTransaction
from shared.models.database.payment_record import PaymentRecord
from shared.models.database.user import User
from shared.models.database.user_balance import UserBalance


class _EngineBeginContext:
    def __init__(self, connection: AsyncMock) -> None:
        self._connection = connection

    async def __aenter__(self) -> AsyncMock:
        return self._connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


@pytest.mark.asyncio
async def test_ensure_user_table_exists_creates_minimal_local_user_table(monkeypatch) -> None:
    service = LocalDevelopmentBootstrapService()
    connection = AsyncMock()

    monkeypatch.setattr(
        "scripts.local_dev_bootstrap_service.engine",
        SimpleNamespace(begin=lambda: _EngineBeginContext(connection)),
    )

    await service.ensure_user_table_exists()

    statement = connection.execute.await_args.args[0]
    rendered = str(statement)
    assert 'CREATE TABLE IF NOT EXISTS "user"' in rendered
    assert "name VARCHAR(255) NOT NULL" in rendered
    assert "email TEXT NULL" in rendered


@pytest.mark.asyncio
async def test_seed_local_developer_upserts_deterministic_highest_tier_identity() -> None:
    service = LocalDevelopmentBootstrapService()
    session = AsyncMock()
    session.add = MagicMock()
    session.get = AsyncMock(side_effect=[None, None, None, None, None])

    await service.seed_local_developer(session)

    added_objects = [call.args[0] for call in session.add.call_args_list]

    user = next(obj for obj in added_objects if isinstance(obj, User))
    balance = next(obj for obj in added_objects if isinstance(obj, UserBalance))
    payment = next(obj for obj in added_objects if isinstance(obj, PaymentRecord))
    transaction = next(obj for obj in added_objects if isinstance(obj, CreditsTransaction))
    api_key = next(obj for obj in added_objects if isinstance(obj, APIKey))

    assert user.id == LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID
    assert user.name == LocalDevelopmentBootstrapService.LOCAL_DEV_USER_NAME
    assert user.email == LocalDevelopmentBootstrapService.LOCAL_DEV_USER_EMAIL

    assert balance.user_id == LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID
    assert balance.user_tier == LocalDevelopmentBootstrapService.LOCAL_DEV_TIER
    assert (
        balance.credits_balance
        == LocalDevelopmentBootstrapService.LOCAL_DEV_CREDITS_BALANCE
    )

    assert payment.user_id == LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID
    assert payment.status == "succeeded"
    assert (
        payment.credits_amount
        == LocalDevelopmentBootstrapService.LOCAL_DEV_LIFETIME_BILLING_MICRO
    )

    assert transaction.user_id == LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID
    assert (
        transaction.credits_amount
        == LocalDevelopmentBootstrapService.LOCAL_DEV_CREDITS_BALANCE
    )
    assert transaction.transaction_type == "local_dev_seed"

    assert api_key.user_id == LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID
    assert api_key.name == "local-dev-full-access"
    assert api_key.enabled_modules == ["all"]
    assert api_key.key_mask.startswith(
        LocalDevelopmentBootstrapService.LOCAL_DEV_API_KEY[:8]
    )


@pytest.mark.asyncio
async def test_seed_local_developer_updates_existing_rows_without_duplicates() -> None:
    service = LocalDevelopmentBootstrapService()
    session = AsyncMock()
    session.add = MagicMock()

    user = User(
        id=LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID,
        name="Old Name",
        email="old@example.com",
    )
    balance = UserBalance(
        user_id=LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID,
        credits_balance=1,
        user_tier="free",
    )
    payment = PaymentRecord(
        id="local-dev-seed-payment-record",
        user_id=LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID,
        payment_type="credits_package",
        amount_cents=1,
        currency="USD",
        status="failed",
    )
    transaction = CreditsTransaction(
        id="local-dev-seed-credit-entry",
        user_id=LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID,
        credits_amount=1,
        transaction_type="usage",
    )
    api_key = APIKey(
        id="local-dev-default-api-key",
        user_id=LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID,
        key_hash="old-hash",
        key_mask="old-mask",
        name="old-name",
        enabled_modules=["guest"],
    )
    session.get = AsyncMock(
        side_effect=[user, balance, payment, transaction, api_key]
    )

    await service.seed_local_developer(session)

    session.add.assert_not_called()

    assert user.id == LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID
    assert user.name == LocalDevelopmentBootstrapService.LOCAL_DEV_USER_NAME
    assert user.email == LocalDevelopmentBootstrapService.LOCAL_DEV_USER_EMAIL

    assert balance.user_id == LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID
    assert balance.user_tier == LocalDevelopmentBootstrapService.LOCAL_DEV_TIER
    assert (
        balance.credits_balance
        == LocalDevelopmentBootstrapService.LOCAL_DEV_CREDITS_BALANCE
    )

    assert payment.user_id == LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID
    assert payment.status == "succeeded"
    assert (
        payment.credits_amount
        == LocalDevelopmentBootstrapService.LOCAL_DEV_LIFETIME_BILLING_MICRO
    )

    assert transaction.user_id == LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID
    assert (
        transaction.credits_amount
        == LocalDevelopmentBootstrapService.LOCAL_DEV_CREDITS_BALANCE
    )
    assert transaction.transaction_type == "local_dev_seed"

    assert api_key.user_id == LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID
    assert api_key.enabled_modules == ["all"]
