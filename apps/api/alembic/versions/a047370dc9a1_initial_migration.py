"""initial migration

Revision ID: a047370dc9a1
Revises: 
Create Date: 2025-10-29 20:56:26.784657

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a047370dc9a1'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(table_name: str) -> bool:
    """检查表是否存在"""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def index_exists(table_name: str, index_name: str) -> bool:
    """检查索引是否存在"""
    try:
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        indexes = inspector.get_indexes(table_name)
        return any(idx['name'] == index_name for idx in indexes)
    except Exception:
        return False


def upgrade() -> None:
    """Upgrade schema - 创建所有初始表结构（如果不存在）"""
    
    # 1. 创建基础表（无外键依赖）
    # 1.1 users 表 (FastAPI Users 基础表 + 自定义字段)
    if not table_exists('users'):
        op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=1024), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=255), nullable=True),
        sa.Column('avatar_url', sa.String(length=512), nullable=True),
        sa.Column('create_time', sa.DateTime(), nullable=True),
        sa.Column('provider_type', sa.String(length=50), nullable=True),
        sa.Column('provider_id', sa.String(length=255), nullable=True),
        sa.Column('credits_balance', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('subscription_id', sa.String(length=255), nullable=True),
        sa.Column('user_type', sa.String(length=50), nullable=False, server_default='user'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )
    if table_exists('users') and not index_exists('users', 'ix_users_email'):
        op.create_index('ix_users_email', 'users', ['email'], unique=False)
    
    # 1.2 roles 表
    if not table_exists('roles'):
        op.create_table('roles',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
        )
        if not index_exists('roles', 'ix_roles_id'):
            op.create_index(op.f('ix_roles_id'), 'roles', ['id'], unique=False)
    
    # 1.3 knowledge_base 表
    if not table_exists('knowledge_base'):
        op.create_table('knowledge_base',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('content', sa.Text(), nullable=True, comment='内容的具体文本'),
        sa.Column('path', sa.Text(), nullable=True, comment='文件路径或来源'),
        sa.Column('type', sa.String(length=2000), nullable=True, comment='内容类型（如PTXT, SUMMARY等）'),
        sa.Column('length', sa.Integer(), nullable=True, comment='内容的长度或大小'),
        sa.Column('keywords', sa.String(length=511), nullable=True, comment='内容的关键词'),
        sa.Column('summary', sa.Text(), nullable=True, comment='内容的摘要'),
        sa.Column('know_id', sa.String(length=128), nullable=True, comment='知识ID，可能关联到外部知识库'),
        sa.Column('tokens', sa.Text(), nullable=True, comment='内容分词后的token'),
        sa.Column('embedding', sa.Text(), nullable=True, comment='内容的语义向量，用于相似度搜索等'),
        sa.PrimaryKeyConstraint('id')
        )
        if not index_exists('knowledge_base', 'ix_knowledge_base_id'):
            op.create_index(op.f('ix_knowledge_base_id'), 'knowledge_base', ['id'], unique=False)
    
    # 1.4 path_base 表
    if not table_exists('path_base'):
        op.create_table('path_base',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('path', sa.Text(), nullable=True, comment='文件路径或来源'),
        sa.Column('embedding', sa.Text(), nullable=True, comment='内容的语义向量，用于相似度搜索等'),
        sa.PrimaryKeyConstraint('id')
        )
        if not index_exists('path_base', 'ix_path_base_id'):
            op.create_index(op.f('ix_path_base_id'), 'path_base', ['id'], unique=False)
    
    # 1.5 file_directory 表（自引用，需要先创建表再添加外键约束）
    if not table_exists('file_directory'):
        op.create_table('file_directory',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False, comment='目录标题'),
        sa.Column('parent_id', sa.String(length=36), nullable=True, comment='父级目录ID，NULL表示根目录'),
        sa.Column('user_id', sa.String(length=36), nullable=False, comment='所属用户ID'),
        sa.Column('create_time', sa.DateTime(), nullable=True, comment='创建时间'),
        sa.Column('update_time', sa.DateTime(), nullable=True, comment='更新时间'),
        sa.PrimaryKeyConstraint('id')
        )
        if not index_exists('file_directory', 'ix_file_directory_id'):
            op.create_index(op.f('ix_file_directory_id'), 'file_directory', ['id'], unique=False)
        # 检查外键是否存在
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        if table_exists('file_directory'):
            fks = inspector.get_foreign_keys('file_directory')
            if not any(fk['name'] == 'fk_file_directory_parent_id' for fk in fks):
                op.create_foreign_key('fk_file_directory_parent_id', 'file_directory', 'file_directory', ['parent_id'], ['id'])
    
    # 2. 创建依赖 users 的表
    # 2.1 api_keys 表
    if not table_exists('api_keys'):
        op.create_table('api_keys',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key_hash', sa.String(length=255), nullable=False),
        sa.Column('key_mask', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('enabled_modules', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    if table_exists('api_keys') and not index_exists('api_keys', 'ix_api_keys_key_hash'):
        op.create_index(op.f('ix_api_keys_key_hash'), 'api_keys', ['key_hash'], unique=False)
    
    # 2.2 subscriptions 表
    if not table_exists('subscriptions'):
        op.create_table('subscriptions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('plan_type', sa.String(length=50), nullable=False),
        sa.Column('stripe_subscription_id', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('start_date', sa.DateTime(), nullable=False),
        sa.Column('end_date', sa.DateTime(), nullable=True),
        sa.Column('subscription_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    if table_exists('subscriptions') and not index_exists('subscriptions', 'ix_subscriptions_stripe_subscription_id'):
        op.create_index(op.f('ix_subscriptions_stripe_subscription_id'), 'subscriptions', ['stripe_subscription_id'], unique=False)
    
    # 2.3 credits_transactions 表
    if not table_exists('credits_transactions'):
        op.create_table('credits_transactions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('credits_amount', sa.Integer(), nullable=False),
        sa.Column('transaction_type', sa.String(length=50), nullable=False),
        sa.Column('stripe_payment_id', sa.String(length=255), nullable=True),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('transaction_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    if table_exists('credits_transactions'):
        if not index_exists('credits_transactions', 'ix_credits_transactions_stripe_payment_id'):
            op.create_index(op.f('ix_credits_transactions_stripe_payment_id'), 'credits_transactions', ['stripe_payment_id'], unique=False)
        if not index_exists('credits_transactions', 'ix_credits_transactions_created_at'):
            op.create_index(op.f('ix_credits_transactions_created_at'), 'credits_transactions', ['created_at'], unique=False)
    
    # 2.4 jobs 表
    if not table_exists('jobs'):
        op.create_table('jobs',
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='pending'),
        sa.Column('source_type', sa.String(length=20), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=True),
        sa.Column('s3_key', sa.String(length=512), nullable=True),
        sa.Column('webhook_url', sa.String(length=512), nullable=True),
        sa.Column('webhook_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('job_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('job_id')
    )
    if table_exists('jobs'):
        for idx_name, columns in [
            ('idx_job_user_id', ['user_id']),
            ('idx_job_status', ['status']),
            ('idx_job_type', ['job_type']),
            ('idx_job_created_at', ['created_at']),
            ('idx_job_user_status', ['user_id', 'status'])
        ]:
            if not index_exists('jobs', idx_name):
                op.create_index(idx_name, 'jobs', columns, unique=False)
    
    # 2.5 usage_logs 表
    if not table_exists('usage_logs'):
        op.create_table('usage_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('api_key_id', sa.String(length=36), nullable=True),
        sa.Column('endpoint', sa.String(length=255), nullable=False),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('credits_used', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('response_time', sa.Integer(), nullable=True),
        sa.Column('status_code', sa.Integer(), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['api_key_id'], ['api_keys.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    if table_exists('usage_logs'):
        if not index_exists('usage_logs', 'ix_usage_logs_endpoint'):
            op.create_index(op.f('ix_usage_logs_endpoint'), 'usage_logs', ['endpoint'], unique=False)
        if not index_exists('usage_logs', 'ix_usage_logs_created_at'):
            op.create_index(op.f('ix_usage_logs_created_at'), 'usage_logs', ['created_at'], unique=False)
    
    # 3. 创建依赖 jobs 的表
    # 3.1 job_state_history 表
    if not table_exists('job_state_history'):
        op.create_table('job_state_history',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('from_state', sa.String(length=50), nullable=False),
        sa.Column('to_state', sa.String(length=50), nullable=False),
        sa.Column('transition_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.job_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    if table_exists('job_state_history'):
        if not index_exists('job_state_history', 'idx_job_state_history_job_id'):
            op.create_index('idx_job_state_history_job_id', 'job_state_history', ['job_id'], unique=False)
        if not index_exists('job_state_history', 'idx_job_state_history_created_at'):
            op.create_index('idx_job_state_history_created_at', 'job_state_history', ['created_at'], unique=False)
    
    # 3.2 job_state_audit_logs 表
    if not table_exists('job_state_audit_logs'):
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
    if table_exists('job_state_audit_logs'):
        for idx_name, columns in [
            ('idx_audit_log_job_id', ['job_id']),
            ('idx_audit_log_created_at', ['created_at']),
            ('idx_audit_log_job_created', ['job_id', 'created_at'])
        ]:
            if not index_exists('job_state_audit_logs', idx_name):
                op.create_index(idx_name, 'job_state_audit_logs', columns, unique=False)
    
    # 3.3 webhook_logs 表
    if not table_exists('webhook_logs'):
        op.create_table('webhook_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('webhook_url', sa.String(length=512), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('request_payload', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('signature', sa.String(length=128), nullable=False),
        sa.Column('idempotency_key', sa.String(length=36), nullable=False),
        sa.Column('response_status_code', sa.Integer(), nullable=True),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.job_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    if table_exists('webhook_logs'):
        for idx_name, columns in [
            ('idx_webhook_logs_job_id', ['job_id']),
            ('idx_webhook_logs_created_at', ['created_at']),
            ('idx_webhook_logs_attempt', ['job_id', 'attempt_number'])
        ]:
            if not index_exists('webhook_logs', idx_name):
                op.create_index(idx_name, 'webhook_logs', columns, unique=False)
    
    # 3.4 job_results 表
    if not table_exists('job_results'):
        op.create_table('job_results',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('job_id', sa.String(length=36), nullable=False),
        sa.Column('delivery_mode', sa.String(length=20), nullable=False),
        sa.Column('document_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('inline_payload', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('result_s3_key', sa.String(length=512), nullable=True),
        sa.Column('result_size', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.job_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('job_id')
    )
    
    # 3.5 job_chunks 表
    if not table_exists('job_chunks'):
        op.create_table('job_chunks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('job_result_id', sa.String(length=36), nullable=False),
        sa.Column('chunk_id', sa.String(length=64), nullable=False),
        sa.Column('chunk_type', sa.String(length=2000), nullable=False),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('path', sa.String(length=1024), nullable=True),
        sa.Column('chunk_metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['job_result_id'], ['job_results.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    if table_exists('job_chunks'):
        if not index_exists('job_chunks', 'idx_job_chunks_result'):
            op.create_index('idx_job_chunks_result', 'job_chunks', ['job_result_id'], unique=False)
        if not index_exists('job_chunks', 'idx_job_chunks_chunk_id'):
            op.create_index('idx_job_chunks_chunk_id', 'job_chunks', ['chunk_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema - 删除所有表（按依赖顺序反向删除）"""
    
    # 删除依赖 job_results 的表
    op.drop_table('job_chunks')
    op.drop_table('job_results')
    
    # 删除依赖 jobs 的表
    op.drop_table('webhook_logs')
    op.drop_table('job_state_audit_logs')
    op.drop_table('job_state_history')
    
    # 删除依赖 users 的表
    op.drop_table('usage_logs')
    op.drop_table('jobs')
    op.drop_table('credits_transactions')
    op.drop_table('subscriptions')
    op.drop_table('api_keys')
    
    # 删除基础表
    op.drop_table('file_directory')
    op.drop_table('path_base')
    op.drop_table('knowledge_base')
    op.drop_table('roles')
    op.drop_table('users')
