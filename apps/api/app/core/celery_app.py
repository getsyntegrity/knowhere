"""
Celery应用配置
避免循环导入问题
"""
from celery import Celery
from kombu import Queue
from app.core.config import app_config

# 创建Celery应用实例
celery_app = Celery(
    'Knowhere API',
    broker=app_config.get_celery_broker_url(),
    backend=app_config.get_celery_result_backend(),
    include=[
        'app.core.tasks.celery_tasks',
        'app.core.tasks.table_fill_tasks',
        'app.core.tasks.kb_tasks'
    ]
)

# 定义优先级队列（统一任务系统）
celery_app.conf.task_queues = (
    # 表格填充队列（按优先级分）
    Queue('table_fill_high', routing_key='table_fill.high', 
          queue_arguments={'x-max-priority': 10}),
    Queue('table_fill_medium', routing_key='table_fill.medium',
          queue_arguments={'x-max-priority': 5}),
    Queue('table_fill_low', routing_key='table_fill.low',
          queue_arguments={'x-max-priority': 1}),
    
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
    Queue('document_processing', routing_key='document.processing',
          queue_arguments={'x-max-priority': 5}),
    Queue('kb_encoding', routing_key='kb.encoding',
          queue_arguments={'x-max-priority': 5}),
    Queue('batch_processing', routing_key='batch.processing',
          queue_arguments={'x-max-priority': 3}),
    Queue('analytics_queue', routing_key='analytics',
          queue_arguments={'x-max-priority': 2}),
    Queue('backup_queue', routing_key='backup',
          queue_arguments={'x-max-priority': 1}),
    Queue('log_processing', routing_key='log.processing',
          queue_arguments={'x-max-priority': 1}),
)

# 配置Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30分钟
    task_soft_time_limit=25 * 60,  # 25分钟
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=True,
    task_reject_on_worker_lost=True,
    task_ignore_result=False,
    result_expires=3600,  # 1小时
    # RabbitMQ特定配置
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    broker_heartbeat=30,
    broker_pool_limit=10,
    # 任务路由配置
    task_routes={
        # 现有任务路由
        'app.tasks.celery_tasks.process_ai_query': {'queue': 'ai_high_priority'},
        'app.tasks.celery_tasks.process_document': {'queue': 'document_processing'},
        'app.tasks.celery_tasks.encode_knowledge_base': {'queue': 'kb_encoding'},
        'app.tasks.celery_tasks.batch_file_processing': {'queue': 'batch_processing'},
        'app.tasks.celery_tasks.user_analytics': {'queue': 'analytics_queue'},
        'app.tasks.celery_tasks.data_backup': {'queue': 'backup_queue'},
        'app.tasks.celery_tasks.log_processing': {'queue': 'log_processing'},
        
        # 表格填充任务路由（动态路由）
        'app.core.tasks.table_fill_tasks.*': {'queue': 'table_fill_medium'},  # 默认中等优先级
        
        # 知识库任务路由（动态路由）
        'app.core.tasks.kb_tasks.*': {'queue': 'kb_medium'},  # 默认中等优先级
    }
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
