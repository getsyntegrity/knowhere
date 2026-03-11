"""
Synchronous OpenAI-compatible client for gevent worker tasks.
Uses the official OpenAI SDK with shared httpx connection pooling
and built-in 429 retry with exponential backoff.

For Aliyun (qwen) models, api keys are drawn from the AliQuotaManager
token pool and automatically rotated on 429 RateLimitError.
"""
import os
import threading
from typing import Any, Dict, List, Optional, Union

import openai
from loguru import logger
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from shared.core.config import settings
from shared.core.exceptions.domain_exceptions import LLMServiceException
from shared.utils.http_clients import get_sync_client

LOCAL_DEBUG = os.getenv("LOCAL_DEBUG", "0") == "1"

_client_cache: Dict[tuple, "OpenAICompatibleClientSync"] = {}
_client_cache_lock = threading.Lock()




def _is_ali_model(model_name: str) -> bool:
    """Check whether a model name routes to Aliyun DashScope."""
    return "qwen" in (model_name or "").lower()


class OpenAICompatibleClientSync:
    """Sync OpenAI-compatible client backed by the official OpenAI SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: int = 300,
        max_retries: int = 2,
    ):
        self.default_model = default_model or getattr(settings, "NORMOL_MODEL", "deepseek-chat")
        self._explicit_api_key = api_key
        self._explicit_api_url = api_url
        self._max_retries = max_retries

        resolved_key, resolved_url = self._resolve_api_config(
            model_name=self.default_model,
            api_key=api_key,
            api_url=api_url,
        )
        self.timeout = (
            getattr(settings, "OPENAI_CLIENT_TIMEOUT", 300)
            if timeout is None
            else timeout
        )
        self._client = OpenAI(
            api_key=resolved_key,
            base_url=resolved_url,
            http_client=get_sync_client(),
            max_retries=max_retries,
            timeout=self.timeout,
        )

    @staticmethod
    def _strip_chat_completions(url: Optional[str]) -> Optional[str]:
        """Strip /chat/completions suffix so the OpenAI SDK can append it."""
        if url and url.rstrip("/").endswith("/chat/completions"):
            return url.rstrip("/").removesuffix("/chat/completions")
        return url

    def _resolve_api_config(
        self,
        model_name: str,
        api_key: Optional[str],
        api_url: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        if api_key and api_url:
            return api_key, self._strip_chat_completions(api_url)

        model_lower = (model_name or "").lower()
        if "qwen" in model_lower:
            resolved_key = api_key or getattr(settings, "ALI_API_KEY", None)
            ali_base = getattr(settings, "ALI_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
            resolved_url = api_url or ali_base
            return resolved_key, self._strip_chat_completions(resolved_url)

        if "glm" in model_lower:
            resolved_key = api_key or getattr(settings, "GLM_API_KEY", None)
            glm_base = getattr(settings, "GLM_URL", "https://open.bigmodel.cn/api/paas/v4")
            if glm_base and not glm_base.endswith("/chat/completions"):
                resolved_url = api_url or f"{glm_base}/chat/completions"
            else:
                resolved_url = api_url or glm_base
            return resolved_key, resolved_url

        if "doubao" in model_lower or model_lower.startswith("ep-"):
            resolved_key = api_key or getattr(settings, "ARK_API_KEY", None)
            resolved_url = api_url or getattr(settings, "ARK_URL", None)
            return resolved_key, self._strip_chat_completions(resolved_url)

        resolved_key = api_key or settings.DS_KEY
        resolved_url = api_url or settings.DS_URL
        return resolved_key, self._strip_chat_completions(resolved_url)

    # ------------------------------------------------------------------
    # Ali token-pool helpers
    # ------------------------------------------------------------------

    def _should_use_ali_pool(self) -> bool:
        """Whether to route through the AliQuotaManager instead of a fixed key."""
        if self._explicit_api_key:
            return False
        return _is_ali_model(self.default_model)

    def _make_ali_pool_call(
        self,
        model: str,
        all_messages: List[ChatCompletionMessageParam],
        temperature: float,
        max_tokens: int,
        api_kwargs: Dict[str, Any],
    ) -> str:
        """Acquire a token, make the call, and retry inline on 429."""
        from shared.utils.ali_quota_manager import get_ali_quota_manager

        quota_manager = get_ali_quota_manager()

        max_retries = settings.ALI_INLINE_MAX_RETRIES
        for attempt in range(max_retries):
            lease = quota_manager.acquire_request(operation="chat_completion")
            try:
                # Build a per-request client with the leased api_key
                client = OpenAI(
                    api_key=lease.api_key,
                    base_url=str(self._client.base_url),
                    http_client=get_sync_client(),
                    max_retries=0,  # we handle retries ourselves
                    timeout=self.timeout,
                )
                response = client.chat.completions.create(
                    model=model,
                    messages=all_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **api_kwargs,
                )
                choices = response.choices
                if not choices:
                    raise LLMServiceException(
                        internal_message="AI returned empty result",
                        provider=self.default_model,
                    )
                return choices[0].message.content or ""
            except openai.RateLimitError as exc:
                retry_after = _parse_retry_after(exc)
                quota_manager.mark_rate_limited(lease.token_id, retry_after)
                logger.warning(
                    f"Ali token {lease.token_id} rate-limited (attempt {attempt + 1}/{max_retries}), "
                    f"cooling down {retry_after}s and retrying with next token"
                )
                if attempt == max_retries - 1:
                    raise LLMServiceException(
                        internal_message=f"All Ali tokens exhausted after {max_retries} retries: {exc}",
                        provider=self.default_model,
                        original_exception=exc,
                    ) from exc
        # unreachable but satisfies the type checker
        raise LLMServiceException(
            internal_message="Ali token pool retry loop exited unexpectedly",
            provider=self.default_model,
        )

    # ------------------------------------------------------------------

    def chat_completion(
        self,
        messages: Union[str, List[ChatCompletionMessageParam]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        top_p: Optional[float] = None,
        timeout: Optional[int] = None,
        **kwargs,
    ) -> str:
        all_messages: List[ChatCompletionMessageParam]
        if isinstance(messages, list):
            all_messages = messages  # type: ignore[assignment]
        else:
            all_messages = [{"role": "user", "content": str(messages)}]

        api_kwargs: Dict[str, Any] = {}
        if top_p is not None:
            api_kwargs["top_p"] = top_p
        if timeout is not None:
            api_kwargs["timeout"] = timeout

        allowed_api_params = {
            "n", "stop", "presence_penalty", "frequency_penalty",
            "logit_bias", "user", "seed", "tools", "tool_choice",
            "response_format", "logprobs", "top_logprobs",
        }
        for key, value in kwargs.items():
            if key in allowed_api_params:
                api_kwargs[key] = value

        effective_model = model or self.default_model

        # Route through Ali token pool when applicable
        if self._should_use_ali_pool():
            try:
                return self._make_ali_pool_call(
                    model=effective_model,
                    all_messages=all_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_kwargs=api_kwargs,
                )
            except LLMServiceException:
                raise
            except Exception as exc:
                logger.error(f"LLM request failed (Ali pool): model={effective_model}, error={exc}")
                raise LLMServiceException(
                    internal_message=f"API request failed: {str(exc)}",
                    provider=self.default_model,
                    original_exception=exc,
                ) from exc

        # Non-Ali path: use the single pre-configured client
        try:
            response = self._client.chat.completions.create(
                model=effective_model,
                messages=all_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **api_kwargs,
            )

            choices = response.choices
            if not choices:
                raise LLMServiceException(
                    internal_message="AI returned empty result",
                    provider=self.default_model,
                )

            content = choices[0].message.content or ""
            return content
        except LLMServiceException:
            raise
        except Exception as exc:
            logger.error(f"LLM request failed: model={effective_model}, base_url={self._client.base_url}, error={exc}")
            raise LLMServiceException(
                internal_message=f"API request failed: {str(exc)}",
                provider=self.default_model,
                original_exception=exc,
            ) from exc


def _parse_retry_after(exc: openai.RateLimitError) -> int:
    """Extract Retry-After seconds from a RateLimitError, with sane bounds."""
    try:
        if hasattr(exc, "response") and exc.response is not None:
            header_value = exc.response.headers.get("retry-after") or exc.response.headers.get("Retry-After")
            if header_value:
                return max(1, min(int(header_value), 120))
    except (ValueError, TypeError, AttributeError):
        pass
    return settings.ALI_TOKEN_COOLDOWN_SECONDS


def get_openai_client(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    api_url: Optional[str] = None,
    timeout: int = 300,
    max_retries: int = 2,
) -> OpenAICompatibleClientSync:
    """Return a cached OpenAICompatibleClientSync instance keyed by config."""
    cache_key = (model, api_key, api_url, timeout, max_retries)
    client = _client_cache.get(cache_key)
    if client is not None:
        return client
    with _client_cache_lock:
        client = _client_cache.get(cache_key)
        if client is not None:
            return client
        client = OpenAICompatibleClientSync(
            api_key=api_key,
            api_url=api_url,
            default_model=model,
            timeout=timeout,
            max_retries=max_retries,
        )
        _client_cache[cache_key] = client
        return client
