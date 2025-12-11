"""
OpenAI兼容的通用AI客户端
支持任何符合OpenAI API规范的模型（DeepSeek、Qwen、GLM等）
"""
import json
import time
from typing import Optional, List, Dict, Any, Union

import httpx
from loguru import logger

from shared.core.config import settings
from shared.services.redis import RedisService, RedisServiceFactory


class OpenAICompatibleClient:
    """
    OpenAI兼容的通用客户端
    支持DeepSeek、Qwen、GLM等所有符合OpenAI API规范的模型
    """
    
    def __init__(
        self, 
        redis_service: Optional[RedisService] = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: int = 300
    ):
        """
        初始化客户端
        
        Args:
            redis_service: Redis服务实例，用于会话管理
            api_key: API密钥，默认使用settings.DS_KEY
            api_url: API URL，默认使用settings.DS_URL
            default_model: 默认模型名称，默认使用settings.NORMOL_MODEL
            timeout: 请求超时时间（秒）
        """
        if redis_service is None:
            redis_service = RedisServiceFactory.get_service()
        self.redis_service = redis_service
        
        # 支持自定义配置，如果没有则使用默认配置
        self.api_key = api_key or settings.DS_KEY
        self.api_url = api_url or settings.DS_URL
        self.default_model = default_model or getattr(settings, 'NORMOL_MODEL', 'deepseek-chat')
        self.timeout = timeout
        
        logger.debug(f"初始化OpenAI兼容客户端: URL={self.api_url}, Model={self.default_model}")

    async def get_conversation_state(self, conversation_id: str) -> Dict[str, Any]:
        """从Redis获取指定对话的状态"""
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
        """更新Redis中的对话状态"""
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
        非流式聊天补全（兼容OpenAI格式）
        
        Args:
            messages: 消息内容，可以是字符串或消息列表
            conversation_id: 对话ID，用于保存会话历史
            model: 模型名称，如果不指定则使用默认模型
            temperature: 温度参数
            max_tokens: 最大生成token数
            top_p: nucleus sampling参数
            stream: 是否流式输出（当前仅支持非流式）
            **kwargs: 其他参数
        
        Returns:
            str: 模型生成的响应内容
        """
        conversation_state = await self.get_conversation_state(conversation_id)

        # 统一处理消息格式，兼容字符串与列表输入
        if isinstance(messages, list):
            incoming_messages = messages
        else:
            incoming_messages = [{"role": "user", "content": str(messages)}]

        previous_messages = conversation_state.get("messages", []) or []
        all_messages = previous_messages + incoming_messages

        # 构建请求头
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 构建请求体
        payload = {
            "model": model or self.default_model,
            "messages": all_messages,
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        # 添加可选参数
        if top_p is not None:
            payload["top_p"] = top_p
        
        # 只添加 OpenAI API 支持的参数，过滤掉客户端配置参数
        # OpenAI API 标准参数白名单
        allowed_api_params = {
            'n', 'stop', 'presence_penalty', 'frequency_penalty', 
            'logit_bias', 'user', 'seed', 'tools', 'tool_choice',
            'response_format', 'logprobs', 'top_logprobs'
        }
        
        # 过滤并添加额外的 API 参数
        for key, value in kwargs.items():
            if key in allowed_api_params:
                payload[key] = value

        try:
            logger.info(f"🌐 开始HTTP请求到 {self.api_url} (模型: {payload['model']}, 超时: {self.timeout}s)...")
            request_start = time.time()
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.api_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            request_duration = time.time() - request_start
            logger.info(f"✅ AI请求完成，耗时: {request_duration:.2f}s")

            choices = data.get("choices", [])
            if not choices:
                raise Exception("AI返回结果为空")

            message = choices[0].get("message", {})
            content = message.get("content", "")
            if content is None:
                content = ""

            # 更新会话状态
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
            conversation_state["status"] = "failed"
            await self.update_conversation_state(conversation_state)
            logger.error(f"❌ API请求失败: {str(e)}, Response: {e.response.text if hasattr(e, 'response') else 'N/A'}")
            raise Exception(f"API请求失败: {str(e)}") from e
        except httpx.TimeoutException as e:
            conversation_state["status"] = "failed"
            await self.update_conversation_state(conversation_state)
            logger.error(f"⏱️ API请求超时: {str(e)}")
            raise Exception(f"API请求超时: {str(e)}") from e
        except Exception as e:
            conversation_state["status"] = "failed"
            await self.update_conversation_state(conversation_state)
            logger.error(f"❌ 处理请求时发生未知错误: {str(e)}")
            raise Exception(f"处理请求时发生未知错误: {str(e)}") from e

    async def reset_conversation(self, conversation_id: str = "default"):
        """重置对话历史"""
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
        keys = await self.redis_service._get_client().keys("ai_conversation:*")
        return [key.decode('utf-8').split(":", 1)[1] for key in keys]


# 向后兼容：DeepSeekRedisStreamClient别名
class DeepSeekRedisStreamClient(OpenAICompatibleClient):
    """向后兼容的DeepSeek客户端（实际使用OpenAI兼容客户端）"""
    pass
