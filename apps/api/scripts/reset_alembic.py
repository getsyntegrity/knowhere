"""
重置 Alembic 迁移历史
删除 alembic_version 表中的记录，以便从头开始
"""
import os
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from shared.core.config import settings

def reset_alembic_version():
    """删除 alembic_version 表中的所有记录"""
    # 创建同步数据库URL（将asyncpg替换为psycopg2）
    sync_database_url = settings.DATABASE_URL.replace("asyncpg", "psycopg2")
    
    # 获取SSL连接参数
    ssl_connect_args = settings.get_ssl_connect_args()
    
    # 创建引擎
    engine = create_engine(
        sync_database_url,
        connect_args=ssl_connect_args
    )
    
    try:
        with engine.connect() as connection:
            # 检查表是否存在
            result = connection.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'alembic_version'
                );
            """))
            table_exists = result.scalar()
            
            if table_exists:
                # 删除表中的所有记录
                connection.execute(text("DELETE FROM alembic_version;"))
                connection.commit()
                print("✓ 已清空 alembic_version 表")
            else:
                print("✓ alembic_version 表不存在，无需清理")
                
        print("✓ Alembic 迁移历史已重置，可以重新生成初始迁移")
        
    except Exception as e:
        print(f"✗ 错误: {e}")
        sys.exit(1)
    finally:
        engine.dispose()

if __name__ == "__main__":
    reset_alembic_version()
