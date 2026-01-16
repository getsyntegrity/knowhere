import json
import time

import httpx

from shared.core.config import settings
from shared.core.exceptions.domain_exceptions import LLMServiceException, KnowhereException
from shared.services.redis import RedisService, RedisServiceFactory
from loguru import logger


class DeepSeekRedisStreamClient:
    """DeepSeek 客户端，负责管理会话状态并调用外部模型生成完整结果"""
    
    def __init__(self, redis_service: RedisService = None):
        if redis_service is None:
            redis_service = RedisServiceFactory.get_service()
        self.redis_service = redis_service

    async def get_conversation_state(self, conversation_id):
        """从Redis获取指定对话的状态"""
        key = f"deepseek:{conversation_id}"

        # 使用新的Redis服务
        state_raw = await self.redis_service.get(key)
        if state_raw:
            if isinstance(state_raw, str):
                state = json.loads(state_raw)
            else:
                state = state_raw
            return {
                "id": conversation_id,
                # FIX: 假设state['messages']也是json字符串
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

    async def update_conversation_state(self, conversation_state):
        """更新Redis中的对话状态"""
        key = f"deepseek:{conversation_state['id']}"
        # FIX: 将整个状态字典作为JSON字符串存入Redis
        state_json = {
            "messages": conversation_state["messages"],
            "progress": str(conversation_state["progress"]),
            "status": conversation_state["status"],
            "last_updated": str(time.time())
        }
        # 使用新的Redis服务
        await self.redis_service.set(key, state_json, ttl=7200)

    async def chat_completion(
        self,
        messages,
        conversation_id="default",
        model=settings.NORMOL_MODEL or "deepseek-chat",
        temperature=0.1,
        max_tokens=4096,
    ):
        """
        非流式聊天补全
        """
        if max_tokens is None:
            max_tokens = 4096
        
        conversation_state = await self.get_conversation_state(conversation_id)

        # 统一处理消息格式，兼容字符串与列表输入
        if isinstance(messages, list):
            incoming_messages = messages
        else:
            incoming_messages = [{"role": "user", "content": str(messages)}]

        previous_messages = conversation_state.get("messages", []) or []
        all_messages = previous_messages + incoming_messages

        headers = {
            "Authorization": f"Bearer {settings.DS_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": all_messages,
            "stream": False,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        logger.debug(f"request LLM with max_tokens: {max_tokens}")

        try:
            from shared.core.constants import APIConstants
            import time
            logger.info(f"🌐 开始HTTP请求到 {settings.DS_URL} (超时: {APIConstants.DEEPSEEK_TIMEOUT}s)...")
            request_start = time.time()
            async with httpx.AsyncClient(timeout=APIConstants.DEEPSEEK_TIMEOUT) as client:
                response = await client.post(settings.DS_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            choices = data.get("choices", [])
            if not choices:
                raise LLMServiceException(
                    internal_message="AI returned empty result",
                    provider="deepseek"
                )

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
            logger.error(f"API Error Response: {e.response.text}")
            raise LLMServiceException(
                internal_message=f"API request failed: {str(e)}",
                provider="deepseek",
                status_code=e.response.status_code,
                original_exception=e
            )
        except KnowhereException:
            conversation_state["status"] = "failed"
            await self.update_conversation_state(conversation_state)
            raise
        except Exception as e:
            conversation_state["status"] = "failed"
            await self.update_conversation_state(conversation_state)
            raise LLMServiceException(
                internal_message=f"Unexpected error during request: {str(e)}",
                provider="deepseek",
                original_exception=e
            )

    async def reset_conversation(self, conversation_id="default"):
        key = f"deepseek:{conversation_id}"
        await self.redis_service.delete(key) # MODIFIED: 确保使用了正确的 redis_client 实例

    async def get_conversation_progress(self, conversation_id="default"):
        state = await self.get_conversation_state(conversation_id)
        return {
            "id": conversation_id,
            "progress": state["progress"],
            "status": state["status"],
            "last_updated": state["last_updated"]
        }

    # MODIFIED: get_all_conversations 改为 async，因为 keys() 是异步的
    async def get_all_conversations(self):
        """获取所有对话ID列表"""
        # 注意: redis.keys() 是一个阻塞操作，在异步代码中大量使用可能会有性能问题
        # 对于调试和少量键是可行的
        keys = await self.redis_service._get_client().keys("deepseek:*")
        return [key.decode('utf-8').split(":")[1] for key in keys]
