"""简化状态机为PRD状态

Revision ID: 20250101_simplify_to_prd_status
Revises: 
Create Date: 2025-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20250101_simplify_to_prd_status'
down_revision = 'c88943aa1196'  # 基于当前的head
branch_labels = None
depends_on = None


def upgrade():
    """升级：将current_state映射到status并删除current_state字段"""
    
    # 1. 备份current_state数据（可选，用于回滚）
    # 这里我们直接进行映射，不创建备份表
    
    # 2. 将current_state映射到status字段
    op.execute("""
        UPDATE jobs 
        SET status = CASE 
            WHEN current_state = 'uploading' THEN 'waiting-file'
            WHEN current_state = 'uploaded' THEN 'pending'
            WHEN current_state = 'pending' THEN 'pending'
            WHEN current_state IN ('parsing', 'vectorizing', 'storing_db', 'processing', 
                                   'extracting_table', 'kb_searching', 'llm_processing', 
                                   'filling_table', 'generating_result') THEN 'running'
            WHEN current_state IN ('completed', 'db_stored') THEN 'done'
            WHEN current_state = 'failed' THEN 'failed'
            ELSE 'pending'
        END
        WHERE current_state IS NOT NULL;
    """)
    
    # 3. 删除current_state字段
    op.drop_column('jobs', 'current_state')


def downgrade():
    """降级：恢复current_state字段（数据无法完全恢复）"""
    
    # 1. 添加current_state字段
    op.add_column('jobs', sa.Column('current_state', sa.String(50), nullable=True))
    
    # 2. 尝试从status恢复current_state（部分恢复）
    op.execute("""
        UPDATE jobs 
        SET current_state = CASE 
            WHEN status = 'waiting-file' THEN 'uploading'
            WHEN status = 'pending' THEN 'pending'
            WHEN status = 'running' THEN 'processing'
            WHEN status = 'done' THEN 'completed'
            WHEN status = 'failed' THEN 'failed'
            ELSE 'pending'
        END;
    """)
    
    # 注意：降级后无法完全恢复原始的详细状态信息
    # 所有处理中的任务都会变成通用的'processing'状态
