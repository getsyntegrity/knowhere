"""add checkerboard search fields

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-22 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE document_chunks ADD COLUMN content_search_text TEXT")
    op.execute("ALTER TABLE document_chunks ADD COLUMN path_search_text TEXT")
    op.execute("ALTER TABLE document_chunks ADD COLUMN term_search_text TEXT")

    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN content_search_tsv TSVECTOR "
        "GENERATED ALWAYS AS (to_tsvector('simple', COALESCE(content_search_text, ''))) STORED"
    )
    op.execute(
        "ALTER TABLE document_chunks ADD COLUMN path_search_tsv TSVECTOR "
        "GENERATED ALWAYS AS (to_tsvector('simple', COALESCE(path_search_text, ''))) STORED"
    )

    op.execute(
        "CREATE INDEX idx_chunk_content_search_tsv ON document_chunks USING GIN (content_search_tsv)"
    )
    op.execute(
        "CREATE INDEX idx_chunk_path_search_tsv ON document_chunks USING GIN (path_search_tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_chunk_path_search_tsv")
    op.execute("DROP INDEX IF EXISTS idx_chunk_content_search_tsv")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS path_search_tsv")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS content_search_tsv")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS term_search_text")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS path_search_text")
    op.execute("ALTER TABLE document_chunks DROP COLUMN IF EXISTS content_search_text")
