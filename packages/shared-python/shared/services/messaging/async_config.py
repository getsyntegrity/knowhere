"""
异步消息配置适配器
将现有messaging_config适配为aio-pika格式
"""
import os
import socket
from typing import Any, Dict
from urllib.parse import urlparse

from shared.core.config import app_config
from shared.core.config.messaging import messaging_config


def get_rabbitmq_url() -> str:
    """获取RabbitMQ连接URL"""
    return app_config.get_rabbitmq_url()


def parse_rabbitmq_url(url: str) -> Dict[str, Any]:
    """
    解析RabbitMQ URL为连接参数
    
    Args:
        url: RabbitMQ连接URL，格式: amqp://user:password@host:port/vhost
        
    Returns:
        包含连接参数的字典
    """
    parsed = urlparse(url)
    
    # 处理virtualhost：如果路径是"/"或空，返回"/"，否则去掉前导斜杠
    if not parsed.path or parsed.path == "/":
        virtualhost = "/"
    else:
        virtualhost = parsed.path.lstrip("/")
    
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5672,
        "login": parsed.username or "guest",  # aio-pika使用login而不是username
        "password": parsed.password or "guest",
        "virtualhost": virtualhost,
    }


def get_connection_params() -> Dict[str, Any]:
    """获取aio-pika连接参数"""
    # 直接从配置读取，避免 URL 编码/解码问题
    # 特别是当用户名或密码包含特殊字符时，直接使用原始值更可靠
    params = {
        "host": app_config.RABBITMQ_HOST,
        "port": app_config.RABBITMQ_PORT,
        "login": app_config.RABBITMQ_USER,  # 直接使用，不进行 URL 编码
        "password": app_config.RABBITMQ_PASSWORD,  # 直接使用，不进行 URL 编码
        "virtualhost": app_config.RABBITMQ_VHOST,
        "MESSAGE_BROKER_TYPE": app_config.MESSAGE_BROKER_TYPE,
        "CELERY_BROKER_URL": app_config.CELERY_BROKER_URL,
        "client_properties": {
            "application_name": "knowhere_api",
            "connection_name": f"api-consumer@{socket.gethostname()}-{os.getpid()}",
        },
        "heartbeat": 30,  # 心跳间隔（秒）
        "blocked_connection_timeout": 60,  # 阻塞连接超时（秒）
    }
    
    return params


def get_exchange_config() -> Dict[str, Any]:
    """获取交换器配置"""
    return {
        "name": messaging_config.EXCHANGE_NAME,
        "type": messaging_config.EXCHANGE_TYPE,
        "durable": True,
        "auto_delete": False,
    }


def get_queue_config(queue_name: str) -> Dict[str, Any]:
    """获取队列配置"""
    base_config = messaging_config.get_queue_config(queue_name)
    
    return {
        "durable": base_config.get("durable", messaging_config.QUEUE_DURABLE),
        "auto_delete": base_config.get("auto_delete", messaging_config.QUEUE_AUTO_DELETE),
        "exclusive": base_config.get("exclusive", messaging_config.QUEUE_EXCLUSIVE),
        "arguments": base_config.get("queue_arguments", {}),
    }


def get_message_properties(priority: int = None, expiration: int = None) -> Dict[str, Any]:
    """
    获取消息属性
    
    Args:
        priority: 消息优先级
        expiration: 消息过期时间（秒）
        
    Returns:
        消息属性字典
    """
    props = messaging_config.get_message_properties()
    
    result = {
        "delivery_mode": props.get("delivery_mode", 2),  # 持久化
    }
    
    if priority is not None:
        result["priority"] = priority
    
    if expiration is not None and expiration > 0:
        # aio-pika使用毫秒，需要整数类型
        result["expiration"] = expiration * 1000
    elif props.get("expiration"):
        # 如果从props获取的是字符串，转换为整数
        expiration_value = props["expiration"]
        if isinstance(expiration_value, str):
            result["expiration"] = int(expiration_value)
        else:
            result["expiration"] = expiration_value
    
    return result


def get_routing_key(message_type: str) -> str:
    """根据消息类型获取路由键"""
    routing_keys = {
        "job_status_update": messaging_config.ROUTING_KEY_STATUS_UPDATE,
        "job_progress_update": messaging_config.ROUTING_KEY_PROGRESS_UPDATE,
        "job_result": messaging_config.ROUTING_KEY_RESULT,
        "job_failure": messaging_config.ROUTING_KEY_FAILURE,
    }
    return routing_keys.get(message_type, messaging_config.ROUTING_KEY_STATUS_UPDATE)


def get_queue_name(message_type: str) -> str:
    """根据消息类型获取队列名称"""
    queue_names = {
        "job_status_update": messaging_config.QUEUE_STATUS_UPDATES,
        "job_progress_update": messaging_config.QUEUE_PROGRESS_UPDATES,
        "job_result": messaging_config.QUEUE_RESULTS,
        "job_failure": messaging_config.QUEUE_FAILURES,
    }
    return queue_names.get(message_type, messaging_config.QUEUE_STATUS_UPDATES)

