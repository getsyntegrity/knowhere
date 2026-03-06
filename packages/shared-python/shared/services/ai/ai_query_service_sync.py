"""
Sync AI query service for Celery gevent worker tasks.
"""
import time
from typing import Any, Optional

from loguru import logger

from shared.core.exceptions.domain_exceptions import KnowhereException, WorkerHandlingException
from shared.services.redis.redis_sync_service import SyncRedisServiceFactory, SyncTaskRedisService
from shared.utils.OpenAICompatibleClientSync import OpenAICompatibleClientSync


class SyncAIQueryService:
    """Synchronous AI query service."""

    def query_ai(
        self,
        messages: Any,
        user_id: str = "system",
        temperature: float = 0.1,
        conversation_id: Optional[str] = None,
        **kwargs,
    ) -> Any:
        redis_service = SyncRedisServiceFactory.get_service()
        task_service = SyncTaskRedisService(redis_service)
        task_service.set_task_status(user_id, "正在连接AI大模型...")

        conversation = conversation_id or f"ai_query_{user_id}_{int(time.time())}"
        ai_client = OpenAICompatibleClientSync(
            redis_service=redis_service,
            api_key=kwargs.get("api_key"),
            api_url=kwargs.get("api_url"),
            default_model=kwargs.get("model"),
            timeout=kwargs.get("timeout", 300),
        )

        client_config_params = {"api_key", "api_url", "timeout", "user_id", "model", "max_tokens"}
        api_params = {k: v for k, v in kwargs.items() if k not in client_config_params}

        try:
            result = ai_client.chat_completion(
                messages=messages,
                temperature=temperature,
                conversation_id=conversation,
                model=kwargs.get("model"),
                max_tokens=kwargs.get("max_tokens"),
                **api_params,
            )
            task_service.save_task_result(
                user_id,
                {
                    "result": result,
                    "conversation_id": conversation,
                    "timestamp": time.time(),
                },
            )
            return result
        except KnowhereException as exc:
            task_service.mark_task_failed(user_id, str(exc))
            raise
        except Exception as exc:
            logger.error(f"Sync AI query failed: {exc}")
            task_service.mark_task_failed(user_id, str(exc))
            raise WorkerHandlingException(
                internal_message=f"AI查询执行失败: {str(exc)}",
                original_exception=exc,
            )


sync_ai_query_service = SyncAIQueryService()

