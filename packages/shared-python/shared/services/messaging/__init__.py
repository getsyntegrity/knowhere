"""
消息服务模块
提供消息发布和订阅功能
使用aio-pika实现异步消息处理
注意：message_consumer 已迁移到 API 服务
"""
from .message_publisher import (
    MessagePublisher,
    get_message_publisher,
    run_async_publish,
)

__all__ = [
    "MessagePublisher",
    "get_message_publisher",
    "run_async_publish",
]

