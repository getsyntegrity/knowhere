"""
AI查询服务
统一处理AI查询任务，支持内联执行和本地直连模式
"""
import os
import time
from typing import Any, Optional

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
            use_celery: 保留历史参数。True 使用内联执行（默认），False 使用本地直连模式。
        """
        self.use_celery = use_celery and not LOCAL_DEBUG

    async def query_ai(
        self,
        messages: Any,
        user_id: str = "system",
        temperature: float = 0.1,
        conversation_id: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        执行AI查询

        Args:
            messages: 查询消息
            user_id: 用户ID
            temperature: 温度参数
            conversation_id: 对话ID
            **kwargs: 其他参数

        Returns:
            AI查询结果
        """
        # 本地调试模式：直接调用 LLM
        if LOCAL_DEBUG or not self.use_celery:
            return await self._execute_direct(
                messages, user_id, temperature, conversation_id, **kwargs
            )

        # 统一架构：worker中只允许内联执行，不再进行嵌套Celery调用
        return await self._execute_inline(
            messages=messages,
            user_id=user_id,
            temperature=temperature,
            conversation_id=conversation_id,
            **kwargs,
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
        # 过滤掉客户端配置参数和已显式传递的参数
        client_config_params = {'api_key', 'api_url', 'timeout', 'user_id', 'model', 'max_tokens'}
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
        except KnowhereException as exc:
            await task_service.mark_task_failed(user_id, str(exc))
            raise
        except Exception as exc:  # pragma: no cover - redis failure cases
            await task_service.mark_task_failed(user_id, str(exc))
            raise WorkerHandlingException(
                internal_message=f"AI查询执行失败: {str(exc)}",
                original_exception=exc
            )


# ai service instance
# default use inline execution, but switch to direct mode in LOCAL_DEBUG mode
ai_query_service = AIQueryService(use_celery=True)

# local direct service instance (not using Celery/Redis)
ai_query_service_local = AIQueryService(use_celery=False)
