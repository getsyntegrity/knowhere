"""
状态机配置管理
"""
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class StateMachineConfig:
    """状态机配置"""
    
    max_retries: int = 3  # 最大重试次数
    base_retry_delay: float = 0.1  # 基础重试延迟（秒）
    
    # 超时配置（用于Redis Keyspace Notifications）
    state_timeouts: Dict[str, int] = None
    
    # 同步配置
    sync_batch_size: int = 100  # 批量同步大小
    sync_interval: int = 300  # 同步间隔（秒）
    
    # 维护配置
    maintenance_interval: int = 3600  # 维护间隔（秒）
    cleanup_interval: int = 1800  # 清理间隔（秒）
    
    # Redis Keyspace Notifications配置
    enable_keyspace_notifications: bool = True  # 启用Keyspace Notifications
    
    def __post_init__(self):
        if self.state_timeouts is None:
            self.state_timeouts = {
                "pending": 300,      # 5分钟
                "uploading": 600,    # 10分钟
                "processing": 1800,  # 30分钟
                "completed": 0,      # 无超时
                "failed": 0,         # 无超时
            }


# 默认配置
DEFAULT_CONFIG = StateMachineConfig()


def get_state_machine_config() -> StateMachineConfig:
    """获取状态机配置"""
    return DEFAULT_CONFIG


def update_state_machine_config(**kwargs) -> StateMachineConfig:
    """更新状态机配置"""
    global DEFAULT_CONFIG
    DEFAULT_CONFIG = StateMachineConfig(**kwargs)
    return DEFAULT_CONFIG
