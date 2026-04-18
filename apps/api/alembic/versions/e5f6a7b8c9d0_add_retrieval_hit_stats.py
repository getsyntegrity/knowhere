"""add retrieval hit stats

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-18 11:50:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'retrieval_hit_stats',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('namespace', sa.String(length=255), nullable=False, server_default='default'),
        sa.Column('hit_kind', sa.String(length=32), nullable=False),
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('chunk_id', sa.String(length=64), nullable=True),
        sa.Column('hit_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('last_hit_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.document_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_retrieval_hit_stats_scope_kind', 'retrieval_hit_stats', ['user_id', 'namespace', 'hit_kind'])
    op.create_index('idx_retrieval_hit_stats_document', 'retrieval_hit_stats', ['document_id'])
    op.create_index('idx_retrieval_hit_stats_chunk', 'retrieval_hit_stats', ['chunk_id'])


def downgrade() -> None:
    op.drop_index('idx_retrieval_hit_stats_chunk', table_name='retrieval_hit_stats')
    op.drop_index('idx_retrieval_hit_stats_document', table_name='retrieval_hit_stats')
    op.drop_index('idx_retrieval_hit_stats_scope_kind', table_name='retrieval_hit_stats')
    op.drop_table('retrieval_hit_stats')
