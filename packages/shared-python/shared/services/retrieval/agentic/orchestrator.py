"""Retrieval Agent orchestrator — the core agent loop.

Runs the state/action/observation cycle using the rule-based policy
and agentic tools.  The fixed terminal step (hydrate + rank) always
executes, even if all tools fail — in that case it uses whatever
discovery rows were collected.

This module never raises exceptions to the caller.  Errors are captured
in the trace and the best available result is returned.
"""
from __future__ import annotations

import os
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from shared.services.retrieval.agentic.policy import RuleBasedPolicy
from shared.services.retrieval.agentic.trace import TraceRecorder
from shared.services.retrieval.agentic.types import (
    ActionType,
    AgentRunConfig,
    AgentState,
    ToolResult,
)
from shared.services.retrieval.app_service import (
    _hydrate_paths_to_rows,
    _load_chunk_importance_scores,
    _normalize_row_scores,
    _rank_candidates_by_path,
)
from shared.services.retrieval.llm_adapter import LLMFn


def _build_config_from_env() -> AgentRunConfig:
    """Read agent config from environment, with sensible defaults."""
    return AgentRunConfig(
        max_steps=int(os.environ.get('RETRIEVAL_AGENTIC_MAX_STEPS', '10')),
        max_docs=int(os.environ.get('RETRIEVAL_AGENTIC_MAX_DOCS', '0')),
        max_path_expansions=int(os.environ.get('RETRIEVAL_AGENTIC_MAX_PATH_EXPANSIONS', '2')),
        max_doc_retries=int(os.environ.get('RETRIEVAL_AGENTIC_MAX_DOC_RETRIES', '2')),
        latency_budget_ms=int(os.environ.get('RETRIEVAL_AGENTIC_LATENCY_BUDGET_MS', '12000')),
        min_evidence_paths=int(os.environ.get('RETRIEVAL_AGENTIC_MIN_EVIDENCE_PATHS', '1')),
    )


class RetrievalAgent:
    """Agentic retrieval orchestrator.

    Usage::

        agent = RetrievalAgent()
        ranked_rows, router = await agent.run(
            db, user_id=..., namespace=..., query=..., ...
        )
    """

    def __init__(self, *, policy: RuleBasedPolicy | None = None) -> None:
        self.policy = policy or RuleBasedPolicy()

    async def run(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        namespace: str,
        query: str,
        top_k: int = 10,
        llm_fn: LLMFn | None = None,
        exclude_document_ids: list[str] | None = None,
        exclude_sections: list[dict[str, str]] | None = None,
        data_type: int = 1,
        signal_paths: list[str] | None = None,
        filter_mode: str = 'delete',
        channels: list[str] | None = None,
        channel_weights: dict[str, float] | None = None,
        config: AgentRunConfig | None = None,
    ) -> tuple[list[dict[str, Any]], str]:
        """Run the agentic retrieval pipeline.

        Returns (ranked_rows, router_used).  Never raises — errors are
        captured in trace and the best available result is returned.
        """
        config = config or _build_config_from_env()
        exclude_document_ids = exclude_document_ids or []
        exclude_sections = exclude_sections or []

        state = AgentState()
        trace = TraceRecorder(
            db, user_id=user_id, namespace=namespace, query=query,
            config=config, top_k=top_k, data_type=data_type,
            filters={
                'exclude_document_ids': exclude_document_ids,
                'exclude_sections': exclude_sections,
                'signal_paths': signal_paths,
            },
        )

        trace_enabled = os.environ.get('RETRIEVAL_AGENTIC_TRACE_ENABLED', 'true') == 'true'
        if trace_enabled:
            await trace.create_run()

        logger.info(
            f'agentic retrieval START: query="{query[:60]}..." '
            f'top_k={top_k} max_steps={config.max_steps} '
            f'budget={config.latency_budget_ms}ms'
        )

        # Shared kwargs for tool calls
        tool_kwargs: dict[str, Any] = {
            'user_id': user_id,
            'namespace': namespace,
            'query': query,
            'top_k': top_k,
            'llm_fn': llm_fn,
            'exclude_document_ids': exclude_document_ids,
            'exclude_sections': exclude_sections,
            'data_type': data_type,
            'signal_paths': signal_paths,
            'filter_mode': filter_mode,
            'channels': channels,
            'channel_weights': channel_weights,
        }

        # ── Agent loop ──
        while state.step_count < config.max_steps:
            if state.elapsed_ms >= config.latency_budget_ms:
                logger.info(
                    f'  agentic: latency budget hit ({state.elapsed_ms}ms >= {config.latency_budget_ms}ms), '
                    f'stopping at step {state.step_count}'
                )
                trace.record_budget_stop('latency')
                break

            action_type = self.policy.decide(state, config)
            if action_type is None:
                logger.info(f'  agentic: policy returned None at step {state.step_count}, stopping')
                break

            result = await self._execute_tool(db, action_type, state, config, **tool_kwargs)
            state.apply(action_type, result)

            if trace_enabled:
                trace.record_step(action_type, result)

            state.step_count += 1

            logger.info(
                f'  agentic step {state.step_count}: action={action_type.value} '
                f'status={result.status} latency={result.latency_ms}ms '
                f'docs={len(state.selected_docs)} paths={len(state.selected_paths)}'
            )

        # ── Fixed terminal step: hydrate + rank ──
        ranked_rows = await self._hydrate_and_rank(
            db, state, user_id=user_id, namespace=namespace, top_k=top_k,
        )

        router_used = 'agentic' if state.selected_paths else 'agentic_discovery_only'

        if trace_enabled:
            await trace.complete(ranked_rows, router_used)

        total_ms = state.elapsed_ms
        logger.info(
            f'agentic retrieval DONE: {len(ranked_rows)} results, '
            f'router={router_used}, steps={state.step_count}, {total_ms}ms'
        )

        return ranked_rows, router_used

    async def _execute_tool(
        self,
        db: AsyncSession,
        action_type: ActionType,
        state: AgentState,
        config: AgentRunConfig,
        **kwargs: Any,
    ) -> ToolResult:
        """Execute a single tool.  Never raises."""
        from shared.services.retrieval.agentic import tools

        try:
            if action_type == ActionType.BOTTOM_DISCOVERY:
                return await tools.bottom_discovery(db, **kwargs)

            elif action_type == ActionType.KG_DOCUMENT_SELECT:
                return await tools.kg_document_select(
                    db,
                    user_id=kwargs['user_id'],
                    namespace=kwargs['namespace'],
                    query=kwargs['query'],
                    llm_fn=kwargs.get('llm_fn'),
                    exclude_document_ids=list(state.excluded_doc_ids | set(kwargs.get('exclude_document_ids', []))),
                )

            elif action_type == ActionType.DOCUMENT_PATH_SELECT:
                # Find which document to process next
                doc = None
                if state.pending_doc_index < len(state.selected_docs):
                    doc = state.selected_docs[state.pending_doc_index]

                if doc is None:
                    return ToolResult(status='error', error='no document to process')

                job_result_id = state.doc_job_map.get(doc.document_id, '')
                if not job_result_id:
                    return ToolResult(
                        status='no_confident_match',
                        payload={'document_id': doc.document_id, 'reason': 'no job_result_id'},
                    )

                return await tools.document_path_select(
                    db,
                    user_id=kwargs['user_id'],
                    namespace=kwargs['namespace'],
                    query=kwargs['query'],
                    llm_fn=kwargs.get('llm_fn'),
                    document_id=doc.document_id,
                    job_result_id=job_result_id,
                    doc_name=doc.source_file_name or state.doc_id_to_name.get(doc.document_id, ''),
                )

            elif action_type == ActionType.GREP_DOCUMENT_DISCOVER:
                return await tools.grep_document_discover(
                    db,
                    user_id=kwargs['user_id'],
                    namespace=kwargs['namespace'],
                    query=kwargs['query'],
                    exclude_document_ids=list(state.excluded_doc_ids | set(kwargs.get('exclude_document_ids', []))),
                )

            elif action_type == ActionType.GRAPH_EXPAND_DOCS:
                doc_ids = [d.document_id for d in state.selected_docs]
                return await tools.graph_expand_docs(
                    db,
                    user_id=kwargs['user_id'],
                    namespace=kwargs['namespace'],
                    document_ids=doc_ids,
                )

            elif action_type == ActionType.NAV_SECTION_SELECT:
                if not state.nav_drill_stack:
                    return ToolResult(status='error', error='nav_drill_stack is empty')

                import asyncio as _asyncio

                # Concurrently navigate ALL pending documents in nav_drill_stack
                drill_entries = list(state.nav_drill_stack)  # snapshot
                nav_tasks = [
                    tools.nav_section_select(
                        db,
                        user_id=kwargs['user_id'],
                        namespace=kwargs['namespace'],
                        query=kwargs['query'],
                        llm_fn=kwargs.get('llm_fn'),
                        document_id=entry['document_id'],
                        job_result_id=state.doc_job_map.get(entry['document_id'], ''),
                        doc_name=state.doc_id_to_name.get(entry['document_id'], ''),
                        section_path=entry.get('section_path'),
                    )
                    for entry in drill_entries
                ]
                nav_results: list[ToolResult] = await _asyncio.gather(*nav_tasks)

                # Merge all results into a single batch ToolResult consumed by state.apply
                all_paths: list[dict] = []
                any_selected = False
                total_latency = 0
                for res in nav_results:
                    total_latency = max(total_latency, res.latency_ms)
                    if res.status == 'selected_paths':
                        any_selected = True
                        all_paths.extend(res.payload.get('selected_paths', []))

                logger.info(
                    f'  agentic.nav_section_select (concurrent): '
                    f'{len(drill_entries)} docs → {len(all_paths)} total paths, '
                    f'{total_latency}ms'
                )
                return ToolResult(
                    status='selected_paths' if any_selected else 'no_confident_match',
                    payload={
                        'selected_paths': all_paths,
                        '_consumed_stack': [e['document_id'] for e in drill_entries],
                    },
                    latency_ms=total_latency,
                )

            else:
                return ToolResult(status='error', error=f'unknown action: {action_type}')

        except Exception as e:
            logger.warning(f'  agentic tool {action_type.value} raised: {e}')
            return ToolResult(status='error', error=str(e))

    async def _hydrate_and_rank(
        self,
        db: AsyncSession,
        state: AgentState,
        *,
        user_id: str,
        namespace: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Fixed terminal step: hydrate selected paths + rank against discovery.

        Reuses _hydrate_paths_to_rows and _rank_candidates_by_path unchanged.
        """
        try:
            # Hydrate agent-selected paths
            agent_rows: list[dict[str, Any]] = []
            if state.selected_paths:
                agent_rows = await _hydrate_paths_to_rows(
                    db,
                    path_selections=state.selected_paths,
                    user_id=user_id,
                    namespace=namespace,
                )

            # Load importance scores for all candidate rows
            all_candidates = state.discovery_rows + agent_rows
            if all_candidates:
                importance_map = await _load_chunk_importance_scores(
                    db, user_id=user_id, namespace=namespace,
                    rows=all_candidates,
                )
                for row in all_candidates:
                    chunk_id = row.get('chunk_id', '')
                    row['importance_raw_score'] = importance_map.get(chunk_id, 0.0)

                _normalize_row_scores(
                    all_candidates,
                    source_field='importance_raw_score',
                    target_field='importance_norm_score',
                    default=0.0,
                )

            # Rank: merge discovery + agent rows
            ranked = _rank_candidates_by_path(
                discovery_rows=state.discovery_rows,
                routed_rows=agent_rows,
                top_k=top_k,
            )

            return ranked

        except Exception as e:
            logger.error(f'agentic hydrate_and_rank failed: {e}')
            # Last resort: return raw discovery rows
            return state.discovery_rows[:top_k]
