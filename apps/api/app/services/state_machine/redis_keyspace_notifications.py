"""
Redis Keyspace Notifications 超时处理机制
真正实现基于Redis TTL的实时超时处理
"""
import asyncio
import json
from typing import Any, Callable, Dict, Optional

from app.services.redis import RedisServiceFactory
from loguru import logger


class RedisKeyspaceNotificationHandler:
    """Redis Keyspace Notifications 超时处理机制"""
    
    def __init__(self, redis_service=None):
        self.redis = redis_service or RedisServiceFactory.get_service()
        self._timeout_callback = None
        self._listening = False
        self._pubsub = None
    
    def set_timeout_callback(self, callback: Callable):
        """设置超时回调函数"""
        self._timeout_callback = callback
    
    async def start_listening(self):
        """开始监听Redis Keyspace Notifications"""
        try:
            # 创建pubsub连接
            self._pubsub = self.redis.pubsub()
            
            # 订阅过期事件
            await self._pubsub.psubscribe("__keyevent@*__:expired")
            
            self._listening = True
            logger.info("开始监听Redis Keyspace Notifications")
            
            # 启动监听循环
            await self._listen_for_expired_keys()
            
        except Exception as e:
            logger.error(f"启动Redis Keyspace Notifications监听失败: {e}")
            self._listening = False
    
    async def stop_listening(self):
        """停止监听"""
        try:
            self._listening = False
            if self._pubsub:
                await self._pubsub.close()
            logger.info("停止监听Redis Keyspace Notifications")
        except Exception as e:
            logger.error(f"停止监听失败: {e}")
    
    async def _listen_for_expired_keys(self):
        """监听过期键事件"""
        try:
            while self._listening:
                try:
                    # 等待消息，设置超时避免阻塞
                    message = await asyncio.wait_for(
                        self._pubsub.get_message(timeout=1.0), 
                        timeout=1.0
                    )
                    
                    if message and message['type'] == 'pmessage':
                        await self._handle_expired_key(message)
                        
                except asyncio.TimeoutError:
                    # 超时是正常的，继续循环
                    continue
                except Exception as e:
                    logger.error(f"处理过期键事件失败: {e}")
                    await asyncio.sleep(1)  # 出错时稍作等待
                    
        except Exception as e:
            logger.error(f"监听过期键事件失败: {e}")
        finally:
            self._listening = False
    
    async def _handle_expired_key(self, message: Dict[str, Any]):
        """处理过期键事件"""
        try:
            key = message['data'].decode('utf-8')
            
            # 检查是否是我们的超时键
            if key.startswith('job_timeout:'):
                job_id = key.replace('job_timeout:', '')
                
                # 获取超时数据（可能已经被删除，需要从监控集合获取）
                timeout_data = await self._get_timeout_data_from_monitoring(job_id)
                
                if timeout_data:
                    logger.info(f"检测到任务 {job_id} 超时: {timeout_data['state']}")
                    
                    # 调用超时回调
                    if self._timeout_callback:
                        await self._timeout_callback(timeout_data)
                    
                    # 从监控集合移除
                    await self._remove_from_monitoring(job_id)
                else:
                    logger.warning(f"任务 {job_id} 超时但未找到超时数据")
            
        except Exception as e:
            logger.error(f"处理过期键 {message.get('data', 'unknown')} 失败: {e}")
    
    async def _get_timeout_data_from_monitoring(self, job_id: str) -> Optional[Dict[str, Any]]:
        """从监控集合获取超时数据"""
        try:
            # 尝试从监控集合获取超时数据
            monitoring_key = "job_timeout_monitoring"
            timeout_data_key = f"job_timeout_data:{job_id}"
            
            # 获取超时数据
            timeout_data_str = await self.redis.get(timeout_data_key)
            if timeout_data_str:
                return json.loads(timeout_data_str)
            
            return None
            
        except Exception as e:
            logger.error(f"获取任务 {job_id} 超时数据失败: {e}")
            return None
    
    async def _remove_from_monitoring(self, job_id: str):
        """从监控集合移除"""
        try:
            monitoring_key = "job_timeout_monitoring"
            await self.redis.srem(monitoring_key, job_id)
        except Exception as e:
            logger.error(f"从监控集合移除任务 {job_id} 失败: {e}")
    
    async def set_task_timeout(self, job_id: str, state: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """设置任务超时 - 使用Keyspace Notifications"""
        try:
            from app.core.state_machine.states import get_state_timeout
            
            timeout = get_state_timeout(state)
            if timeout <= 0:
                return True
            
            # 创建超时数据
            timeout_data = {
                "job_id": job_id,
                "state": state,
                "created_at": asyncio.get_event_loop().time(),
                "metadata": metadata or {}
            }
            
            # 设置超时键（用于触发过期事件）
            timeout_key = f"job_timeout:{job_id}"
            await self.redis.set(timeout_key, "1", ex=timeout)
            
            # 保存超时数据（用于回调时获取详细信息）
            timeout_data_key = f"job_timeout_data:{job_id}"
            await self.redis.set(
                timeout_data_key, 
                json.dumps(timeout_data), 
                ex=timeout + 60  # 比超时时间稍长，确保能获取到数据
            )
            
            # 添加到监控集合
            monitoring_key = "job_timeout_monitoring"
            await self.redis.sadd(monitoring_key, job_id)
            
            logger.debug(f"任务 {job_id} 超时设置成功: {state} -> {timeout}秒")
            return True
            
        except Exception as e:
            logger.error(f"设置任务 {job_id} 超时失败: {e}")
            return False
    
    async def clear_task_timeout(self, job_id: str) -> bool:
        """清除任务超时"""
        try:
            # 删除超时键
            timeout_key = f"job_timeout:{job_id}"
            await self.redis.delete(timeout_key)
            
            # 删除超时数据
            timeout_data_key = f"job_timeout_data:{job_id}"
            await self.redis.delete(timeout_data_key)
            
            # 从监控集合移除
            await self._remove_from_monitoring(job_id)
            
            logger.debug(f"任务 {job_id} 超时已清除")
            return True
            
        except Exception as e:
            logger.error(f"清除任务 {job_id} 超时失败: {e}")
            return False
    
    async def is_listening(self) -> bool:
        """检查是否正在监听"""
        return self._listening
