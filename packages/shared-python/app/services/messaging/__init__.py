"""
消息服务模块
提供消息发布和订阅功能
"""
from .message_consumer import MessageConsumer, get_message_consumer
from .message_publisher import MessagePublisher, get_message_publisher

__all__ = [
    "MessagePublisher",
    "get_message_publisher",
    "MessageConsumer",
    "get_message_consumer",
]

# 创建全局消息发布器实例（延迟初始化）
_message_publisher: MessagePublisher = None


def get_message_publisher_instance() -> MessagePublisher:
    """获取消息发布器实例（单例模式）"""
    global _message_publisher
    if _message_publisher is None:
        _message_publisher = MessagePublisher()
    return _message_publisher

