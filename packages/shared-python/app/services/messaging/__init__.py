"""
消息服务模块
提供消息发布和订阅功能
注意：message_consumer 已迁移到 API 服务
"""
from .message_publisher import MessagePublisher, get_message_publisher

__all__ = [
    "MessagePublisher",
    "get_message_publisher",
]

# 创建全局消息发布器实例（延迟初始化）
_message_publisher: MessagePublisher = None


def get_message_publisher_instance() -> MessagePublisher:
    """获取消息发布器实例（单例模式）"""
    global _message_publisher
    if _message_publisher is None:
        _message_publisher = MessagePublisher()
    return _message_publisher

