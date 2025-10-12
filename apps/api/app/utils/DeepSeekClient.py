import json
import time
import httpx
from app.core.dependencies import get_redis_service
from app.services.redis import RedisService
from app.core.config import settings


class DeepSeekRedisStreamClient:
    """
    使用此方式时务必注意，当前方法是httpx,不是https，原因是因为redis是一个很单纯的内存工具，他跟异步是完美契合的，
    我们的工作多半都是在内存中完成的，所以尽量贴合redis的内容去写
    """
    
    def __init__(self, redis_service: RedisService = None):
        self.redis_service = redis_service or get_redis_service()

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
            stream_key: str = None
    ):
        """
        流式聊天补全
        """
        # MODIFIED: 增加了对 stream_key 的检查，确保它被传入
        if not stream_key:
            raise ValueError("A 'stream_key' 流必须存到Redis.")

        # --- 获取和检查对话状态  ---
        conversation_state = await self.get_conversation_state(conversation_id)

        if conversation_state["status"] == "completed":
            if conversation_state["messages"]:
                last_msg = conversation_state["messages"][-1]
                if last_msg["role"] == "assistant":
                    content = last_msg["content"]
                    # MODIFIED: 将完整内容推送到 stream_key，让调用者消费
                    await self.redis_service.rpush(stream_key, content)
                    return content
        # ---  准备请求 ---
        headers = {
            "Authorization": f"Bearer {settings.DS_KEY}",
            "Content-Type": "application/json"
        }
        # MODIFIED: 修正了历史消息的组合方式
        all_messages = conversation_state.get("messages", []) + messages
        payload = {
            "model": model,
            "messages": all_messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # --- 步骤 3: 发送请求并处理流  ---
        try:
            from app.core.constants import APIConstants
            async with httpx.AsyncClient(timeout=APIConstants.DEEPSEEK_TIMEOUT) as client:
                async with client.stream("POST", settings.DS_URL, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    conversation_state["status"] = "progressing"
                    await self.update_conversation_state(conversation_state)

                    full_response = ""
                    buffer = ""
                    # char_count 和 chunk_count 不再需要通过回调传递，变为局部变量
                    char_count = 0
                    chunk_count = 0

                    async for line in response.aiter_lines():
                        if line and line.startswith('data: '):
                            event_data = line[6:]
                            if event_data == "[DONE]":
                                break

                            try:
                                data = json.loads(event_data)
                                if "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        content_chunk = delta["content"]
                                        full_response += content_chunk
                                        buffer += content_chunk
                                        # MODIFIED: 直接将数据块推送到Redis
                                        await self.redis_service.rpush(stream_key, content_chunk)

                                        # chunk_count 逻辑保持，用于定期保存状态
                                        chunk_count += 1
                                        if chunk_count % 20 == 0:
                                            # 更新消息列表时，只更新最后一条助手的消息，而不是追加
                                            if any(msg['role'] == 'assistant' for msg in
                                                   conversation_state["messages"]):
                                                conversation_state["messages"][-1]['content'] = full_response
                                            else:
                                                conversation_state["messages"].append(
                                                    {"role": "assistant", "content": full_response})

                                            conversation_state["progress"] = len(full_response)
                                            await self.update_conversation_state(conversation_state)
                            except json.JSONDecodeError:
                                continue

                    # --- 循环结束后的收尾逻辑 ---
                    # MODIFIED: 移除了对 callback 的调用
                    # if buffer and callback:
                    #     await callback(buffer, char_count, len(full_response))

                    # 更新最终状态
                    if any(msg['role'] == 'assistant' for msg in conversation_state["messages"]):
                        conversation_state["messages"][-1]['content'] = full_response
                    else:
                        conversation_state["messages"].append({"role": "assistant", "content": full_response})

                    conversation_state["progress"] = len(full_response)
                    conversation_state["status"] = "completed"
                    await self.update_conversation_state(conversation_state)

                    # 在所有操作完成后，返回最终结果
                    return full_response
                    # --- 内联逻辑结束 ---

        except httpx.HTTPStatusError as e:
            conversation_state["status"] = "failed"
            await self.update_conversation_state(conversation_state)
            raise Exception(f"API请求失败: {str(e)}") from e
        except Exception as e:
            # 捕获其他可能的异常
            conversation_state["status"] = "failed"
            await self.update_conversation_state(conversation_state)
            raise Exception(f"处理流时发生未知错误: {str(e)}") from e

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