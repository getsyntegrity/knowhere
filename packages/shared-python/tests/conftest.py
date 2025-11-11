"""
Pytest配置文件
设置测试环境和mock
"""
import os
import sys
from unittest.mock import MagicMock, patch, AsyncMock
from contextlib import asynccontextmanager

# 在导入应用代码之前设置必要的环境变量
os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://test:test@localhost/test')
os.environ.setdefault('SECRET_KEY', 'test_secret_key')
os.environ.setdefault('DS_KEY', 'test_ds_key')
os.environ.setdefault('DS_URL', 'https://test.ds.url')
os.environ.setdefault('S3_BUCKET_NAME', 'test-bucket')
os.environ.setdefault('S3_ACCESS_KEY_ID', 'test_key')
os.environ.setdefault('S3_SECRET_ACCESS_KEY', 'test_secret')
os.environ.setdefault('S3_TEMP_PATH', '/tmp')
os.environ.setdefault('TMP_PATH', '/tmp')
os.environ.setdefault('FONT_PATH', '/tmp/fonts')
os.environ.setdefault('CHROMEDRIVER_PATH', '/tmp/chromedriver')
os.environ.setdefault('RABBITMQ_HOST', 'localhost')
os.environ.setdefault('RABBITMQ_PORT', '5672')
os.environ.setdefault('RABBITMQ_USER', 'admin')
os.environ.setdefault('RABBITMQ_PASSWORD', 'admin123')
os.environ.setdefault('RABBITMQ_VHOST', '/')
os.environ.setdefault('REDIS_HOST', 'localhost')
os.environ.setdefault('REDIS_PORT', '6379')

# Mock数据库引擎，避免在测试时创建真实连接
# 需要在导入app模块之前进行mock
@patch('sqlalchemy.ext.asyncio.create_async_engine')
def mock_database(mock_create_engine):
    """Mock数据库引擎创建"""
    mock_engine = MagicMock()
    mock_create_engine.return_value = mock_engine
    return mock_engine

# 在导入前应用mock
mock_database()

# Mock get_db_context
original_get_db_context = None
try:
    from app.core.database import get_db_context
    original_get_db_context = get_db_context
except ImportError:
    pass

@asynccontextmanager
async def mock_get_db_context():
    """Mock数据库上下文"""
    mock_db = AsyncMock()
    yield mock_db

# 如果get_db_context存在，替换它
if 'app.core.database' in sys.modules:
    sys.modules['app.core.database'].get_db_context = mock_get_db_context

