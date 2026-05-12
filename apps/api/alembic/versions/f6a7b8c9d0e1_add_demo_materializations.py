"""add demo materializations

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-12 08:25:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "demo_materializations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("namespace", sa.String(length=255), nullable=False),
        sa.Column("demo_source_id", sa.String(length=128), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.document_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "namespace",
            "demo_source_id",
            name="uq_demo_materializations_scope_source",
        ),
    )
    op.create_index(
        "idx_demo_materializations_document",
        "demo_materializations",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "idx_demo_materializations_document",
        table_name="demo_materializations",
    )
    op.drop_table("demo_materializations")
