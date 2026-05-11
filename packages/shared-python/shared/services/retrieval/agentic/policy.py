"""LLM-driven policy for agentic retrieval.

Replaces the former RuleBasedPolicy.  All control decisions are made by a
small LLM call so the agent can adapt to query complexity and KB topology
rather than following a fixed rule tree.

Design:
  - ``LLMPolicy.decide()`` is **async** — it calls the LLM to pick the
    next action.
  - On parse failure the agent terminates immediately (no hidden fallback).
  - The prompt is compact: no raw chunk content, only state metadata.
"""
from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from shared.services.retrieval.agentic.types import ActionType, AgentRunConfig, AgentState
from shared.services.retrieval.llm_adapter import LLMFn

# ── Available actions presented to the LLM ───────────────────────────────────

# NOTE: BOTTOM_DISCOVERY is intentionally excluded from this list.
# It is now a mandatory pre-step executed automatically by the orchestrator
# before the LLM decision loop begins.  The LLM should never need to decide
# whether to run it — doing so wastes one LLM call per run.
_AVAILABLE_ACTIONS: list[dict[str, Any]] = [
    {
        'action': ActionType.KG_DOCUMENT_SELECT.value,
        'description': (
            'Ask the LLM to select the most relevant documents from the Knowledge Graph '
            'overview (doc summaries). Use after discovery.'
        ),
        'when': 'discovery_done is true, kg_done is false',
    },
    {
        'action': ActionType.DOCUMENT_PATH_SELECT.value,
        'description': (
            'Drill into the next pending document\'s section tree and pick relevant '
            'paths. The document is chosen automatically from selected_docs[pending_doc_index].'
        ),
        'when': 'kg_done is true, there are pending documents to process',
    },
    {
        'action': ActionType.GREP_DOCUMENT_DISCOVER.value,
        'description': (
            'Run term/grep search across all documents to discover relevant doc IDs '
            'when KG selection found nothing.'
        ),
        'when': 'kg_done is true but selected_docs is empty',
    },
    {
        'action': ActionType.GRAPH_EXPAND_DOCS.value,
        'description': (
            'Expand via Knowledge Graph edge relationships to find related documents '
            'not yet selected.'
        ),
        'when': 'Optional deepening — use when current results seem insufficient',
    },
    {
        'action': ActionType.DONE.value,
        'description': (
            'Stop the agent loop and proceed to final hydration and ranking. '
            'Use when you have sufficient evidence paths or the budget is nearly exhausted.'
        ),
        'when': 'Sufficient paths collected, or further actions would not improve results',
    },
]

_ACTIONS_BLOCK = '\n'.join(
    f"  {i+1}. \"{a['action']}\": {a['description']} [{a['when']}]"
    for i, a in enumerate(_AVAILABLE_ACTIONS)
)

_POLICY_PROMPT_TEMPLATE = """\
You are a retrieval agent orchestrating document search for a RAG system.
Your job: choose the SINGLE best next action given the current state.

QUERY: "{query}"

CURRENT STATE:
{state_json}

BUDGET: {elapsed_ms}ms elapsed of {budget_ms}ms max | Step {step} of {max_steps}

AVAILABLE ACTIONS:
{actions_block}

RULES:
1. Run kg_document_select when discovery_done is true and kg_done is false.
2. After kg select, run document_path_select for each pending document.
3. Call done when all pending documents are processed OR you have >= {min_evidence} evidence paths.
4. Only use grep_document_discover if kg_document_select found 0 documents.
5. Only use graph_expand_docs if you need more related docs after reviewing results.
Note: bottom_discovery is already executed automatically before this loop — do NOT attempt to call it.

Return ONLY a JSON object, no markdown, no explanation:
{{"action": "<action_name>", "reason": "<one sentence why>"}}
"""


def _parse_action_from_response(response: str) -> dict[str, Any] | None:
    """Extract the JSON decision object from the LLM response."""
    # Strip markdown code fences if present
    text = response.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    text = text.strip()

    # Try to extract {...} block
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Try the whole text as JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


class LLMPolicy:
    """Async LLM-driven policy.  One LLM call per agent step.

    Usage::

        policy = LLMPolicy(llm_fn)
        action_type, reason = await policy.decide(state, config, query=query)
    """

    def __init__(self, llm_fn: LLMFn, *, query: str = '') -> None:
        self._llm_fn = llm_fn
        self._query = query

    def build_prompt(self, state: AgentState, config: AgentRunConfig) -> str:
        """Build the decision prompt.  Public for test inspection."""
        state_data = state.state_summary()
        
        has_pending_docs = state.pending_doc_index < len(state.selected_docs)
        state_data['has_pending_docs'] = has_pending_docs
        state_json = json.dumps(state_data, ensure_ascii=False, indent=2)

        allowed_actions = []
        for action in _AVAILABLE_ACTIONS:
            name = action['action']
            if name == ActionType.KG_DOCUMENT_SELECT.value and (not state.discovery_done or state.kg_done):
                continue
            if name == ActionType.DOCUMENT_PATH_SELECT.value and (not state.kg_done or not has_pending_docs):
                continue
            if name == ActionType.GREP_DOCUMENT_DISCOVER.value and (not state.kg_done or len(state.selected_docs) > 0):
                continue
            allowed_actions.append(action)

        actions_block = '\n'.join(
            f"  {i+1}. \"{a['action']}\": {a['description']} [{a['when']}]"
            for i, a in enumerate(allowed_actions)
        )

        return _POLICY_PROMPT_TEMPLATE.format(
            query=self._query,
            state_json=state_json,
            elapsed_ms=state.elapsed_ms,
            budget_ms=config.latency_budget_ms,
            step=state.step_count,
            max_steps=config.max_steps,
            actions_block=actions_block,
            min_evidence=config.min_evidence_paths,
        )

    async def decide(
        self,
        state: AgentState,
        config: AgentRunConfig,
    ) -> tuple[ActionType | None, str]:
        """Ask the LLM which action to take next.

        Returns ``(action_type, reason)`` or ``(None, reason)`` when the
        LLM says ``done`` or when parsing fails (hard stop).
        """
        prompt = self.build_prompt(state, config)

        logger.info(
            f'  [LLMPolicy] step={state.step_count} calling LLM '
            f'(state: discovery={state.discovery_done}, kg={state.kg_done}, '
            f'docs={len(state.selected_docs)}, pending={state.pending_doc_index}, '
            f'paths={len(state.selected_paths)})'
        )

        # ── Verbose prompt logging (controlled by env) ──
        import os
        if os.environ.get('RETRIEVAL_AGENTIC_VERBOSE', 'false') == 'true':
            logger.info(
                f'\n{"="*60}\n'
                f'[LLMPolicy PROMPT step={state.step_count}]\n'
                f'{prompt}\n'
                f'{"="*60}'
            )

        raw_response = await self._llm_fn(prompt)

        logger.info(
            f'  [LLMPolicy] raw_response={repr(raw_response[:200])}'
        )

        if os.environ.get('RETRIEVAL_AGENTIC_VERBOSE', 'false') == 'true':
            logger.info(
                f'\n{"="*60}\n'
                f'[LLMPolicy RESPONSE step={state.step_count}]\n'
                f'{raw_response}\n'
                f'{"="*60}'
            )

        if not raw_response.strip():
            logger.warning('  [LLMPolicy] empty response → stopping agent')
            return None, 'empty LLM response'

        parsed = _parse_action_from_response(raw_response)
        if not parsed:
            logger.warning(
                f'  [LLMPolicy] could not parse JSON from response: {repr(raw_response[:300])} → stopping agent'
            )
            return None, f'parse_error: {raw_response[:100]}'

        action_str = str(parsed.get('action', '')).strip()
        reason = str(parsed.get('reason', '')).strip()

        logger.info(f'  [LLMPolicy] decided action="{action_str}" reason="{reason}"')

        if action_str == ActionType.DONE.value:
            return ActionType.DONE, reason

        # Validate against whitelist
        try:
            action_type = ActionType(action_str)
        except ValueError:
            logger.warning(
                f'  [LLMPolicy] unknown action "{action_str}" → stopping agent'
            )
            return None, f'unknown_action: {action_str}'

        return action_type, reason

    async def attempt_answer(
        self,
        state: AgentState,
        config: AgentRunConfig,
        ranked_rows: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """Three-state verdict: is the evidence sufficient?

        Returns (verdict, reason) where verdict is one of:
          - 'DONE': evidence is sufficient, stop searching
          - 'NOT_SUFFICIENT': partial match, need more evidence
          - 'NOT_FOUND': no relevant evidence found at all
        """
        # Build evidence summary (paths + previews, not full content)
        evidence_lines: list[str] = []
        for i, row in enumerate(ranked_rows[:20]):  # cap to avoid huge prompt
            path = row.get('section_path') or row.get('source_chunk_path') or ''
            content_preview = str(row.get('content', ''))[:150]
            score = round(float(row.get('score', 0.0) or 0.0), 3)
            evidence_lines.append(
                f'  {i+1}. path="{path}" score={score}\n'
                f'     preview: {content_preview}'
            )
        evidence_text = '\n'.join(evidence_lines) or '(no evidence collected)'

        prompt = _ATTEMPT_ANSWER_PROMPT.format(
            query=self._query,
            evidence_count=len(ranked_rows),
            evidence_summary=evidence_text,
            revision_count=state.revision_count,
            max_revisions=config.max_revisions,
        )

        raw_response = await self._llm_fn(prompt)
        logger.info(f'  [LLMPolicy.attempt_answer] raw={repr(raw_response[:200])}')

        parsed = _parse_action_from_response(raw_response)
        if not parsed:
            return 'DONE', 'parse_error — treating as done'

        verdict = str(parsed.get('verdict', 'DONE')).strip().upper()
        reason = str(parsed.get('reason', '')).strip()

        if verdict not in ('DONE', 'NOT_SUFFICIENT', 'NOT_FOUND'):
            verdict = 'DONE'

        return verdict, reason


_ATTEMPT_ANSWER_PROMPT = """\
You are evaluating whether the collected evidence can answer the user's query.

QUERY: "{query}"

EVIDENCE ({evidence_count} items, showing top 20):
{evidence_summary}

REVISION: {revision_count} of {max_revisions} revisions used.

Evaluate the evidence and return ONE verdict:
- "DONE": The evidence is sufficient to answer the query. Use this if the main points are covered.
- "NOT_SUFFICIENT": Partial match — some relevant info found but key aspects are missing. Only use if more searching could realistically help.
- "NOT_FOUND": The evidence is completely irrelevant to the query. Only use if nothing matches at all.

When in doubt, prefer DONE — avoid unnecessary extra search rounds.

Return ONLY a JSON object:
{{"verdict": "DONE", "reason": "one sentence explanation"}}
"""
