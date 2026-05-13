"""Agentic retrieval orchestration for Knowhere.

Navigate-then-answer loop:
  Phase 1: Document selection (discovery + KG LLM select)
  Phase 2: Per-document iterative navigation (navigate_step — unified action)
  Phase 3: attempt_answer → DONE (return answer) or NOT_FOUND → revision

Each navigate_step decides action (NAVIGATE/STOP), optional asset tools,
and section selections in a single LLM call. STOP terminates drill-down.
After navigation, attempt_answer is called automatically — its result
(answer or NOT_FOUND+reason) drives the revision loop.

All tools are thin wrappers around existing retrieval components — no new
retrieval algorithms, ranking strategies, or prompts are introduced.
"""
