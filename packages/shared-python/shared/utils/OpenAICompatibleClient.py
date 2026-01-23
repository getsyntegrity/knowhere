"""
OpenAI-compatible universal AI client
Supports any model that follows the OpenAI API specification (DeepSeek, Qwen, GLM, etc.)
"""
import json
import os
import time
from typing import Optional, List, Dict, Any, Union

import httpx
from loguru import logger

from shared.core.config import settings
from shared.core.exceptions.domain_exceptions import (
    LLMServiceException,
    UnknownException,
)

# Local debug mode: do not use Redis
LOCAL_DEBUG = os.getenv("LOCAL_DEBUG", "0") == "1"


class OpenAICompatibleClient:
    """
    OpenAI-compatible universal client
    Supports DeepSeek, Qwen, GLM and all models that follow the OpenAI API specification
    """
    
    def __init__(
        self, 
        redis_service = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: int = 300,
        skip_redis: bool = False
    ):
        """
        Initialize the client
        
        Args:
            redis_service: Redis service instance for session management (optional)
            api_key: API key, if not provided will auto-route based on model name
            api_url: API URL, if not provided will auto-route based on model name
            default_model: Default model name, defaults to settings.NORMOL_MODEL
            timeout: Request timeout in seconds
            skip_redis: Whether to skip Redis (local debug mode)
        """
        # Local debug mode or explicit skip: do not use Redis
        if LOCAL_DEBUG or skip_redis or redis_service is None:
            self.redis_service = None
        else:
            from shared.services.redis import RedisServiceFactory
            self.redis_service = redis_service or RedisServiceFactory.get_service()
        
        # Get model name for routing
        self.default_model = default_model or getattr(settings, 'NORMOL_MODEL', 'deepseek-chat')
        
        # Auto-route API based on model name (if api_key/api_url not explicitly provided)
        resolved_key, resolved_url = self._resolve_api_config(
            model_name=self.default_model,
            api_key=api_key,
            api_url=api_url
        )
        
        self.api_key = resolved_key
        self.api_url = resolved_url
        self.timeout = timeout
        
        logger.debug(f"Initializing OpenAI-compatible client: URL={self.api_url}, Model={self.default_model}, Redis={'enabled' if self.redis_service else 'disabled'}")
    
    def _resolve_api_config(self, model_name: str, api_key: Optional[str], api_url: Optional[str]) -> tuple:
        """
        Resolve API key and URL based on model name
        
        Routing rules:
        - qwen* / qwen3-max / qwen-* → ALI_API_KEY + ALI_URL
        - doubao* / ep-* → ARK_API_KEY + ARK_URL  
        - deepseek* / default → DS_KEY + DS_URL
        
        Returns:
            tuple: (api_key, api_url)
        """
        # If both explicitly provided, use them directly
        if api_key and api_url:
            return api_key, api_url
        
        model_lower = (model_name or '').lower()
        
        # Qwen models → Aliyun DashScope
        if 'qwen' in model_lower:
            resolved_key = api_key or getattr(settings, 'ALI_API_KEY', None)
            ali_base = getattr(settings, 'ALI_URL', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
            # Ensure URL has /chat/completions suffix
            if ali_base and not ali_base.endswith('/chat/completions'):
                resolved_url = api_url or f"{ali_base}/chat/completions"
            else:
                resolved_url = api_url or ali_base
            logger.debug(f"Model '{model_name}' routed to Aliyun DashScope")
            return resolved_key, resolved_url
        
        # Doubao/Ark models → Volcano Engine
        if 'doubao' in model_lower or model_lower.startswith('ep-'):
            resolved_key = api_key or getattr(settings, 'ARK_API_KEY', None)
            resolved_url = api_url or getattr(settings, 'ARK_URL', None)
            logger.debug(f"Model '{model_name}' routed to Volcano Ark")
            return resolved_key, resolved_url
        
        # Default: DeepSeek
        resolved_key = api_key or settings.DS_KEY
        resolved_url = api_url or settings.DS_URL
        logger.debug(f"Model '{model_name}' routed to DeepSeek (default)")
        return resolved_key, resolved_url

    async def get_conversation_state(self, conversation_id: str) -> Dict[str, Any]:
        """Get the state of a specific conversation from Redis"""
        # No Redis mode: return empty state
        if self.redis_service is None:
            return {
                "id": conversation_id,
                "messages": [],
                "progress": 0,
                "status": "pending",
                "last_updated": time.time()
            }
        
        key = f"ai_conversation:{conversation_id}"

        state_raw = await self.redis_service.get(key)
        if state_raw:
            if isinstance(state_raw, str):
                state = json.loads(state_raw)
            else:
                state = state_raw
            return {
                "id": conversation_id,
                "messages": json.loads(state.get("messages", "[]")) if isinstance(state.get("messages"), str) else state.get("messages", []),
                "progress": int(state.get("progress", 0)),
                "status": state.get("status", "pending"),
                "last_updated": float(state.get("last_updated", time.time()))
            }
        return {
            "id": conversation_id,
            "messages": [],
            "progress": 0,
            "status": "pending",
            "last_updated": time.time()
        }

    async def update_conversation_state(self, conversation_state: Dict[str, Any]):
        """Update conversation state in Redis"""
        # No Redis mode: skip
        if self.redis_service is None:
            return
            
        key = f"ai_conversation:{conversation_state['id']}"
        state_json = {
            "messages": conversation_state["messages"],
            "progress": str(conversation_state["progress"]),
            "status": conversation_state["status"],
            "last_updated": str(time.time())
        }
        await self.redis_service.set(key, state_json, ttl=7200)

    async def chat_completion(
        self,
        messages: Union[str, List[Dict[str, str]]],
        conversation_id: str = "default",
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        top_p: Optional[float] = None,
        stream: bool = False,
        **kwargs
    ) -> str:
        """
        Non-streaming chat completion (OpenAI format compatible)
        
        Args:
            messages: Message content, can be a string or message list
            conversation_id: Conversation ID for saving session history
            model: Model name, uses default model if not specified
            temperature: Temperature parameter
            max_tokens: Maximum number of tokens to generate
            top_p: Nucleus sampling parameter
            stream: Whether to stream output (currently only non-streaming is supported)
            **kwargs: Other parameters
        
        Returns:
            str: Model-generated response content
        """
        conversation_state = await self.get_conversation_state(conversation_id)

        # Unified message format handling, compatible with string and list inputs
        if isinstance(messages, list):
            incoming_messages = messages
        else:
            incoming_messages = [{"role": "user", "content": str(messages)}]

        # No Redis mode: do not use history messages
        if self.redis_service is None:
            all_messages = incoming_messages
        else:
            previous_messages = conversation_state.get("messages", []) or []
            all_messages = previous_messages + incoming_messages

        # Build request headers
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Build request body
        payload = {
            "model": model or self.default_model,
            "messages": all_messages,
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # Add optional parameters
        if top_p is not None:
            payload["top_p"] = top_p
        
        allowed_api_params = {
            'n', 'stop', 'presence_penalty', 'frequency_penalty', 
            'logit_bias', 'user', 'seed', 'tools', 'tool_choice',
            'response_format', 'logprobs', 'top_logprobs'
        }
        
        # Filter and add extra API parameters
        for key, value in kwargs.items():
            if key in allowed_api_params:
                payload[key] = value

        try:
            logger.info(f"🌐 Starting HTTP request to {self.api_url} (model: {payload['model']}, timeout: {self.timeout}s)...")
            request_start = time.time()
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.api_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            request_duration = time.time() - request_start
            logger.info(f"✅ AI request completed, duration: {request_duration:.2f}s")

            choices = data.get("choices", [])
            if not choices:
                raise LLMServiceException(
                    internal_message="AI returned empty result",
                    provider=self.default_model,
                )

            message = choices[0].get("message", {})
            content = message.get("content", "")
            if content is None:
                content = ""

            # Update session state (only when Redis is available)
            if self.redis_service is not None:
                if message:
                    assistant_message = {"role": message.get("role", "assistant"), "content": content}
                else:
                    assistant_message = {"role": "assistant", "content": content}

                conversation_state["messages"] = all_messages + [assistant_message]
                conversation_state["progress"] = len(content)
                conversation_state["status"] = "completed"
                await self.update_conversation_state(conversation_state)

            return content

        except httpx.HTTPStatusError as e:
            if self.redis_service is not None:
                conversation_state["status"] = "failed"
                await self.update_conversation_state(conversation_state)
            logger.error(f"❌ API request failed: {str(e)}, Response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
            raise LLMServiceException(
                internal_message=f"API request failed: {str(e)}",
                provider=self.default_model,
                status_code=e.response.status_code if hasattr(e, 'response') else None,
                original_exception=e,
            ) from e
        except httpx.TimeoutException as e:
            if self.redis_service is not None:
                conversation_state["status"] = "failed"
                await self.update_conversation_state(conversation_state)
            logger.error(f"⏱️ API request timeout: {str(e)}")
            raise LLMServiceException(
                internal_message=f"API request timeout: {str(e)}",
                provider=self.default_model,
                original_exception=e,
            ) from e
        except LLMServiceException:
            # Re-raise LLMServiceException without wrapping
            raise
        except Exception as e:
            if self.redis_service is not None:
                conversation_state["status"] = "failed"
                await self.update_conversation_state(conversation_state)
            logger.error(f"❌ Unknown error during request processing: {str(e)}")
            raise UnknownException(original_exception=e) from e

    async def reset_conversation(self, conversation_id: str = "default"):
        """重置对话历史"""
        if self.redis_service is None:
            return
        key = f"ai_conversation:{conversation_id}"
        await self.redis_service.delete(key)

    async def get_conversation_progress(self, conversation_id: str = "default") -> Dict[str, Any]:
        """获取对话进度"""
        state = await self.get_conversation_state(conversation_id)
        return {
            "id": conversation_id,
            "progress": state["progress"],
            "status": state["status"],
            "last_updated": state["last_updated"]
        }

    async def get_all_conversations(self) -> List[str]:
        """获取所有对话ID列表"""
        if self.redis_service is None:
            return []
        keys = await self.redis_service._get_client().keys("ai_conversation:*")
        return [key.decode('utf-8').split(":", 1)[1] for key in keys]


# 向后兼容：DeepSeekRedisStreamClient别名
class DeepSeekRedisStreamClient(OpenAICompatibleClient):
    """向后兼容的DeepSeek客户端（实际使用OpenAI兼容客户端）"""
    pass
