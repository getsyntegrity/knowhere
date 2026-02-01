"""Add webhook_events table and update webhook_logs

Revision ID: d1e2f3a4b5c6
Revises: b2c3d4e5f6a8
Create Date: 2026-01-25 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'b2c3d4e5f6a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create webhook_events table (the "outbox")
    op.create_table(
        'webhook_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('job_id', sa.String(36), sa.ForeignKey('jobs.job_id', ondelete='CASCADE'), nullable=False),
        sa.Column('target_url', sa.String(2048), nullable=False),
        sa.Column('secret', sa.Text(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('next_retry_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create indexes for webhook_events
    op.create_index('idx_webhook_events_job_id', 'webhook_events', ['job_id'])
    op.create_index('idx_webhook_events_status', 'webhook_events', ['status'])
    op.create_index('idx_webhook_events_next_retry', 'webhook_events', ['next_retry_at'])
    op.create_index('idx_webhook_events_created_at', 'webhook_events', ['created_at'])
    
    # Add event_id column to webhook_logs (nullable for backward compatibility)
    op.add_column(
        'webhook_logs',
        sa.Column('event_id', sa.String(36), sa.ForeignKey('webhook_events.id', ondelete='CASCADE'), nullable=True)
    )
    
    # Add duration_ms column to webhook_logs
    op.add_column(
        'webhook_logs',
        sa.Column('duration_ms', sa.Integer(), nullable=False, server_default='0')
    )
    
    # Create index for event_id
    op.create_index('idx_webhook_logs_event_id', 'webhook_logs', ['event_id'])


def downgrade() -> None:
    # Drop index and column from webhook_logs
    op.drop_index('idx_webhook_logs_event_id', table_name='webhook_logs')
    op.drop_column('webhook_logs', 'duration_ms')
    op.drop_column('webhook_logs', 'event_id')
    
    # Drop indexes from webhook_events
    op.drop_index('idx_webhook_events_created_at', table_name='webhook_events')
    op.drop_index('idx_webhook_events_next_retry', table_name='webhook_events')
    op.drop_index('idx_webhook_events_status', table_name='webhook_events')
    op.drop_index('idx_webhook_events_job_id', table_name='webhook_events')
    
    # Drop webhook_events table
    op.drop_table('webhook_events')
