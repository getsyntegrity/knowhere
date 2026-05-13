from __future__ import annotations

import os

os.environ.setdefault("DS_KEY", "test")
os.environ.setdefault("DS_URL", "https://example.com")
os.environ.setdefault("S3_BUCKET_NAME", "test")
os.environ.setdefault("S3_ACCESS_KEY_ID", "test")
os.environ.setdefault("S3_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("S3_TEMP_PATH", "/tmp")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://root:root123@localhost:5432/Knowhere")
os.environ.setdefault("TMP_PATH", "/tmp")

import pytest

from shared.services.retrieval.workflow.types import PlannedStep, QueryPlan
from shared.services.retrieval.workflow.wallet import BudgetWallet


@pytest.mark.asyncio
async def test_wallet_allocates_ledgers_per_step():
    plan = QueryPlan(
        original_query="q",
        steps=[
            PlannedStep(id="s1", sub_query="q1", step_kind="retrieve"),
            PlannedStep(id="s2", sub_query="q2", step_kind="synthesize", depends_on=["s1"]),
        ],
    )
    wallet = BudgetWallet(
        total=50000,
        per_retrieve_step_default=40000,
        per_synthesize_step_default=6000,
    )

    ledgers = await wallet.allocate(plan)

    assert set(ledgers) == {"s1", "s2"}
    assert wallet.snapshot()["allocated"] == 46000


@pytest.mark.asyncio
async def test_wallet_scales_down_under_total_cap():
    plan = QueryPlan(
        original_query="q",
        steps=[
            PlannedStep(id="s1", sub_query="q1", step_kind="retrieve"),
            PlannedStep(id="s2", sub_query="q2", step_kind="retrieve"),
            PlannedStep(id="s3", sub_query="q3", step_kind="synthesize", depends_on=["s1", "s2"]),
        ],
    )
    wallet = BudgetWallet(
        total=30000,
        per_retrieve_step_default=40000,
        per_synthesize_step_default=6000,
    )

    await wallet.allocate(plan)
    snapshot = wallet.snapshot()

    assert snapshot["allocated"] <= 30000
    assert snapshot["allocations"]["s1"] >= 4000
    assert snapshot["allocations"]["s3"] >= 1500


@pytest.mark.asyncio
async def test_wallet_reclaim_records_unused_capacity():
    plan = QueryPlan(
        original_query="q",
        steps=[PlannedStep(id="s1", sub_query="q1", step_kind="retrieve")],
    )
    wallet = BudgetWallet(
        total=40000,
        per_retrieve_step_default=40000,
        per_synthesize_step_default=6000,
    )
    ledgers = await wallet.allocate(plan)

    await wallet.reclaim("s1", ledgers["s1"])

    assert wallet.snapshot()["reclaimed"]["s1"] == 40000
