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

from shared.services.retrieval.workflow.synthesizer import compose_final_answer
from shared.services.retrieval.workflow.types import PlannedStep, QueryPlan, StepResult


def test_compose_final_answer_concat_final_parts():
    plan = QueryPlan(
        original_query="q",
        steps=[
            PlannedStep(id="s1", sub_query="q1", output_role="final_part"),
            PlannedStep(id="s2", sub_query="q2", output_role="intermediate"),
            PlannedStep(id="s3", sub_query="q3", output_role="final_part"),
        ],
        final_strategy="concat_final_parts",
    )
    results = {
        "s1": StepResult("s1", "q1", "retrieve", [], "final_part", answer_text="A1"),
        "s2": StepResult("s2", "q2", "retrieve", [], "intermediate", answer_text="A2"),
        "s3": StepResult("s3", "q3", "retrieve", [], "final_part", answer_text="A3"),
    }

    assert compose_final_answer(plan, results) == "A1\n\nA3"


def test_compose_final_answer_last_synthesize():
    plan = QueryPlan(
        original_query="q",
        steps=[
            PlannedStep(id="s1", sub_query="q1", output_role="consumed_by_synthesis"),
            PlannedStep(id="s2", sub_query="q2", step_kind="synthesize", depends_on=["s1"], output_role="final_part"),
        ],
        final_strategy="last_synthesize",
    )
    results = {
        "s1": StepResult("s1", "q1", "retrieve", [], "consumed_by_synthesis", answer_text="A1"),
        "s2": StepResult("s2", "q2", "synthesize", ["s1"], "final_part", answer_text="FINAL"),
    }

    assert compose_final_answer(plan, results) == "FINAL"


def test_query_plan_topological_batches():
    plan = QueryPlan(
        original_query="q",
        steps=[
            PlannedStep(id="s1", sub_query="q1"),
            PlannedStep(id="s2", sub_query="q2"),
            PlannedStep(id="s3", sub_query="q3", step_kind="synthesize", depends_on=["s1", "s2"]),
        ],
    )

    batches = plan.topological_batches()

    assert [step.id for step in batches[0]] == ["s1", "s2"]
    assert [step.id for step in batches[1]] == ["s3"]
