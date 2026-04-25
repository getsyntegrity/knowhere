import importlib
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from pytest import MonkeyPatch

from tests.support.contract_database import ContractDatabase


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_should_return_the_authenticated_users_initialized_credits_balance(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    async with developer_api_client_factory() as api_client:
        response = await api_client.get("/api/v1/billing/credits")

    assert response.status_code == 200
    assert response.json() == {"credits_balance": 2000.0}


@pytest.mark.asyncio
async def test_should_return_usage_statistics_for_the_requested_period(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    now = _utc_now()

    async with developer_api_client_factory() as api_client:
        await ContractDatabase.insert_credits_transaction(
            transaction_id=str(uuid4()),
            user_id="local-dev-user",
            credits_amount=-1_250_000,
            transaction_type="usage",
            created_at=now - timedelta(days=3),
        )
        await ContractDatabase.insert_credits_transaction(
            transaction_id=str(uuid4()),
            user_id="local-dev-user",
            credits_amount=-500_000,
            transaction_type="usage",
            created_at=now - timedelta(days=2),
        )
        await ContractDatabase.insert_user(user_id="contract-billing-other-user")
        await ContractDatabase.insert_credits_transaction(
            transaction_id=str(uuid4()),
            user_id="contract-billing-other-user",
            credits_amount=-9_000_000,
            transaction_type="usage",
            created_at=now - timedelta(days=1),
        )

        response = await api_client.get(
            "/api/v1/billing/usage",
            params={"period": "month"},
        )

    assert response.status_code == 200

    response_json = cast(dict[str, object], response.json())

    assert response_json["period"] == "month"
    assert response_json["total_credits_used"] == 1.75
    assert response_json["api_calls_count"] == 2
    assert response_json["success_rate"] == 95.0
    assert response_json["average_response_time"] == 0.0
    assert response_json["top_endpoints"] == []


@pytest.mark.asyncio
async def test_should_return_only_the_authenticated_users_transaction_history(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    now = _utc_now()
    newest_transaction_id = str(uuid4())
    older_transaction_id = str(uuid4())

    async with developer_api_client_factory() as api_client:
        await ContractDatabase.insert_credits_transaction(
            transaction_id=older_transaction_id,
            user_id="local-dev-user",
            credits_amount=-1_000_000,
            transaction_type="usage",
            description="Older billing history item",
            created_at=now - timedelta(hours=2),
        )
        await ContractDatabase.insert_credits_transaction(
            transaction_id=newest_transaction_id,
            user_id="local-dev-user",
            credits_amount=2_000_000,
            transaction_type="refund",
            description="Newest billing history item",
            created_at=now - timedelta(hours=1),
        )
        await ContractDatabase.insert_user(user_id="contract-billing-history-other")
        await ContractDatabase.insert_credits_transaction(
            transaction_id=str(uuid4()),
            user_id="contract-billing-history-other",
            credits_amount=-7_000_000,
            transaction_type="usage",
            description="Should be filtered out",
            created_at=now,
        )

        response = await api_client.get("/api/v1/billing/history")

    assert response.status_code == 200

    response_json = cast(list[dict[str, object]], response.json())
    response_ids = [cast(str, item["id"]) for item in response_json]

    assert newest_transaction_id in response_ids
    assert older_transaction_id in response_ids
    assert response_ids.index(newest_transaction_id) < response_ids.index(
        older_transaction_id
    )
    newest_item = next(item for item in response_json if item["id"] == newest_transaction_id)
    assert newest_item["credits_amount"] == 2.0
    assert newest_item["transaction_type"] == "refund"
    assert newest_item["description"] == "Newest billing history item"


@pytest.mark.asyncio
async def test_should_compute_parse_usage_metrics_from_seeded_jobs_and_transactions(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    now = _utc_now()

    async with developer_api_client_factory() as api_client:
        await ContractDatabase.insert_price_config(
            price_id="price_contract_credits_2",
            product_type="credits_package",
            plan_id="credits_2",
            credits_amount=2_000_000,
            amount_cents=400,
        )
        await ContractDatabase.insert_credits_transaction(
            transaction_id=str(uuid4()),
            user_id="local-dev-user",
            credits_amount=-2_000_000,
            transaction_type="usage",
            created_at=now - timedelta(minutes=10),
        )
        await ContractDatabase.insert_credits_transaction(
            transaction_id=str(uuid4()),
            user_id="local-dev-user",
            credits_amount=500_000,
            transaction_type="refund",
            created_at=now - timedelta(minutes=5),
        )
        await ContractDatabase.insert_job(
            job_id=f"job_{uuid4().hex[:12]}",
            user_id="local-dev-user",
            status="done",
            created_at=now - timedelta(seconds=40),
            updated_at=now - timedelta(seconds=30),
        )
        await ContractDatabase.insert_job(
            job_id=f"job_{uuid4().hex[:12]}",
            user_id="local-dev-user",
            status="failed",
            created_at=now - timedelta(seconds=30),
            updated_at=now,
        )
        await ContractDatabase.insert_job(
            job_id=f"job_{uuid4().hex[:12]}",
            user_id="local-dev-user",
            status="pending",
            created_at=now - timedelta(seconds=20),
            updated_at=now - timedelta(seconds=10),
        )

        response = await api_client.get("/api/v1/billing/parse-usage")

    assert response.status_code == 200

    response_json = cast(dict[str, object], response.json())

    assert response_json["request_total"] == 0
    assert response_json["mom_growth"] == 0.0
    assert response_json["credits_used"] == 1.5
    assert response_json["estimated_amount"] == 3.0
    assert response_json["success_rate"] == 50.0
    assert response_json["avg_processing_time"] == 20.0


@pytest.mark.asyncio
async def test_should_split_subscriptions_and_credit_packages_in_price_configs(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
) -> None:
    async with developer_api_client_factory() as api_client:
        await ContractDatabase.insert_price_config(
            price_id="price_contract_plus",
            product_type="subscription",
            plan_id="plus",
            amount_cents=999,
            extra_metadata={
                "display_name": "Plus Plan",
                "description": "Subscription tier",
                "features": ["jobs", "priority"],
                "frontend_config": {"popular": True},
            },
        )
        await ContractDatabase.insert_price_config(
            price_id="price_contract_credits_500",
            product_type="credits_package",
            plan_id="credits_500",
            credits_amount=500_000_000,
            amount_cents=2500,
            extra_metadata={"display_name": "500 Credits"},
        )

        response = await api_client.get("/api/v1/billing/price-configs")

    assert response.status_code == 200

    response_json = cast(dict[str, object], response.json())
    subscriptions = cast(list[dict[str, object]], response_json["subscriptions"])
    credits_packages = cast(list[dict[str, object]], response_json["credits_packages"])

    assert len(subscriptions) == 1
    assert subscriptions[0]["plan_id"] == "plus"
    assert subscriptions[0]["name"] == "Plus Plan"
    assert subscriptions[0]["popular"] is True

    assert len(credits_packages) == 1
    assert credits_packages[0]["plan_id"] == "credits_500"
    assert credits_packages[0]["name"] == "500 Credits"
    assert credits_packages[0]["credits_amount"] == 500.0


@pytest.mark.asyncio
async def test_should_reject_a_missing_stripe_signature_header_for_the_webhook_endpoint(
    api_client_factory: Callable[[], AbstractAsyncContextManager[AsyncClient]],
) -> None:
    async with api_client_factory() as api_client:
        response = await api_client.post("/api/v1/billing/webhook", content=b"{}")

    assert response.status_code == 500
    assert response.headers["x-request-id"]

    response_json = cast(dict[str, object], response.json())
    error = cast(dict[str, object], response_json["error"])

    assert response_json["success"] is False
    assert error["code"] == "INTERNAL_ERROR"
    assert error["message"] == "An internal system error occurred. Please contact support."
    assert error["details"] == {"service": "stripe"}


@pytest.mark.asyncio
async def test_should_return_a_checkout_url_when_buying_a_credit_package(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeStripeService:
        async def create_checkout_session_for_credits_package(
            self,
            db,
            user_id: str,
            price_id: str,
            success_url: str,
            cancel_url: str,
            quantity: int,
            email: str | None = None,
        ) -> str:
            assert user_id == "local-dev-user"
            assert price_id == "price_contract_package"
            assert quantity == 2
            assert email == "local-dev-user@knowhere.local"
            assert success_url.endswith("type=credits_package")
            assert cancel_url.endswith("canceled=true")
            return "https://checkout.stripe.test/session/contract-package"

    async with developer_api_client_factory() as api_client:
        billing_module = importlib.import_module("app.api.v1.routes.billing")
        monkeypatch.setattr(billing_module, "StripeService", FakeStripeService)
        response = await api_client.post(
            "/api/v1/billing/buy-credits-package",
            json={"price_id": "price_contract_package", "quantity": 2},
        )

    assert response.status_code == 200
    assert response.json() == {
        "checkout_url": "https://checkout.stripe.test/session/contract-package",
        "session_id": "",
    }


@pytest.mark.asyncio
async def test_should_return_a_payment_intent_payload_when_buying_credits(
    developer_api_client_factory: Callable[
        [], AbstractAsyncContextManager[AsyncClient]
    ],
    monkeypatch: MonkeyPatch,
) -> None:
    class FakeStripeService:
        async def create_payment_intent(
            self,
            user_id: str,
            amount: int,
            credits_amount: int,
            currency: str = "usd",
        ) -> dict[str, str]:
            assert user_id == "local-dev-user"
            assert amount == 700
            assert credits_amount == 350_000_000
            assert currency == "cny"
            return {
                "client_secret": "pi_contract_secret",
                "payment_intent_id": "pi_contract_id",
            }

    async with developer_api_client_factory() as api_client:
        billing_module = importlib.import_module("app.api.v1.routes.billing")
        monkeypatch.setattr(billing_module, "StripeService", FakeStripeService)
        response = await api_client.post(
            "/api/v1/billing/buy-credits",
            json={"credits_amount": 350},
        )

    assert response.status_code == 200
    assert response.json() == {
        "client_secret": "pi_contract_secret",
        "payment_intent_id": "pi_contract_id",
    }
