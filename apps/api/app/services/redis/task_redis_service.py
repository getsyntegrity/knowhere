"""
任务相关Redis服务
"""
from typing import Any, Dict, List, Optional

from app.services.redis.redis_service import RedisService
from app.utils.redis_key_builder import RedisKeyType, redis_key_builder
from loguru import logger


class TaskRedisService:
    """任务相关Redis服务"""
    
    def __init__(self, redis_service: RedisService):
        self.redis = redis_service
    
    async def create_task(self, task_id: str, task_data: Dict[str, Any]) -> bool:
        """创建任务记录"""
        try:
            # 保存任务元数据
            metadata_key = redis_key_builder.task_metadata(task_id)
            await self.redis.hset(metadata_key, mapping=task_data)
            await self.redis.expire(metadata_key, redis_key_builder.get_key_ttl(RedisKeyType.TASK))
            
            # 设置初始状态
            await self.set_task_status(task_id, "pending")
            
            # 添加到处理中任务集合
            processing_tasks_key = redis_key_builder.set_processing_tasks()
            await self.redis.sadd(processing_tasks_key, task_id)
            await self.redis.expire(processing_tasks_key, redis_key_builder.get_key_ttl(RedisKeyType.SET))
            
            logger.info(f"任务 {task_id} 创建成功")
            return True
        except Exception as e:
            logger.error(f"创建任务 {task_id} 失败: {e}")
            return False
    
    async def set_task_status(self, task_id: str, status: str) -> bool:
        """设置任务状态"""
        try:
            status_key = redis_key_builder.task_status(task_id)
            await self.redis.set(status_key, status, ttl=redis_key_builder.get_key_ttl(RedisKeyType.TASK))
            
            # 更新任务进度
            progress_key = redis_key_builder.task_progress(task_id)
            progress_data = {
                "status": status,
                "timestamp": self._get_current_timestamp()
            }
            await self.redis.hset(progress_key, mapping=progress_data)
            await self.redis.expire(progress_key, redis_key_builder.get_key_ttl(RedisKeyType.TASK))
            
            logger.debug(f"任务 {task_id} 状态更新为: {status}")
            return True
        except Exception as e:
            logger.error(f"设置任务 {task_id} 状态失败: {e}")
            return False
    
    async def get_task_status(self, task_id: str) -> str:
        """获取任务状态"""
        try:
            status_key = redis_key_builder.task_status(task_id)
            status = await self.redis.get(status_key, "unknown")
            return status
        except Exception as e:
            logger.error(f"获取任务 {task_id} 状态失败: {e}")
            return "unknown"
    
    async def save_task_result(self, task_id: str, result: Dict[str, Any]) -> bool:
        """保存任务结果"""
        try:
            result_key = redis_key_builder.task_result(task_id)
            await self.redis.set(result_key, result, ttl=redis_key_builder.get_key_ttl(RedisKeyType.TASK))
            
            # 更新任务状态为完成
            await self.set_task_status(task_id, "done")
            
            # 从处理中任务集合移除
            processing_tasks_key = redis_key_builder.set_processing_tasks()
            await self.redis.srem(processing_tasks_key, task_id)
            
            logger.info(f"任务 {task_id} 结果保存成功")
            return True
        except Exception as e:
            logger.error(f"保存任务 {task_id} 结果失败: {e}")
            return False
    
    async def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务结果"""
        try:
            result_key = redis_key_builder.task_result(task_id)
            result = await self.redis.get(result_key)
            return result
        except Exception as e:
            logger.error(f"获取任务 {task_id} 结果失败: {e}")
            return None
    
    async def update_task_progress(self, task_id: str, progress: int, message: str = "") -> bool:
        """更新任务进度"""
        try:
            progress_key = redis_key_builder.task_progress(task_id)
            progress_data = {
                "progress": progress,
                "message": message,
                "timestamp": self._get_current_timestamp()
            }
            await self.redis.hset(progress_key, mapping=progress_data)
            await self.redis.expire(progress_key, redis_key_builder.get_key_ttl(RedisKeyType.TASK))
            return True
        except Exception as e:
            logger.error(f"更新任务 {task_id} 进度失败: {e}")
            return False
    
    async def get_task_progress(self, task_id: str) -> Dict[str, Any]:
        """获取任务进度"""
        try:
            progress_key = redis_key_builder.task_progress(task_id)
            progress = await self.redis.hgetall(progress_key)
            return progress
        except Exception as e:
            logger.error(f"获取任务 {task_id} 进度失败: {e}")
            return {}
    
    async def mark_task_failed(self, task_id: str, error_message: str) -> bool:
        """标记任务失败"""
        try:
            # 更新状态
            await self.set_task_status(task_id, f"failed: {error_message}")
            
            # 从处理中任务集合移除
            processing_tasks_key = redis_key_builder.set_processing_tasks()
            await self.redis.srem(processing_tasks_key, task_id)
            
            # 记录错误日志
            error_logs_key = redis_key_builder.list_error_logs()
            error_data = {
                "task_id": task_id,
                "error": error_message,
                "timestamp": self._get_current_timestamp()
            }
            await self.redis.rpush(error_logs_key, error_data)
            await self.redis.expire(error_logs_key, redis_key_builder.get_key_ttl(RedisKeyType.LIST))
            
            logger.error(f"任务 {task_id} 标记为失败: {error_message}")
            return True
        except Exception as e:
            logger.error(f"标记任务 {task_id} 失败时出错: {e}")
            return False
    
    async def get_processing_tasks(self) -> List[str]:
        """获取处理中的任务列表"""
        try:
            processing_tasks_key = redis_key_builder.set_processing_tasks()
            tasks = await self.redis.smembers(processing_tasks_key)
            return list(tasks)
        except Exception as e:
            logger.error(f"获取处理中任务列表失败: {e}")
            return []
    
    async def cleanup_task(self, task_id: str) -> bool:
        """清理任务相关数据"""
        try:
            # 删除所有相关键
            keys_to_delete = [
                redis_key_builder.task_status(task_id),
                redis_key_builder.task_result(task_id),
                redis_key_builder.task_metadata(task_id),
                redis_key_builder.task_progress(task_id)
            ]
            
            await self.redis.delete(*keys_to_delete)
            
            # 从处理中任务集合移除
            processing_tasks_key = redis_key_builder.set_processing_tasks()
            await self.redis.srem(processing_tasks_key, task_id)
            
            logger.info(f"任务 {task_id} 数据清理完成")
            return True
        except Exception as e:
            logger.error(f"清理任务 {task_id} 数据失败: {e}")
            return False
    
    def _get_current_timestamp(self) -> str:
        """获取当前时间戳"""
        import time
        return str(int(time.time()))
