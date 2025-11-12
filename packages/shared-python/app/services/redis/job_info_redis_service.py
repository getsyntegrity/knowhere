"""
Job基本信息Redis服务
统一管理Job基本信息的Redis缓存，供API和Worker服务使用
"""
from typing import Dict, Any, Optional
from loguru import logger

from app.services.redis.redis_service import RedisService
from app.utils.redis_key_builder import redis_key_builder


class JobInfoRedisService:
    """Job基本信息Redis服务"""
    
    # 缓存过期时间：2小时（与job_metadata一致）
    JOB_INFO_TTL = 7200
    
    def __init__(self, redis_service: RedisService):
        self.redis = redis_service
    
    async def save_job_info(self, job_id: str, job_info: Dict[str, Any]) -> bool:
        """
        保存Job基本信息到Redis（2小时过期）
        
        Args:
            job_id: 任务ID
            job_info: Job基本信息字典，包含：
                - job_id: 任务ID
                - s3_key: S3键
                - user_id: 用户ID
                - webhook_enabled: 是否启用Webhook
                - job_type: 任务类型
                - source_type: 来源类型
                - created_at: 创建时间（ISO格式字符串）
        
        Returns:
            是否保存成功
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
        从Redis获取Job基本信息
        
        Args:
            job_id: 任务ID
        
        Returns:
            Job基本信息字典，如果不存在则返回None
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
        更新Redis中的Job基本信息（刷新过期时间）
        
        Args:
            job_id: 任务ID
            updates: 要更新的字段字典
        
        Returns:
            是否更新成功
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
        删除Redis中的Job基本信息
        
        Args:
            job_id: 任务ID
        
        Returns:
            是否删除成功
        """
        try:
            key = redis_key_builder.task_info(job_id)
            await self.redis.delete(key)
            logger.debug(f"Job信息已从Redis删除: job_id={job_id}")
            return True
        except Exception as e:
            logger.error(f"删除Job信息失败: {e}")
            return False

