"""
AI查询服务
统一处理AI查询任务，支持Celery和本地直连模式
"""
import asyncio
import os
import time
from typing import Any, Optional

from celery import current_task
from loguru import logger

from shared.core.exceptions.domain_exceptions import WorkerHandlingException, KnowhereException

# Local debug mode: set LOCAL_DEBUG=1 to enable
LOCAL_DEBUG = os.getenv("LOCAL_DEBUG", "0") == "1"

class AIQueryService:
    """AI查询服务"""

    def __init__(self, use_celery: bool = True):
        """
        初始化AI查询服务

        Args:
            use_celery: 是否使用Celery，False则使用本地直连模式
        """
        self.use_celery = use_celery and not LOCAL_DEBUG

    async def query_ai(
        self,
        messages: Any,
        user_id: str = "system",
        temperature: float = 0.1,
        conversation_id: Optional[str] = None,
        timeout: int = 90,
        **kwargs
    ) -> Any:
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
        # 本地调试模式：直接调用 LLM
        if LOCAL_DEBUG or not self.use_celery:
            return await self._execute_direct(
                messages, user_id, temperature, conversation_id, **kwargs
            )
        
        # 生产模式：使用 Celery
        return await self._query_with_celery(
            messages, user_id, temperature, conversation_id, timeout, **kwargs
        )

    async def _query_with_celery(
        self,
        messages: Any,
        user_id: str,
        temperature: float,
        conversation_id: Optional[str],
        timeout: int,
        **kwargs
    ) -> Any:
        """使用Celery执行AI查询"""
        try:
            if self._running_inside_celery_worker():
                return await self._execute_inline(
                    messages=messages,
                    user_id=user_id,
                    temperature=temperature,
                    conversation_id=conversation_id,
                    **kwargs,
                )

            # 延迟导入避免循环导入
            from shared.core.tasks.celery_tasks import \
                process_ai_query as celery_process_ai_query

            # 提交Celery任务
            task = celery_process_ai_query.delay(
                prompt=messages,
                user_id=user_id,
                temperature=temperature,
                conversation_id=conversation_id,
                **kwargs
            )

            # 等待任务完成（避免阻塞事件循环）
            result = await asyncio.to_thread(task.get, timeout=timeout)

            if result.get("status") == "success":
                return result.get("result", {})
            raise WorkerHandlingException(
                internal_message=f"Celery任务失败: {result.get('error', '未知错误')}"
            )

        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"Celery AI查询失败: {e}")
            raise WorkerHandlingException(
                internal_message=f"Celery AI查询失败: {str(e)}",
                original_exception=e
            )

    async def _execute_direct(
        self,
        messages: Any,
        user_id: str,
        temperature: float,
        conversation_id: Optional[str],
        **kwargs
    ) -> Any:
        """Local direct mode: call OpenAI API directly without Redis/Celery"""
        from shared.utils.OpenAICompatibleClient import OpenAICompatibleClient

        conversation = conversation_id or f"ai_query_{user_id}_{int(time.time())}"

        # Create OpenAI compatible client
        ai_client = OpenAICompatibleClient(
            redis_service=None,  # Local mode doesn't need Redis
            api_key=kwargs.get('api_key'),
            api_url=kwargs.get('api_url'),
            default_model=kwargs.get('model'),
            timeout=kwargs.get('timeout', 300)
        )
        
        # Filter out params that are already handled separately
        excluded_params = {'api_key', 'api_url', 'timeout', 'user_id', 'model', 'max_tokens'}
        api_params = {k: v for k, v in kwargs.items() if k not in excluded_params}
        
        try:
            result = await ai_client.chat_completion(
                messages=messages,
                temperature=temperature,
                conversation_id=conversation,
                model=kwargs.get('model'),
                max_tokens=kwargs.get('max_tokens'),
                **api_params
            )
            return result
        except KnowhereException:
            raise
        except Exception as exc:
            logger.error(f"Local direct AI query failed: {exc}")
            raise WorkerHandlingException(
                internal_message=f"Local direct AI query failed: {str(exc)}",
                original_exception=exc
            )

    @staticmethod
    def _running_inside_celery_worker() -> bool:
        """检测当前是否处于Celery worker上下文"""
        try:
            return bool(current_task and getattr(current_task, "request", None))
        except Exception:
            return False

    async def _execute_inline(
        self,
        messages: Any,
        user_id: str,
        temperature: float,
        conversation_id: Optional[str],
        **kwargs
    ) -> Any:
        """在当前Celery任务内直接执行AI查询，避免嵌套子任务阻塞"""
        from shared.services.redis import RedisServiceFactory, TaskRedisService
        from shared.utils.OpenAICompatibleClient import OpenAICompatibleClient

        redis_service = RedisServiceFactory.get_service()
        task_service = TaskRedisService(redis_service)

        conversation = conversation_id or f"ai_query_{user_id}_{int(time.time())}"

        await task_service.set_task_status(user_id, "正在连接AI大模型...")

        # 创建OpenAI兼容客户端，支持自定义配置
        ai_client = OpenAICompatibleClient(
            redis_service=redis_service,
            api_key=kwargs.get('api_key'),
            api_url=kwargs.get('api_url'),
            default_model=kwargs.get('model'),
            timeout=kwargs.get('timeout', 300)
        )
        
        # 只传递 API 相关参数，不传递客户端配置参数
        # 过滤掉客户端配置参数
        client_config_params = {'api_key', 'api_url', 'timeout', 'user_id'}
        api_params = {k: v for k, v in kwargs.items() if k not in client_config_params}
        
        try:
            result = await ai_client.chat_completion(
                messages=messages,
                temperature=temperature,
                conversation_id=conversation,
                model=kwargs.get('model'),
                max_tokens=kwargs.get('max_tokens'),
                **api_params
            )

            await task_service.save_task_result(
                user_id,
                {
                    "result": result,
                    "conversation_id": conversation,
                    "timestamp": time.time(),
                },
            )
            return result
        except KnowhereException:
            await task_service.mark_task_failed(user_id, str(exc))
            raise
        except Exception as exc:  # pragma: no cover - redis failure cases
            await task_service.mark_task_failed(user_id, str(exc))
            raise WorkerHandlingException(
                internal_message=f"AI查询执行失败: {str(exc)}",
                original_exception=exc
            )


# ai service instance
# default use celery, but switch to direct mode in LOCAL_DEBUG mode
ai_query_service = AIQueryService(use_celery=True)

# local direct service instance (not using Celery/Redis)
ai_query_service_local = AIQueryService(use_celery=False)
