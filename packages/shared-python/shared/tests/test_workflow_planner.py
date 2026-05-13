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

from shared.services.retrieval.agentic.budget import BudgetLedger
from shared.services.retrieval.workflow.planner import QueryPlanner


@pytest.mark.asyncio
async def test_planner_parses_multi_step_plan():
    async def llm(_prompt):
        return """
        {
          "reasoning_summary": "compare two years then synthesize",
          "steps": [
            {"id": "s1", "sub_query": "2024 market size", "step_kind": "retrieve", "depends_on": [], "output_role": "consumed_by_synthesis"},
            {"id": "s2", "sub_query": "2025 market size", "step_kind": "retrieve", "depends_on": [], "output_role": "consumed_by_synthesis"},
            {"id": "s3", "sub_query": "compare s1 and s2", "step_kind": "synthesize", "depends_on": ["s1", "s2"], "output_role": "final_part"}
          ],
          "final_strategy": "last_synthesize"
        }
        """

    planner = QueryPlanner(
        llm_fn=llm,
        planner_ledger=BudgetLedger(total=4000, planning_ratio=0.0, bootstrap=4000),
        max_steps=5,
        total_budget=200000,
        per_step_budget=40000,
    )
    plan = await planner.plan(query="compare 2024 and 2025")

    assert len(plan.steps) == 3
    assert plan.steps[2].depends_on == ["s1", "s2"]
    assert plan.final_strategy == "last_synthesize"


@pytest.mark.asyncio
async def test_planner_falls_back_to_single_step_on_bad_json():
    async def llm(_prompt):
        return "not json"

    planner = QueryPlanner(
        llm_fn=llm,
        planner_ledger=None,
        max_steps=5,
        total_budget=200000,
        per_step_budget=40000,
    )
    plan = await planner.plan(query="hello")

    assert plan.planner_status == "fallback"
    assert len(plan.steps) == 1
    assert plan.steps[0].sub_query == "hello"


@pytest.mark.asyncio
async def test_planner_falls_back_when_too_many_steps():
    async def llm(_prompt):
        return {
            "steps": [
                {"id": f"s{i}", "sub_query": f"q{i}", "step_kind": "retrieve", "depends_on": [], "output_role": "final_part"}
                for i in range(1, 7)
            ],
            "final_strategy": "concat_final_parts",
        }.__repr__().replace("'", '"')

    planner = QueryPlanner(
        llm_fn=llm,
        planner_ledger=None,
        max_steps=3,
        total_budget=200000,
        per_step_budget=40000,
    )
    plan = await planner.plan(query="too broad")

    assert plan.planner_status == "fallback"
    assert len(plan.steps) == 1
