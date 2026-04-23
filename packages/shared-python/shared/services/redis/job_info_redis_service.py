"""
Redis service for job summary information.
Maintains shared job-info cache entries for both API and worker services.
"""
from typing import Any, Dict, Optional

from loguru import logger

from shared.services.redis.redis_service import RedisService
from shared.utils.redis_key_builder import redis_key_builder, RedisKeyType


class JobInfoRedisService:
    """Redis service for cached job information."""
    
    # Cache TTL aligned with the Job lifecycle TTL.
    JOB_INFO_TTL = redis_key_builder.get_key_ttl(RedisKeyType.TASK)
    
    def __init__(self, redis_service: RedisService):
        self.redis = redis_service
    
    async def save_job_info(self, job_id: str, job_info: Dict[str, Any]) -> bool:
        """
        Save job information to Redis with the Job-aligned TTL.
        
        Args:
            job_id: Job ID.
            job_info: Job info payload including IDs, ownership, and source data.
        
        Returns:
            Whether the save succeeded.
        """
        try:
            key = redis_key_builder.task_info(job_id)
            await self.redis.set(key, job_info, ttl=self.JOB_INFO_TTL)
            logger.debug(f"Job信息已保存到Redis: job_id={job_id}, ttl={self.JOB_INFO_TTL}s")
            return True
        except Exception as e:
            logger.error(f"保存Job信息到Redis失败: {e}")
            return False
    
    async def get_job_info(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Load job information from Redis.
        
        Args:
            job_id: Job ID.
        
        Returns:
            Job info payload, or None when missing.
        """
        try:
            key = redis_key_builder.task_info(job_id)
            job_info = await self.redis.get(key)
            if job_info:
                logger.debug(f"从Redis获取Job信息: job_id={job_id}")
            return job_info
        except Exception as e:
            logger.error(f"从Redis获取Job信息失败: {e}")
            return None
    
    async def update_job_info(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update cached job information and refresh its TTL.
        
        Args:
            job_id: Job ID.
            updates: Fields to merge into the cached record.
        
        Returns:
            Whether the update succeeded.
        """
        try:
            job_info = await self.get_job_info(job_id)
            if job_info:
                job_info.update(updates)
                return await self.save_job_info(job_id, job_info)
            return False
        except Exception as e:
            logger.error(f"更新Job信息失败: {e}")
            return False
    
    async def delete_job_info(self, job_id: str) -> bool:
        """
        Delete cached job information from Redis.
        
        Args:
            job_id: Job ID.
        
        Returns:
            Whether the delete succeeded.
        """
        try:
            key = redis_key_builder.task_info(job_id)
            await self.redis.delete(key)
            logger.debug(f"Job信息已从Redis删除: job_id={job_id}")
            return True
        except Exception as e:
            logger.error(f"删除Job信息失败: {e}")
            return False
