"""
状态超时处理服务 - 基于Redis Keyspace Notifications
"""
import json
from typing import List, Dict, Any, Optional
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.state_machine.states import get_state_timeout, JobStatus
from app.core.state_machine.redis_keyspace_notifications import RedisKeyspaceNotificationHandler
from app.services.redis import RedisServiceFactory


class StateTimeoutService:
    """状态超时处理服务 - 基于Redis Keyspace Notifications"""
    
    def __init__(self, redis_service=None):
        self.redis = redis_service or RedisServiceFactory.get_service()
        self.notification_handler = RedisKeyspaceNotificationHandler(redis_service)
        
        # 设置超时回调
        self.notification_handler.set_timeout_callback(self._handle_timeout_callback)
    
    async def start_listening(self):
        """启动超时监听"""
        await self.notification_handler.start_listening()
    
    async def stop_listening(self):
        """停止超时监听"""
        await self.notification_handler.stop_listening()
    
    async def is_listening(self) -> bool:
        """检查是否正在监听"""
        return await self.notification_handler.is_listening()
    
    async def check_timeout_tasks(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """检查超时任务 - Keyspace Notifications模式下不需要定时检查"""
        # 使用Redis Keyspace Notifications时，超时会自动触发回调
        # 此方法保留用于兼容性，但通常返回空列表
        logger.debug("使用Redis Keyspace Notifications，超时会自动处理")
        return []
    
    async def handle_timeout_tasks(
        self, 
        db: AsyncSession, 
        state_machine_service,
        timeout_tasks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """处理超时任务 - Keyspace Notifications模式下通常不需要此方法"""
        # 在Keyspace Notifications模式下，超时会自动通过回调处理
        # 此方法保留用于兼容性
        return {
            "total_timeout": len(timeout_tasks),
            "handled_success": 0,
            "handled_failed": 0,
            "note": "Keyspace Notifications模式下超时会自动处理"
        }
    
    async def set_task_timeout(self, task_id: str, state: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """设置任务超时"""
        try:
            return await self.notification_handler.set_task_timeout(task_id, state, metadata)
        except Exception as e:
            logger.error(f"设置任务 {task_id} 超时失败: {e}")
            return False
    
    async def extend_task_timeout(self, task_id: str, state: str) -> bool:
        """延长任务超时时间"""
        try:
            # 重新设置超时
            return await self.notification_handler.set_task_timeout(task_id, state)
        except Exception as e:
            logger.error(f"延长任务 {task_id} 超时时间失败: {e}")
            return False
    
    async def clear_task_timeout(self, task_id: str) -> bool:
        """清除任务超时"""
        try:
            return await self.notification_handler.clear_task_timeout(task_id)
        except Exception as e:
            logger.error(f"清除任务 {task_id} 超时失败: {e}")
            return False
    
    async def get_timeout_info(self, task_id: str) -> Dict[str, Any]:
        """获取任务超时信息"""
        try:
            # 通过监控集合检查
            monitoring_key = "job_timeout_monitoring"
            is_monitored = await self.redis.sismember(monitoring_key, task_id)
            
            if is_monitored:
                timeout_data_key = f"job_timeout_data:{task_id}"
                timeout_data_str = await self.redis.get(timeout_data_key)
                if timeout_data_str:
                    timeout_data = json.loads(timeout_data_str)
                    return {
                        "task_id": task_id,
                        "has_timeout": True,
                        "state": timeout_data.get("state"),
                        "created_at": timeout_data.get("created_at"),
                        "metadata": timeout_data.get("metadata", {})
                    }
            
            return {
                "task_id": task_id,
                "has_timeout": False,
                "state": None
            }
            
        except Exception as e:
            logger.error(f"获取任务 {task_id} 超时信息失败: {e}")
            return {
                "task_id": task_id,
                "has_timeout": False,
                "error": str(e)
            }
    
    # 私有方法
    
    async def _handle_timeout_callback(self, timeout_info: Dict[str, Any]):
        """处理超时回调"""
        try:
            job_id = timeout_info["job_id"]
            state = timeout_info["state"]
            
            logger.warning(f"任务 {job_id} 在状态 {state} 超时")
            
            # 这里可以添加具体的超时处理逻辑
            # 例如：发送通知、记录日志、触发重试等
            
        except Exception as e:
            logger.error(f"处理超时回调失败: {e}")