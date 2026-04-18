"""add retrieval graph routing

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-18 10:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'graph_nodes',
        sa.Column('node_id', sa.String(length=128), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('namespace', sa.String(length=255), nullable=False, server_default='default'),
        sa.Column('node_kind', sa.String(length=32), nullable=False),
        sa.Column('owner_document_id', sa.String(length=36), nullable=False),
        sa.Column('job_result_id', sa.String(length=36), nullable=False),
        sa.Column('ref_document_id', sa.String(length=36), nullable=True),
        sa.Column('ref_section_id', sa.String(length=36), nullable=True),
        sa.Column('properties', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['owner_document_id'], ['documents.document_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_result_id'], ['job_results.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('node_id'),
    )
    op.create_index('idx_graph_nodes_scope', 'graph_nodes', ['user_id', 'namespace', 'node_kind'])
    op.create_index('idx_graph_nodes_owner_revision', 'graph_nodes', ['owner_document_id', 'job_result_id'])
    op.create_index('idx_graph_nodes_ref_document', 'graph_nodes', ['ref_document_id'])
    op.create_index('idx_graph_nodes_ref_section', 'graph_nodes', ['ref_section_id'])

    op.create_table(
        'graph_edges',
        sa.Column('edge_id', sa.String(length=160), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('namespace', sa.String(length=255), nullable=False, server_default='default'),
        sa.Column('edge_kind', sa.String(length=32), nullable=False),
        sa.Column('source_node_id', sa.String(length=128), nullable=False),
        sa.Column('target_node_id', sa.String(length=128), nullable=False),
        sa.Column('owner_document_id', sa.String(length=36), nullable=False),
        sa.Column('job_result_id', sa.String(length=36), nullable=False),
        sa.Column('is_directed', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('weight', sa.Integer(), nullable=True),
        sa.Column('properties', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['source_node_id'], ['graph_nodes.node_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_node_id'], ['graph_nodes.node_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_document_id'], ['documents.document_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_result_id'], ['job_results.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('edge_id'),
    )
    op.create_index('idx_graph_edges_scope', 'graph_edges', ['user_id', 'namespace', 'edge_kind'])
    op.create_index('idx_graph_edges_owner_revision', 'graph_edges', ['owner_document_id', 'job_result_id'])
    op.create_index('idx_graph_edges_source', 'graph_edges', ['source_node_id'])
    op.create_index('idx_graph_edges_target', 'graph_edges', ['target_node_id'])


def downgrade() -> None:
    op.drop_index('idx_graph_edges_target', table_name='graph_edges')
    op.drop_index('idx_graph_edges_source', table_name='graph_edges')
    op.drop_index('idx_graph_edges_owner_revision', table_name='graph_edges')
    op.drop_index('idx_graph_edges_scope', table_name='graph_edges')
    op.drop_table('graph_edges')

    op.drop_index('idx_graph_nodes_ref_section', table_name='graph_nodes')
    op.drop_index('idx_graph_nodes_ref_document', table_name='graph_nodes')
    op.drop_index('idx_graph_nodes_owner_revision', table_name='graph_nodes')
    op.drop_index('idx_graph_nodes_scope', table_name='graph_nodes')
    op.drop_table('graph_nodes')
