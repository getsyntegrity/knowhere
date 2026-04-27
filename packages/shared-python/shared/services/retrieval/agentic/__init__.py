"""Agentic retrieval orchestration for Knowhere.

Upgrades the retrieval pipeline from a fixed sequence to a state/action/observation
loop with explicit tool selection, budget controls, and trajectory recording.

All tools are thin wrappers around existing retrieval components — no new retrieval
algorithms, ranking strategies, or prompts are introduced.
"""
