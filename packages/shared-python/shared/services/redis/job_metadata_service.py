"""Redis service for cached job metadata."""
from typing import Any, Dict, Optional

from loguru import logger

from shared.services.redis.redis_service import RedisService
from shared.utils.redis_key_builder import redis_key_builder, RedisKeyType


class JobMetadataService:
    """Redis service for job metadata."""
    
    # Cache TTL aligned with the Job lifecycle TTL.
    METADATA_TTL = redis_key_builder.get_key_ttl(RedisKeyType.TASK)
    
    def __init__(self, redis_service: RedisService):
        self.redis = redis_service
    
    async def save_metadata(self, job_id: str, metadata: Dict[str, Any]) -> bool:
        """Save job_metadata to Redis with the Job-aligned TTL."""
        try:
            key = redis_key_builder.task_metadata(job_id)
            await self.redis.set(key, metadata, ttl=self.METADATA_TTL)
            logger.debug(f"Job metadata已保存到Redis: job_id={job_id}, ttl={self.METADATA_TTL}s")
            return True
        except Exception as e:
            logger.error(f"保存job metadata到Redis失败: {e}")
            return False
    
    async def get_metadata(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load job_metadata from Redis."""
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
        """Update cached job_metadata and refresh its TTL."""
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
        """Delete cached job_metadata."""
        try:
            key = redis_key_builder.task_metadata(job_id)
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.error(f"删除job metadata失败: {e}")
            return False
