import os
import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# 设置PYTHONPATH以包含共享包路径（必须在所有导入之前）
alembic_dir = Path(__file__).parent.resolve()
project_root = alembic_dir.parent
monorepo_root = project_root.parent.parent
shared_python_path = monorepo_root / "packages" / "shared-python"
shared_python_path = shared_python_path.resolve()

# 确保共享包路径在sys.path的最前面
shared_path_str = str(shared_python_path)
project_path_str = str(project_root)

# 移除可能存在的路径，避免重复
if shared_path_str in sys.path:
    sys.path.remove(shared_path_str)
if project_path_str in sys.path:
    sys.path.remove(project_path_str)

# 按优先级顺序插入：共享包优先，然后是项目根目录
if shared_python_path.exists():
    sys.path.insert(0, shared_path_str)
if project_root.exists():
    sys.path.insert(1 if shared_python_path.exists() else 0, project_path_str)

# 设置环境变量
current_pythonpath = os.environ.get('PYTHONPATH', '')
if shared_path_str not in current_pythonpath:
    os.environ['PYTHONPATH'] = f"{shared_path_str}:{project_path_str}:{current_pythonpath}" if current_pythonpath else f"{shared_path_str}:{project_path_str}"

# 清除可能缓存的app模块
if 'app' in sys.modules:
    del sys.modules['app']
    modules_to_remove = [key for key in sys.modules.keys() if key.startswith('app.')]
    for key in modules_to_remove:
        del sys.modules[key]

# 导入我们的数据库配置和模型
from app.core.config import settings
from app.core.database import Base
from app.models.database import user, api_key, subscription, credits_transaction, usage_log, knowledge_base

# 创建同步数据库URL（将asyncpg替换为psycopg2）
sync_database_url = settings.DATABASE_URL.replace("asyncpg", "psycopg2")

# 获取SSL连接参数
ssl_connect_args = settings.get_ssl_connect_args()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    # 使用我们的数据库配置（同步版本）
    url = sync_database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # 使用配置的SSL参数
        connect_args=ssl_connect_args
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # 直接使用create_engine来确保SSL参数被正确传递
    from sqlalchemy import create_engine
    
    connectable = create_engine(
        sync_database_url,
        poolclass=pool.NullPool,
        connect_args=ssl_connect_args
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
