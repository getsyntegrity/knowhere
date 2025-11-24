"""
Celery配置
"""
from typing import Dict

from pydantic import BaseModel, Field


class CeleryConfig(BaseModel):
    """Celery配置"""
    
    # RabbitMQ配置
    RABBITMQ_HOST: str = Field(default="localhost", description="RabbitMQ主机")
    RABBITMQ_PORT: int = Field(default=5672, description="RabbitMQ端口")
    RABBITMQ_USER: str = Field(default="admin", description="RabbitMQ用户名")
    RABBITMQ_PASSWORD: str = Field(default="admin123", description="RabbitMQ密码")
    RABBITMQ_VHOST: str = Field(default="/", description="RabbitMQ虚拟主机")
    
    # Celery配置 - 使用RabbitMQ作为消息代理
    CELERY_BROKER_URL: str = Field(default="amqp://guest:guest@localhost:5672//", description="Celery消息代理URL")
    CELERY_RESULT_BACKEND: str = Field(default="rpc://", description="Celery结果后端URL")
    
    # Redis配置（用于结果后端，可选）
    CELERY_RESULT_BACKEND_REDIS: str = Field(default="redis://localhost:6379/2", description="Redis结果后端URL（可选）")
    
    # 消息代理类型
    MESSAGE_BROKER_TYPE: str = Field(default="rabbitmq", description="消息代理类型: rabbitmq 或 redis")
    
    # 任务优先级配置
    TASK_PRIORITIES: Dict[str, int] = Field(default={
        'ai_query': 10,
        'user_auth': 10,
        'urgent_document': 10,
        'document_processing': 5,
        'kb_encoding': 5,
        'batch_processing': 5,
        'analytics': 1,
        'backup': 1,
        'log_processing': 1,
    }, description="任务优先级配置")
    
    # 队列配置映射
    QUEUE_MAPPING: Dict[str, str] = Field(default={
        'ai_query': 'ai_high_priority',
        'user_auth': 'auth_queue',
        'urgent_document': 'document_urgent',
        'document_processing': 'document_processing',
        'kb_encoding': 'kb_encoding',
        'batch_processing': 'batch_processing',
        'analytics': 'analytics_queue',
        'backup': 'backup_queue',
        'log_processing': 'log_processing',
    }, description="队列配置映射")
    
    def get_task_priority(self, task_type: str) -> int:
        """获取任务优先级"""
        return self.TASK_PRIORITIES.get(task_type, 5)
    
    def get_queue_name(self, task_type: str) -> str:
        """获取队列名称"""
        return self.QUEUE_MAPPING.get(task_type, 'default')
    
    def get_rabbitmq_url(self) -> str:
        """构建RabbitMQ连接URL"""
        if self.RABBITMQ_USER and self.RABBITMQ_PASSWORD:
            # 直接使用原始值，不进行 URL 编码
            # Celery/kombu 在解析 URL 时会自动处理特殊字符
            return f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASSWORD}@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}{self.RABBITMQ_VHOST}"
        else:
            return f"amqp://{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}{self.RABBITMQ_VHOST}"
    
    def get_celery_broker_url(self) -> str:
        """获取Celery消息代理URL"""
        if self.MESSAGE_BROKER_TYPE == "rabbitmq":
            return self.get_rabbitmq_url()
        else:
            return self.CELERY_BROKER_URL
    
    def get_celery_result_backend(self) -> str:
        """获取Celery结果后端URL"""
        if self.MESSAGE_BROKER_TYPE == "rabbitmq":
            return self.CELERY_RESULT_BACKEND
        else:
            return self.CELERY_RESULT_BACKEND_REDIS
