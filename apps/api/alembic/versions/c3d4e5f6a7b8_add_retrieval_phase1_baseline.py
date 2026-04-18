"""add retrieval phase1 baseline

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-18 09:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'documents',
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('namespace', sa.String(length=255), nullable=False, server_default='default'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='active'),
        sa.Column('current_job_result_id', sa.String(length=36), nullable=True),
        sa.Column('source_file_name', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('archived_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['current_job_result_id'], ['job_results.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('document_id'),
    )
    op.create_index('idx_documents_user_namespace_status', 'documents', ['user_id', 'namespace', 'status'])
    op.create_index('idx_documents_current_job_result', 'documents', ['current_job_result_id'])

    op.add_column('job_results', sa.Column('document_id', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_job_results_document_id'), 'job_results', ['document_id'])
    op.create_foreign_key(None, 'job_results', 'documents', ['document_id'], ['document_id'], ondelete='SET NULL')

    op.create_table(
        'document_sections',
        sa.Column('section_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('namespace', sa.String(length=255), nullable=False, server_default='default'),
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('job_result_id', sa.String(length=36), nullable=False),
        sa.Column('parent_section_id', sa.String(length=36), nullable=True),
        sa.Column('section_path', sa.Text(), nullable=False),
        sa.Column('section_title', sa.Text(), nullable=True),
        sa.Column('section_level', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('section_metadata', sa.JSON(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.document_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_result_id'], ['job_results.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_section_id'], ['document_sections.section_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('section_id'),
        sa.UniqueConstraint('document_id', 'job_result_id', 'section_path', name='uq_document_sections_revision_path'),
    )
    op.create_index('idx_document_sections_scope', 'document_sections', ['user_id', 'namespace'])
    op.create_index('idx_document_sections_doc_revision', 'document_sections', ['document_id', 'job_result_id'])

    op.create_table(
        'document_chunks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('chunk_id', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.Text(), nullable=False),
        sa.Column('namespace', sa.String(length=255), nullable=False, server_default='default'),
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('job_result_id', sa.String(length=36), nullable=False),
        sa.Column('section_id', sa.String(length=36), nullable=True),
        sa.Column('chunk_type', sa.String(length=64), nullable=False, server_default='text'),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('source_chunk_path', sa.Text(), nullable=True),
        sa.Column('file_path', sa.Text(), nullable=True),
        sa.Column('chunk_metadata', sa.JSON(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.document_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_result_id'], ['job_results.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['section_id'], ['document_sections.section_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('document_id', 'job_result_id', 'source_chunk_path', name='uq_document_chunks_revision_path'),
    )
    op.create_index('idx_document_chunks_scope', 'document_chunks', ['user_id', 'namespace'])
    op.create_index('idx_document_chunks_chunk_id', 'document_chunks', ['chunk_id'])
    op.create_index('idx_document_chunks_doc_revision', 'document_chunks', ['document_id', 'job_result_id'])
    op.create_index('idx_document_chunks_section', 'document_chunks', ['section_id'])


def downgrade() -> None:
    op.drop_index('idx_document_chunks_section', table_name='document_chunks')
    op.drop_index('idx_document_chunks_doc_revision', table_name='document_chunks')
    op.drop_index('idx_document_chunks_chunk_id', table_name='document_chunks')
    op.drop_index('idx_document_chunks_scope', table_name='document_chunks')
    op.drop_table('document_chunks')

    op.drop_index('idx_document_sections_doc_revision', table_name='document_sections')
    op.drop_index('idx_document_sections_scope', table_name='document_sections')
    op.drop_table('document_sections')

    op.drop_constraint(None, 'job_results', type_='foreignkey')
    op.drop_index(op.f('ix_job_results_document_id'), table_name='job_results')
    op.drop_column('job_results', 'document_id')

    op.drop_index('idx_documents_current_job_result', table_name='documents')
    op.drop_index('idx_documents_user_namespace_status', table_name='documents')
    op.drop_table('documents')
