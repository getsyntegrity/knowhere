"""add agentic retrieval tables

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-26 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── retrieval_runs: one row per agentic retrieval query ──
    op.create_table(
        'retrieval_runs',
        sa.Column('run_id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.Text, nullable=False),
        sa.Column('namespace', sa.String(255), nullable=False, server_default='default'),
        sa.Column('query', sa.Text, nullable=False),
        sa.Column('query_hash', sa.String(32), nullable=False, server_default=''),
        sa.Column('top_k', sa.Integer, nullable=False, server_default='10'),
        sa.Column('data_type', sa.Integer, nullable=False, server_default='1'),
        sa.Column('filters', sa.JSON, nullable=True),
        sa.Column('policy_name', sa.String(64), nullable=False, server_default='rule_based_v1'),
        sa.Column('agentic_enabled', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('cache_hit', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('result_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('final_doc_ids', sa.JSON, nullable=True),
        sa.Column('result_provenance', sa.JSON, nullable=True),
        sa.Column('latency_ms', sa.Integer, nullable=False, server_default='0'),
        sa.Column('token_count', sa.Integer, nullable=True),
        sa.Column('error', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime, nullable=True),
    )
    op.create_index('idx_retrieval_runs_user_namespace', 'retrieval_runs', ['user_id', 'namespace'])
    op.create_index('idx_retrieval_runs_created', 'retrieval_runs', ['created_at'])
    op.create_index('idx_retrieval_runs_query_hash', 'retrieval_runs', ['query_hash'])

    # ── retrieval_steps: one row per agent step within a run ──
    op.create_table(
        'retrieval_steps',
        sa.Column('step_id', sa.String(36), primary_key=True),
        sa.Column('run_id', sa.String(36), nullable=False, index=True),
        sa.Column('step_index', sa.Integer, nullable=False, server_default='0'),
        sa.Column('action_type', sa.String(64), nullable=False),
        sa.Column('action_input', sa.JSON, nullable=True),
        sa.Column('observation', sa.JSON, nullable=True),
        sa.Column('selected_doc_ids', sa.JSON, nullable=True),
        sa.Column('selected_paths', sa.JSON, nullable=True),
        sa.Column('latency_ms', sa.Integer, nullable=False, server_default='0'),
        sa.Column('token_count', sa.Integer, nullable=True),
        sa.Column('model_name', sa.String(128), nullable=True),
        sa.Column('error', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_retrieval_steps_run', 'retrieval_steps', ['run_id', 'step_index'])


def downgrade() -> None:
    op.drop_index('idx_retrieval_steps_run', table_name='retrieval_steps')
    op.drop_table('retrieval_steps')
    op.drop_index('idx_retrieval_runs_query_hash', table_name='retrieval_runs')
    op.drop_index('idx_retrieval_runs_created', table_name='retrieval_runs')
    op.drop_index('idx_retrieval_runs_user_namespace', table_name='retrieval_runs')
    op.drop_table('retrieval_runs')
