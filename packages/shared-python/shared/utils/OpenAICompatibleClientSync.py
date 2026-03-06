"""
Synchronous OpenAI-compatible client for gevent worker tasks.
"""
import json
import os
import time
from typing import Any, Dict, List, Optional, Union

import httpx
from loguru import logger

from shared.core.config import settings
from shared.core.exceptions.domain_exceptions import LLMServiceException, UnknownException

LOCAL_DEBUG = os.getenv("LOCAL_DEBUG", "0") == "1"


class OpenAICompatibleClientSync:
    """Sync OpenAI-compatible client."""

    def __init__(
        self,
        redis_service=None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: int = 300,
        skip_redis: bool = False,
    ):
        if LOCAL_DEBUG or skip_redis or redis_service is None:
            self.redis_service = None
        else:
            from shared.services.redis.redis_sync_service import SyncRedisServiceFactory

            self.redis_service = redis_service or SyncRedisServiceFactory.get_service()

        self.default_model = default_model or getattr(settings, "NORMOL_MODEL", "deepseek-chat")
        resolved_key, resolved_url = self._resolve_api_config(
            model_name=self.default_model,
            api_key=api_key,
            api_url=api_url,
        )
        self.api_key = resolved_key
        self.api_url = resolved_url
        self.timeout = timeout

    def _resolve_api_config(
        self,
        model_name: str,
        api_key: Optional[str],
        api_url: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        if api_key and api_url:
            return api_key, api_url

        model_lower = (model_name or "").lower()
        if "qwen" in model_lower:
            resolved_key = api_key or getattr(settings, "ALI_API_KEY", None)
            ali_base = getattr(settings, "ALI_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            if ali_base and not ali_base.endswith("/chat/completions"):
                resolved_url = api_url or f"{ali_base}/chat/completions"
            else:
                resolved_url = api_url or ali_base
            return resolved_key, resolved_url

        if "doubao" in model_lower or model_lower.startswith("ep-"):
            resolved_key = api_key or getattr(settings, "ARK_API_KEY", None)
            resolved_url = api_url or getattr(settings, "ARK_URL", None)
            return resolved_key, resolved_url

        resolved_key = api_key or settings.DS_KEY
        resolved_url = api_url or settings.DS_URL
        return resolved_key, resolved_url

    def get_conversation_state(self, conversation_id: str) -> Dict[str, Any]:
        if self.redis_service is None:
            return {
                "id": conversation_id,
                "messages": [],
                "progress": 0,
                "status": "pending",
                "last_updated": time.time(),
            }

        key = f"ai_conversation:{conversation_id}"
        state_raw = self.redis_service.get(key)
        if not state_raw:
            return {
                "id": conversation_id,
                "messages": [],
                "progress": 0,
                "status": "pending",
                "last_updated": time.time(),
            }

        state = json.loads(state_raw) if isinstance(state_raw, str) else state_raw
        return {
            "id": conversation_id,
            "messages": json.loads(state.get("messages", "[]")) if isinstance(state.get("messages"), str) else state.get("messages", []),
            "progress": int(state.get("progress", 0)),
            "status": state.get("status", "pending"),
            "last_updated": float(state.get("last_updated", time.time())),
        }

    def update_conversation_state(self, conversation_state: Dict[str, Any]) -> None:
        if self.redis_service is None:
            return
        key = f"ai_conversation:{conversation_state['id']}"
        state_json = {
            "messages": conversation_state["messages"],
            "progress": str(conversation_state["progress"]),
            "status": conversation_state["status"],
            "last_updated": str(time.time()),
        }
        self.redis_service.set(key, state_json, ttl=7200)

    def chat_completion(
        self,
        messages: Union[str, List[Dict[str, str]]],
        conversation_id: str = "default",
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        top_p: Optional[float] = None,
        stream: bool = False,
        **kwargs,
    ) -> str:
        conversation_state = self.get_conversation_state(conversation_id)

        if isinstance(messages, list):
            incoming_messages = messages
        else:
            incoming_messages = [{"role": "user", "content": str(messages)}]

        if self.redis_service is None:
            all_messages = incoming_messages
        else:
            previous_messages = conversation_state.get("messages", []) or []
            all_messages = previous_messages + incoming_messages

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model or self.default_model,
            "messages": all_messages,
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if top_p is not None:
            payload["top_p"] = top_p

        allowed_api_params = {
            "n",
            "stop",
            "presence_penalty",
            "frequency_penalty",
            "logit_bias",
            "user",
            "seed",
            "tools",
            "tool_choice",
            "response_format",
            "logprobs",
            "top_logprobs",
        }
        for key, value in kwargs.items():
            if key in allowed_api_params:
                payload[key] = value

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(self.api_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            choices = data.get("choices", [])
            if not choices:
                raise LLMServiceException(
                    internal_message="AI returned empty result",
                    provider=self.default_model,
                )

            message = choices[0].get("message", {})
            content = message.get("content") or ""

            if self.redis_service is not None:
                assistant_message = {"role": message.get("role", "assistant"), "content": content}
                conversation_state["messages"] = all_messages + [assistant_message]
                conversation_state["progress"] = len(content)
                conversation_state["status"] = "completed"
                self.update_conversation_state(conversation_state)

            return content
        except httpx.HTTPStatusError as exc:
            if self.redis_service is not None:
                conversation_state["status"] = "failed"
                self.update_conversation_state(conversation_state)
            logger.error(
                f"API request failed: {exc}, response={exc.response.text if hasattr(exc, 'response') else 'N/A'}"
            )
            raise LLMServiceException(
                internal_message=f"API request failed: {str(exc)}",
                provider=self.default_model,
                status_code=exc.response.status_code if hasattr(exc, "response") else None,
                original_exception=exc,
            ) from exc
        except httpx.TimeoutException as exc:
            if self.redis_service is not None:
                conversation_state["status"] = "failed"
                self.update_conversation_state(conversation_state)
            raise LLMServiceException(
                internal_message=f"API request timeout: {str(exc)}",
                provider=self.default_model,
                original_exception=exc,
            ) from exc
        except LLMServiceException:
            raise
        except Exception as exc:
            if self.redis_service is not None:
                conversation_state["status"] = "failed"
                self.update_conversation_state(conversation_state)
            raise UnknownException(original_exception=exc) from exc

    def reset_conversation(self, conversation_id: str = "default") -> None:
        if self.redis_service is None:
            return
        self.redis_service.delete(f"ai_conversation:{conversation_id}")

