"""
Job元数据Redis服务
"""
from typing import Any, Dict, Optional

from loguru import logger

from shared.services.redis.redis_service import RedisService
from shared.utils.redis_key_builder import redis_key_builder


class JobMetadataService:
    """Job元数据Redis服务"""
    
    # 缓存过期时间：2小时
    METADATA_TTL = 7200
    
    def __init__(self, redis_service: RedisService):
        self.redis = redis_service
    
    async def save_metadata(self, job_id: str, metadata: Dict[str, Any]) -> bool:
        """保存job_metadata到Redis（2小时过期）"""
        try:
            key = redis_key_builder.task_metadata(job_id)
            await self.redis.set(key, metadata, ttl=self.METADATA_TTL)
            logger.debug(f"Job metadata已保存到Redis: job_id={job_id}, ttl={self.METADATA_TTL}s")
            return True
        except Exception as e:
            logger.error(f"保存job metadata到Redis失败: {e}")
            return False
    
    async def get_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        """从Redis获取job_metadata"""
        try:
            key = redis_key_builder.task_metadata(job_id)
            metadata = await self.redis.get(key)
            if metadata:
                logger.debug(f"从Redis获取job metadata: job_id={job_id}")
            return metadata
        except Exception as e:
            logger.error(f"从Redis获取job metadata失败: {e}")
            return None
    
    async def update_metadata(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """更新Redis中的job_metadata（刷新过期时间）"""
        try:
            metadata = await self.get_metadata(job_id)
            if metadata:
                metadata.update(updates)
                return await self.save_metadata(job_id, metadata)
            return False
        except Exception as e:
            logger.error(f"更新job metadata失败: {e}")
            return False
    
    async def delete_metadata(self, job_id: str) -> bool:
        """删除Redis中的job_metadata"""
        try:
            key = redis_key_builder.task_metadata(job_id)
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"删除job metadata失败: {e}")
            return False
