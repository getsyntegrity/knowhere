"""
AI查询服务
统一处理AI查询任务，支持Celery和ARQ两种模式
"""
import asyncio
import time
from typing import Dict, Any, Optional
from loguru import logger

from app.core.config import app_config, redis_pool_manager


class AIQueryService:
    """AI查询服务"""
    
    def __init__(self, use_celery: bool = True):
        """
        初始化AI查询服务
        
        Args:
            use_celery: 是否使用Celery，False则使用ARQ
        """
        self.use_celery = use_celery
        self.redis_pool = None
    
    async def _get_redis_pool(self):
        """获取Redis连接池"""
        if not self.redis_pool:
            self.redis_pool = await redis_pool_manager.get_pool()
        return self.redis_pool
    
    async def query_ai(
        self, 
        messages: str, 
        user_id: str = "system",
        temperature: float = 0.1,
        conversation_id: Optional[str] = None,
        timeout: int = 90,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行AI查询
        
        Args:
            messages: 查询消息
            user_id: 用户ID
            temperature: 温度参数
            conversation_id: 对话ID
            timeout: 超时时间
            **kwargs: 其他参数
            
        Returns:
            AI查询结果
        """
        if self.use_celery:
            return await self._query_with_celery(
                messages, user_id, temperature, conversation_id, timeout, **kwargs
            )
        else:
            return await self._query_with_arq(
                messages, user_id, temperature, conversation_id, timeout, **kwargs
            )
    
    async def _query_with_celery(
        self, 
        messages: str, 
        user_id: str,
        temperature: float,
        conversation_id: Optional[str],
        timeout: int,
        **kwargs
    ) -> Dict[str, Any]:
        """使用Celery执行AI查询"""
        try:
            # 延迟导入避免循环导入
            from app.core.tasks.celery_tasks import process_ai_query as celery_process_ai_query
            # 提交Celery任务
            task = celery_process_ai_query.delay(
                prompt=messages,
                user_id=user_id,
                temperature=temperature,
                conversation_id=conversation_id,
                **kwargs
            )
            
            # 等待任务完成
            result = task.get(timeout=timeout)
            
            if result.get('status') == 'success':
                return result.get('result', {})
            else:
                raise Exception(f"Celery任务失败: {result.get('error', '未知错误')}")
                
        except Exception as e:
            logger.error(f"Celery AI查询失败: {e}")
            raise
    
    async def _query_with_arq(
        self, 
        messages: str, 
        user_id: str,
        temperature: float,
        conversation_id: Optional[str],
        timeout: int,
        **kwargs
    ) -> Dict[str, Any]:
        """使用ARQ执行AI查询（向后兼容）"""
        try:
            # 获取Redis连接池
            redis_pool = await self._get_redis_pool()
            
            # 提交ARQ任务（已弃用，仅用于向后兼容）
            # 注意：ARQ已弃用，建议使用Celery模式
            raise NotImplementedError("ARQ模式已弃用，请使用Celery模式")
            
            # 等待任务完成
            result = await wait_for_job_result(job, timeout=timeout)
            
            return result
            
        except Exception as e:
            logger.error(f"ARQ AI查询失败: {e}")
            raise
    
    async def query_ai_stream(
        self,
        messages: str,
        user_id: str = "system",
        temperature: float = 0.1,
        conversation_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        执行流式AI查询（仅支持Celery）
        
        Args:
            messages: 查询消息
            user_id: 用户ID
            temperature: 温度参数
            conversation_id: 对话ID
            **kwargs: 其他参数
            
        Returns:
            流式查询结果
        """
        if not self.use_celery:
            raise NotImplementedError("流式查询仅支持Celery模式")
        
        try:
            # 提交Celery任务
            task = celery_process_ai_query.delay(
                prompt=messages,
                user_id=user_id,
                temperature=temperature,
                conversation_id=conversation_id,
                **kwargs
            )
            
            return {
                'task_id': task.id,
                'status': 'started',
                'stream_key': f"task:{user_id}:stream"
            }
            
        except Exception as e:
            logger.error(f"流式AI查询失败: {e}")
            raise


# 全局AI查询服务实例
# 默认使用Celery，可以通过环境变量配置
ai_query_service = AIQueryService(use_celery=True)

# 向后兼容的ARQ服务实例
ai_query_service_arq = AIQueryService(use_celery=False)
