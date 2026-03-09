"""
Synchronous OpenAI-compatible client for gevent worker tasks.
"""
import os
from typing import Any, Dict, List, Optional, Union

import httpx
from loguru import logger

from shared.core.config import settings
from shared.core.exceptions.domain_exceptions import LLMServiceException, UnknownException
from shared.utils.http_clients import get_sync_client
from shared.utils.concurrency_limits import concurrency_limit

LOCAL_DEBUG = os.getenv("LOCAL_DEBUG", "0") == "1"


class OpenAICompatibleClientSync:
    """Sync OpenAI-compatible client."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: int = 300,
    ):
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

    def chat_completion(
        self,
        messages: Union[str, List[Dict[str, str]]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        top_p: Optional[float] = None,
        stream: bool = False,
        **kwargs,
    ) -> str:
        if isinstance(messages, list):
            all_messages = messages
        else:
            all_messages = [{"role": "user", "content": str(messages)}]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: Dict[str, Any] = {
            "model": model or self.default_model,
            "messages": all_messages,
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if top_p is not None:
            payload["top_p"] = top_p

        allowed_api_params = {
            "n", "stop", "presence_penalty", "frequency_penalty",
            "logit_bias", "user", "seed", "tools", "tool_choice",
            "response_format", "logprobs", "top_logprobs",
        }
        for key, value in kwargs.items():
            if key in allowed_api_params:
                payload[key] = value

        try:
            client = get_sync_client()
            with concurrency_limit("llm_http"):
                response = client.post(self.api_url, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()

            choices = data.get("choices", [])
            if not choices:
                raise LLMServiceException(
                    internal_message="AI returned empty result",
                    provider=self.default_model,
                )

            content = choices[0].get("message", {}).get("content") or ""
            return content
        except httpx.HTTPStatusError as exc:
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
            raise LLMServiceException(
                internal_message=f"API request timeout: {str(exc)}",
                provider=self.default_model,
                original_exception=exc,
            ) from exc
        except LLMServiceException:
            raise
        except Exception as exc:
            raise UnknownException(original_exception=exc) from exc
