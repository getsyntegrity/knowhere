"""
存储适配器实现
"""
from .s3_adapter import S3StorageAdapter

# OSSStorageAdapter延迟导入，只在需要时导入（避免oss2未安装时出错）

__all__ = ['S3StorageAdapter']

# 提供延迟导入函数
def get_oss_adapter():
    """延迟导入OSSStorageAdapter"""
    from .oss_adapter import OSSStorageAdapter
    return OSSStorageAdapter

__all__.append('get_oss_adapter')

