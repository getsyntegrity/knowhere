"""
消息队列配置
定义RabbitMQ交换器、队列和路由规则
"""
from typing import Any, Dict

from pydantic import BaseModel, Field


class MessagingConfig(BaseModel):
    """消息队列配置"""
    
    # 交换器配置
    EXCHANGE_NAME: str = Field(default="job_events", description="消息交换器名称")
    EXCHANGE_TYPE: str = Field(default="direct", description="交换器类型: direct/topic/fanout")
    
    # 队列名称
    QUEUE_STATUS_UPDATES: str = Field(default="job_status_updates", description="状态更新队列")
    QUEUE_PROGRESS_UPDATES: str = Field(default="job_progress_updates", description="进度更新队列")
    QUEUE_RESULTS: str = Field(default="job_results", description="结果数据队列")
    QUEUE_FAILURES: str = Field(default="job_failures", description="失败消息队列")
    
    # 路由键
    ROUTING_KEY_STATUS_UPDATE: str = Field(default="job.status.update", description="状态更新路由键")
    ROUTING_KEY_PROGRESS_UPDATE: str = Field(default="job.progress.update", description="进度更新路由键")
    ROUTING_KEY_RESULT: str = Field(default="job.result", description="结果数据路由键")
    ROUTING_KEY_FAILURE: str = Field(default="job.failure", description="失败消息路由键")
    
    # 消息配置
    MESSAGE_TTL: int = Field(default=86400, description="消息TTL（秒），默认24小时")
    MESSAGE_PERSISTENT: bool = Field(default=True, description="消息是否持久化")
    MESSAGE_DELIVERY_MODE: int = Field(default=2, description="消息交付模式: 1=非持久, 2=持久")
    
    # 队列配置
    QUEUE_DURABLE: bool = Field(default=True, description="队列是否持久化")
    QUEUE_AUTO_DELETE: bool = Field(default=False, description="队列是否自动删除")
    QUEUE_EXCLUSIVE: bool = Field(default=False, description="队列是否独占")
    
    # 重试配置
    PUBLISH_RETRY_COUNT: int = Field(default=3, description="消息发布重试次数")
    PUBLISH_RETRY_DELAY: float = Field(default=1.0, description="消息发布重试延迟（秒）")
    
    def get_queue_config(self, queue_name: str) -> Dict[str, Any]:
        """获取队列配置"""
        return {
            "durable": self.QUEUE_DURABLE,
            "auto_delete": self.QUEUE_AUTO_DELETE,
            "exclusive": self.QUEUE_EXCLUSIVE,
        }
    
    def get_message_properties(self) -> Dict[str, Any]:
        """获取消息属性"""
        # RabbitMQ的expiration使用字符串格式的毫秒数
        expiration_ms = self.MESSAGE_TTL * 1000
        return {
            "delivery_mode": self.MESSAGE_DELIVERY_MODE,
            "expiration": str(expiration_ms) if expiration_ms > 0 else None,  # RabbitMQ使用毫秒，None表示不过期
        }


# 创建全局消息配置实例
messaging_config = MessagingConfig()

