"""
Sync AI query service for Celery gevent worker tasks.
"""
from typing import Any, Optional

from loguru import logger

from shared.core.exceptions.domain_exceptions import KnowhereException, WorkerHandlingException
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
        ai_client = OpenAICompatibleClientSync(
            api_key=kwargs.get("api_key"),
            api_url=kwargs.get("api_url"),
            default_model=kwargs.get("model"),
            timeout=kwargs.get("timeout", 300),
        )

        client_config_params = {"api_key", "api_url", "timeout", "user_id", "model", "max_tokens"}
        api_params = {k: v for k, v in kwargs.items() if k not in client_config_params}

        try:
            return ai_client.chat_completion(
                messages=messages,
                temperature=temperature,
                model=kwargs.get("model"),
                max_tokens=kwargs.get("max_tokens"),
                **api_params,
            )
        except KnowhereException:
            raise
        except Exception as exc:
            logger.error(f"Sync AI query failed: {exc}")
            raise WorkerHandlingException(
                internal_message=f"AI查询执行失败: {str(exc)}",
                original_exception=exc,
            )


sync_ai_query_service = SyncAIQueryService()
