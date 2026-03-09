"""add active jobs partial index for concurrency checks

Revision ID: f3a9c2e4d5b6
Revises: jkl012mno345
Create Date: 2026-02-27 22:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3a9c2e4d5b6"
down_revision: Union[str, Sequence[str], None] = "a3f7c9d1e2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEX_NAME = "idx_job_user_active_states"
_ACTIVE_STATES_WHERE = (
    "status IN ('waiting-file', 'pending', 'running', 'converting')"
)


def upgrade() -> None:
    """Create index optimized for per-user active-job count queries."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("jobs")}
    if _INDEX_NAME in existing_indexes:
        return

    if conn.dialect.name == "postgresql":
        op.create_index(
            _INDEX_NAME,
            "jobs",
            ["user_id", "status"],
            unique=False,
            postgresql_where=sa.text(_ACTIVE_STATES_WHERE),
        )
        return

    # Fallback for non-PostgreSQL dialects.
    op.create_index(
        _INDEX_NAME,
        "jobs",
        ["user_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Drop active-job count optimization index."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("jobs")}
    if _INDEX_NAME in existing_indexes:
        op.drop_index(_INDEX_NAME, table_name="jobs")
