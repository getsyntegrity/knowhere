"""
Celery应用配置
避免循环导入问题
"""
import os
import socket

from celery import Celery
from kombu import Queue

from shared.core.config import app_config


# 生成唯一的节点名称
def get_unique_node_name():
    """生成唯一的 Celery 节点名称"""
    hostname = socket.gethostname()
    pid = os.getpid()
    return f"celery@{hostname}-{pid}"

# 创建Celery应用实例
celery_app = Celery(
    'Knowhere API',
    broker=app_config.get_celery_broker_url(),
    backend=app_config.get_celery_result_backend(),
    include=[
        'shared.core.tasks.celery_tasks',
        # 以下模块已移除，改为在各自服务启动时动态导入：
        # 'app.core.tasks.kb_tasks',  # 仅在 Worker 服务中使用
        # 'app.core.tasks.state_machine_tasks',  # 仅在 API 服务中使用
        # 'app.core.tasks.webhook_tasks',  # 仅在 API 服务中使用
        # 注意：message_handlers 不再是 Celery 任务，由 MessageConsumer 直接调用
    ]
)

# 定义优先级队列（统一任务系统）
celery_app.conf.task_queues = (
    # 知识库队列（按优先级分）
    Queue('kb_high', routing_key='kb.high',
          queue_arguments={'x-max-priority': 10}),
    Queue('kb_medium', routing_key='kb.medium',
          queue_arguments={'x-max-priority': 5}),
    Queue('kb_low', routing_key='kb.low',
          queue_arguments={'x-max-priority': 1}),
    
    # 其他任务队列
    Queue('ai_high_priority', routing_key='ai.high',
          queue_arguments={'x-max-priority': 10}),
    
    # ==========================================================
    # Webhook Queues (DLX-based non-blocking retry)
    # ==========================================================
    
    # 1. Main Work Queue - Workers consume from this
    Queue('webhook_work', routing_key='webhook.work'),
    
    # 2. Wait Queues - NO workers consume from these!
    #    RabbitMQ holds message for TTL, then dead-letters to webhook_work
    Queue('webhook_wait_1m', routing_key='webhook.wait.1m',
          queue_arguments={
              'x-message-ttl': 60000,  # 60 seconds (1 minute)
              'x-dead-letter-exchange': '',  # Default exchange
              'x-dead-letter-routing-key': 'webhook_work'  # Must match QUEUE NAME for default exchange
          }),
    Queue('webhook_wait_10m', routing_key='webhook.wait.10m',
          queue_arguments={
              'x-message-ttl': 600000,  # 600 seconds (10 minutes)
              'x-dead-letter-exchange': '',
              'x-dead-letter-routing-key': 'webhook_work'
          }),
    Queue('webhook_wait_30m', routing_key='webhook.wait.30m',
          queue_arguments={
              'x-message-ttl': 1800000,  # 1800 seconds (30 minutes)
              'x-dead-letter-exchange': '',
              'x-dead-letter-routing-key': 'webhook_work'
          }),
    Queue('webhook_wait_2h', routing_key='webhook.wait.2h',
          queue_arguments={
              'x-message-ttl': 7200000,  # 7200 seconds (2 hours)
              'x-dead-letter-exchange': '',
              'x-dead-letter-routing-key': 'webhook_work'
          }),
    Queue('webhook_wait_6h', routing_key='webhook.wait.6h',
          queue_arguments={
              'x-message-ttl': 21600000,  # 21600 seconds (6 hours)
              'x-dead-letter-exchange': '',
              'x-dead-letter-routing-key': 'webhook_work'
          }),
    
    # 3. Dead Letter Queue - Final failure destination
    Queue('webhook_dead', routing_key='webhook.dead'),
)

# 配置Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3300,  # 55 minutes soft limit
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=True,
    task_reject_on_worker_lost=True,
    task_ignore_result=True,
    result_expires=3600,  # 1小时
    # 节点名称和PID配置
    worker_hijack_root_logger=False,
    worker_log_color=False,
    # RabbitMQ特定配置
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    broker_heartbeat=30,
    broker_pool_limit=app_config.BROKER_POOL_LIMIT,
    # 任务路由配置
    task_routes={
        # Knowledge base tasks (dynamic routing)
        'app.core.tasks.kb_tasks.*': {'queue': 'kb_medium'},  # Default medium priority
        
        # Webhook tasks - route to dedicated webhook work queue
        'app.core.tasks.webhook_tasks.dispatch_webhook_task': {'queue': 'webhook_work'},
        'app.core.tasks.webhook_tasks.recover_orphaned_webhooks': {'queue': 'webhook_work'},
    },
    # Periodic tasks (Celery Beat)
    beat_schedule={
        'recover-orphaned-webhooks': {
            'task': 'app.core.tasks.webhook_tasks.recover_orphaned_webhooks',
            'schedule': 300.0,  # Every 5 minutes
        },
    },
)

def get_celery_app() -> Celery:
    """获取Celery应用实例"""
    return celery_app

def get_task_priority(task_type: str) -> int:
    """获取任务优先级"""
    return app_config.get_task_priority(task_type)

def get_queue_name(task_type: str) -> str:
    """获取队列名称"""
    return app_config.get_queue_name(task_type)
