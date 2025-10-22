"""Add state machine improvements

Revision ID: add_state_machine_improvements
Revises: f16d6b72dcf8
Create Date: 2024-01-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_state_machine_improvements'
down_revision = 'f16d6b72dcf8'
branch_labels = None
depends_on = None


def upgrade():
    # 添加版本控制字段到jobs表（如果不存在）
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('jobs')]
    
    if 'version' not in columns:
        op.add_column('jobs', sa.Column('version', sa.Integer(), nullable=False, server_default='0'))
    
    # 创建状态审计日志表（如果不存在）
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()
    
    if 'job_state_audit_logs' not in tables:
        op.create_table('job_state_audit_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('from_state', sa.String(length=50), nullable=True),
        sa.Column('to_state', sa.String(length=50), nullable=False),
        sa.Column('transition_reason', sa.String(length=100), nullable=False),
        sa.Column('operator_id', sa.String(length=36), nullable=True),
        sa.Column('operator_type', sa.String(length=20), nullable=False, server_default='system'),
        sa.Column('transition_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['job_id'], ['jobs.job_id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        
        # 创建索引
        op.create_index('idx_audit_log_job_id', 'job_state_audit_logs', ['job_id'])
        op.create_index('idx_audit_log_created_at', 'job_state_audit_logs', ['created_at'])
        op.create_index('idx_audit_log_job_created', 'job_state_audit_logs', ['job_id', 'created_at'])


def downgrade():
    # 检查表是否存在
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    tables = inspector.get_table_names()
    
    if 'job_state_audit_logs' in tables:
        # 删除索引
        op.drop_index('idx_audit_log_job_created', table_name='job_state_audit_logs')
        op.drop_index('idx_audit_log_created_at', table_name='job_state_audit_logs')
        op.drop_index('idx_audit_log_job_id', table_name='job_state_audit_logs')
        
        # 删除表
        op.drop_table('job_state_audit_logs')
    
    # 删除版本控制字段（如果存在）
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('jobs')]
    
    if 'version' in columns:
        op.drop_column('jobs', 'version')
