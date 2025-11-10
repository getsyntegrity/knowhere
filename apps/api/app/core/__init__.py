"""
核心模块统一导入接口
重构后的配置管理、Redis管理等功能
注意：共享包内容需要从共享包导入
"""

# 共享包内容 - 从共享包导入
# 注意：由于Python的模块查找机制，当从apps/api/app/core导入时，
# Python会先查找本地模块。我们需要确保共享包路径在sys.path的最前面
import sys
import os
import importlib
from pathlib import Path

# 确保共享包路径在sys.path的最前面
# 查找共享包路径（使用绝对路径）
current_file = Path(__file__).resolve()
# core/__init__.py -> app/core -> app -> apps/api -> apps -> knowhere/
# 需要向上5级才能到达monorepo根目录
monorepo_root = current_file.parent.parent.parent.parent.parent
shared_python_path = monorepo_root / "packages" / "shared-python"

if shared_python_path.exists():
    # 确保共享包路径在sys.path的最前面（优先级最高）
    shared_path_str = str(shared_python_path)
    if shared_path_str in sys.path:
        # 如果已经在路径中，移除后重新插入到最前面
        sys.path.remove(shared_path_str)
    sys.path.insert(0, shared_path_str)
    
    # 更新环境变量
    current_pythonpath = os.environ.get('PYTHONPATH', '')
    if shared_path_str not in current_pythonpath:
        os.environ['PYTHONPATH'] = f"{shared_path_str}:{current_pythonpath}" if current_pythonpath else shared_path_str

# 现在可以安全地从共享包导入
# 使用importlib来确保从共享包导入，而不是本地模块
try:
    # 先尝试直接导入（如果路径设置正确，应该能成功）
    from app.core.config import app_config, redis_config_manager, redis_pool_manager
    from app.core.database import get_db
    from app.core.security import get_password_hash, verify_password
    from app.core.constants import SystemConstants, BusinessConstants, APIConstants, ProcessingConstants
    from app.core.logging import setup_logging
except ImportError as e:
    # 如果直接导入失败，说明路径设置有问题
    # 检查sys.path，确保共享包路径在最前面
    if shared_python_path.exists():
        # 再次确保共享包路径在最前面
        shared_path_str = str(shared_python_path)
        if shared_path_str in sys.path:
            sys.path.remove(shared_path_str)
        sys.path.insert(0, shared_path_str)
        
        # 清除可能缓存的失败导入
        modules_to_remove = [k for k in sys.modules.keys() if k.startswith('app.core.')]
        for mod in modules_to_remove:
            del sys.modules[mod]
        
        # 重新尝试导入
        try:
            from app.core.config import app_config, redis_config_manager, redis_pool_manager
            from app.core.database import get_db
            from app.core.security import get_password_hash, verify_password
            from app.core.constants import SystemConstants, BusinessConstants, APIConstants, ProcessingConstants
            from app.core.logging import setup_logging
        except ImportError as e2:
            raise ImportError(
                f"无法从共享包导入模块。\n"
                f"原始错误: {e}\n"
                f"重试错误: {e2}\n"
                f"共享包路径: {shared_python_path}\n"
                f"路径存在: {shared_python_path.exists()}\n"
                f"sys.path前5项: {sys.path[:5]}\n"
                f"请确保main.py已正确设置PYTHONPATH，且共享包路径在sys.path的最前面"
            ) from e2
    else:
        raise ImportError(
            f"无法找到共享包路径: {shared_python_path}\n"
            f"请确保共享包存在于 packages/shared-python 目录"
        )

# 依赖注入 - API专用，保留在API中
from .dependencies import (
    get_current_user,
    get_redis_service,
    get_redis_service_factory
)

# 响应处理 - API专用，保留在API中
from .response import (
    ResponseCode
)

# 向后兼容的别名
settings = app_config

__all__ = [
    # 配置
    'app_config',
    'settings',  # 向后兼容
    
    # Redis
    'redis_config_manager',
    'redis_pool_manager',
    
    # 数据库
    'get_db',
    
    # 安全
    'get_password_hash',
    'verify_password',
    
    # 依赖
    'get_current_user',
    'get_redis_service',
    'get_redis_service_factory',
    
    # 响应
    'ResponseCode',
    
    # 常量
    'SystemConstants',
    'BusinessConstants',
    'APIConstants',
    'ProcessingConstants',
    
    # 日志
    'setup_logging'
]
