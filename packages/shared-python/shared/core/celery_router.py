"""
Celery任务路由器 - 基于用户订阅的动态路由
整合了TaskPriorityService的优先级计算逻辑
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

from loguru import logger

from shared.core.celery_app import get_celery_app

# 注意：get_queue_for_job 已简化，不再需要直接访问数据库


class TaskType(Enum):
    """任务类型枚举"""
    AI_QUERY = "ai_query"
    USER_AUTH = "user_auth"
    URGENT_DOCUMENT = "urgent_document"
    DOCUMENT_PROCESSING = "document_processing"
    KB_ENCODING = "kb_encoding"
    BATCH_PROCESSING = "batch_processing"
    ANALYTICS = "analytics"
    BACKUP = "backup"
    LOG_PROCESSING = "log_processing"
    KB_MANAGEMENT = "kb_management"

class UserLevel(Enum):
    """用户等级枚举"""
    VIP = "vip"
    PREMIUM = "premium"
    STANDARD = "standard"
    BASIC = "basic"

class DocumentImportance(Enum):
    """文档重要性枚举"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class TaskContext:
    """任务上下文"""
    task_type: TaskType
    user_id: str
    user_level: UserLevel = UserLevel.STANDARD
    document_importance: DocumentImportance = DocumentImportance.MEDIUM
    is_urgent: bool = False
    resource_requirements: str = "medium"
    estimated_duration: int = 300  # 秒
    retry_count: int = 0
    metadata: Dict[str, Any] = None


class CeleryTaskRouter:
    """Celery任务路由器"""
    
    def __init__(self):
        self.celery_app = get_celery_app()
        # 注意：get_queue_for_job 已简化，不再需要 subscription_repo
        
        # 基础优先级配置（从TaskPriorityService迁移）
        self.base_priorities = {
            TaskType.AI_QUERY: 10,
            TaskType.USER_AUTH: 10,
            TaskType.URGENT_DOCUMENT: 10,
            TaskType.DOCUMENT_PROCESSING: 5,
            TaskType.KB_ENCODING: 5,
            TaskType.BATCH_PROCESSING: 5,
            TaskType.ANALYTICS: 1,
            TaskType.BACKUP: 1,
            TaskType.LOG_PROCESSING: 1,
            TaskType.KB_MANAGEMENT: 6,
        }
        
        # 用户等级权重
        self.user_level_weights = {
            UserLevel.VIP: 1.2,
            UserLevel.PREMIUM: 1.1,
            UserLevel.STANDARD: 1.0,
            UserLevel.BASIC: 0.9,
        }
        
        # 文档重要性权重
        self.document_importance_weights = {
            DocumentImportance.CRITICAL: 1.3,
            DocumentImportance.HIGH: 1.1,
            DocumentImportance.MEDIUM: 1.0,
            DocumentImportance.LOW: 0.8,
        }
        
        # 紧急任务权重
        self.urgent_weight = 1.5
        
        # 重试惩罚权重
        self.retry_penalty = 0.1
    
    def calculate_priority(self, context: TaskContext) -> int:
        """
        计算任务优先级（从TaskPriorityService迁移）
        
        Args:
            context: 任务上下文
            
        Returns:
            计算后的优先级 (1-10)
        """
        try:
            # 获取基础优先级
            base_priority = self.base_priorities.get(context.task_type, 5)
            
            # 应用用户等级权重
            user_weight = self.user_level_weights.get(context.user_level, 1.0)
            
            # 应用文档重要性权重
            doc_weight = self.document_importance_weights.get(context.document_importance, 1.0)
            
            # 应用紧急任务权重
            urgent_weight = self.urgent_weight if context.is_urgent else 1.0
            
            # 应用重试惩罚
            retry_penalty = 1.0 - (context.retry_count * self.retry_penalty)
            retry_penalty = max(0.1, retry_penalty)  # 最小权重0.1
            
            # 计算最终优先级
            final_priority = base_priority * user_weight * doc_weight * urgent_weight * retry_penalty
            
            # 限制在1-10范围内
            final_priority = max(1, min(10, int(final_priority)))
            
            logger.debug(f"任务优先级计算: 基础={base_priority}, 用户权重={user_weight}, "
                        f"文档权重={doc_weight}, 紧急权重={urgent_weight}, "
                        f"重试惩罚={retry_penalty}, 最终={final_priority}")
            
            return final_priority
            
        except Exception as e:
            logger.error(f"计算任务优先级失败: {e}")
            return 5  # 默认中等优先级
    
    def create_task_context(self, task_type: str, user_id: str, **kwargs) -> TaskContext:
        """
        创建任务上下文（从TaskPriorityService迁移）
        
        Args:
            task_type: 任务类型
            user_id: 用户ID
            **kwargs: 其他参数
            
        Returns:
            任务上下文
        """
        try:
            # 解析任务类型
            task_type_enum = TaskType(task_type)
            
            # 解析用户等级
            user_level = UserLevel(kwargs.get('user_level', 'standard'))
            
            # 解析文档重要性
            document_importance = DocumentImportance(kwargs.get('document_importance', 'medium'))
            
            return TaskContext(
                task_type=task_type_enum,
                user_id=user_id,
                user_level=user_level,
                document_importance=document_importance,
                is_urgent=kwargs.get('is_urgent', False),
                resource_requirements=kwargs.get('resource_requirements', 'medium'),
                estimated_duration=kwargs.get('estimated_duration', 300),
                retry_count=kwargs.get('retry_count', 0),
                metadata=kwargs.get('metadata', {})
            )
        except Exception as e:
            logger.error(f"创建任务上下文失败: {e}")
            # 返回默认上下文
            return TaskContext(
                task_type=TaskType.DOCUMENT_PROCESSING,
                user_id=user_id,
                metadata=kwargs.get('metadata', {})
            )
    
    def get_queue_for_job(self, job_type: str, user_id: str) -> str:
        """
        根据用户订阅级别获取队列名称
        
        Args:
            job_type: 任务类型 (kb_management, ai_query, document_processing, etc.)
            user_id: 用户ID
            
        Returns:
            str: 队列名称
        """
        try:
            # TODO:简化版本：直接返回默认队列，避免异步操作（后续优化）
            priority_level = 1  # 默认Free订阅
            
            # 根据任务类型和优先级选择队列
            if job_type in ["kb_management", "kb_encoding"]:
                if priority_level >= 9:
                    return "kb_high"
                elif priority_level >= 5:
                    return "kb_medium"
                else:
                    return "kb_low"
            elif job_type in ["ai_query", "user_auth", "urgent_document"]:
                return "ai_high_priority"
            elif job_type in ["document_processing"]:
                return "document_processing"
            elif job_type in ["batch_processing"]:
                return "batch_processing"
            elif job_type in ["analytics"]:
                return "analytics_queue"
            elif job_type in ["backup"]:
                return "backup_queue"
            elif job_type in ["log_processing"]:
                return "log_processing"
            else:
                # 默认中等优先级
                return f"{job_type}_medium"
                
        except Exception as e:
            logger.error(f"获取用户 {user_id} 队列失败: {e}")
            # 默认返回中等优先级队列
            if job_type in ["kb_management", "kb_encoding"]:
                return "kb_medium"
            elif job_type in ["ai_query", "user_auth", "urgent_document"]:
                return "ai_high_priority"
            else:
                return "default"
    
    def route_task(self, name, args, kwargs, options, task=None, **kwds):
        """
        Celery任务路由函数
        
        这个函数会被Celery调用来自动路由任务
        支持基于任务类型和用户优先级的动态路由
        """
        try:
            # 从kwargs中提取job_type和user_id
            job_type = kwargs.get('job_type')
            user_id = kwargs.get('user_id')
            
            # 如果kwargs中没有user_id，尝试从args中提取（针对upload_url_file_task）
            if not user_id and len(args) >= 3:
                user_id = args[2]  # upload_url_file_task的第三个参数是user_id
            
            if job_type and user_id:
                # 创建任务上下文并计算优先级
                context = self.create_task_context(
                    task_type=job_type,
                    user_id=user_id,
                    user_level=kwargs.get('user_level', 'standard'),
                    document_importance=kwargs.get('document_importance', 'medium'),
                    is_urgent=kwargs.get('is_urgent', False),
                    retry_count=kwargs.get('retry_count', 0),
                    metadata=kwargs.get('metadata', {})
                )
                
                # 获取队列名称
                queue_name = self.get_queue_for_job(job_type, user_id)
                
                # 计算优先级
                priority = self.calculate_priority(context)
                
                logger.info(f"路由任务 {name} 到队列 {queue_name} (用户: {user_id}, 类型: {job_type}, 优先级: {priority})")
                
                return {
                    'queue': queue_name,
                    'priority': priority
                }
            else:
                # 使用默认路由
                return None
                
        except Exception as e:
            logger.error(f"任务路由失败: {e}")
            return None


# Create router instance
task_router = CeleryTaskRouter()

# Register router with Celery - combine function routing and static routing
celery_app = get_celery_app()

# Save static routes configured in celery_app.py
static_routes = celery_app.conf.task_routes.copy() if isinstance(celery_app.conf.task_routes, dict) else {}

# Celery supports router list: try function router first, fallback to static dict
# 1. task_router.route_task: Dynamic routing (based on user subscription, for kb_tasks)
# 2. static_routes: Static routing (webhook and other fixed routes, from celery_app.py)
celery_app.conf.task_routes = [
    task_router.route_task,  # Dynamic routing priority
    static_routes,           # Fallback to static configuration
]



