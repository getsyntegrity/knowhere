"""Rule-based policy for agentic retrieval.

Determines the next action based on current state and budget constraints.
v1 is purely rule-based — no LLM planning, no learned policy.
"""
from __future__ import annotations

from shared.services.retrieval.agentic.types import ActionType, AgentRunConfig, AgentState


class RuleBasedPolicy:
    """Stateless decision function: (state, config) → next action or None.

    Returning None means the agent loop should stop and proceed to
    the fixed terminal step (hydrate_and_rank).
    """

    def decide(self, state: AgentState, config: AgentRunConfig) -> ActionType | None:
        # ── Step 1: Always start with bottom_discovery ──
        if not state.discovery_done:
            return ActionType.BOTTOM_DISCOVERY

        # ── Step 2: KG document selection ──
        if not state.kg_done and state.doc_retry_count < config.max_doc_retries:
            return ActionType.KG_DOCUMENT_SELECT

        # ── Step 3: Pending doc_nav section drills (progressive expansion) ──
        if state.nav_drill_stack:
            if state.path_expansion_count < config.max_path_expansions:
                return ActionType.NAV_SECTION_SELECT

        # ── Step 4: Process selected documents one by one ──
        if state.selected_docs and state.pending_doc_index < len(state.selected_docs):
            # max_docs=0 means no limit — LLM decides autonomously
            if config.max_docs == 0 or state.pending_doc_index < config.max_docs:
                return ActionType.DOCUMENT_PATH_SELECT

        # ── Step 5: Handle need_more_docs (go back to KG select) ──
        if (
            state.last_observation
            and state.last_observation.status == 'need_more_docs'
            and state.doc_retry_count < config.max_doc_retries
        ):
            return ActionType.KG_DOCUMENT_SELECT

        # ── Step 6: If no docs selected at all, try GREP as fallback ──
        if not state.selected_docs and state.kg_done and state.doc_retry_count == 0:
            return ActionType.GREP_DOCUMENT_DISCOVER

        # ── Done: proceed to hydrate_and_rank ──
        return None
