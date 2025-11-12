"""
状态机模块
注意：状态机管理器已迁移到 API 服务，这里只保留状态定义
"""
from .states import JobStatus

__all__ = [
    "JobStatus",
]