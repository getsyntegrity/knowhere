"""
速率限制服务
"""
import os
import time
from typing import Dict, Any
from loguru import logger

from app.services.redis.redis_service import RedisService
from app.utils.redis_key_builder import redis_key_builder


class RateLimitService:
    """速率限制服务"""
    
    # 默认值，可通过环境变量覆盖
    RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # 60秒窗口
    RATE_LIMIT_MAX_REQUESTS = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "1000"))  # 最大请求数
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"  # 是否启用
    
    def __init__(self, redis_service: RedisService):
        self.redis = redis_service
        logger.info(
            f"速率限制服务初始化: "
            f"启用={self.RATE_LIMIT_ENABLED}, "
            f"窗口={self.RATE_LIMIT_WINDOW}秒, "
            f"最大请求数={self.RATE_LIMIT_MAX_REQUESTS}"
        )
    
    async def check_rate_limit(self, user_id: str, api_name: str) -> Dict[str, Any]:
        """
        检查并更新速率限制
        
        Args:
            user_id: 用户ID
            api_name: API名称
            
        Returns:
            {
                "allowed": bool,  # 是否允许请求
                "limit": int,  # 限制数量
                "remaining": int,  # 剩余次数
                "reset": int,  # 重置时间戳
            }
        """
        # 如果速率限制未启用，直接允许所有请求
        if not self.RATE_LIMIT_ENABLED:
            return {
                "allowed": True,
                "limit": self.RATE_LIMIT_MAX_REQUESTS,
                "remaining": self.RATE_LIMIT_MAX_REQUESTS,
                "reset": int(time.time()) + self.RATE_LIMIT_WINDOW,
            }
        
        try:
            # 构建速率限制键
            rate_limit_key = redis_key_builder.rate_limit_api(user_id, api_name)
            
            # 使用管道确保原子性操作
            client = await self.redis._get_client()
            async with client.pipeline() as pipe:
                # 增加计数
                await pipe.incr(rate_limit_key)
                
                # 如果是第一次（计数=1），设置TTL
                await pipe.expire(rate_limit_key, self.RATE_LIMIT_WINDOW)
                
                # 获取当前计数和TTL
                await pipe.get(rate_limit_key)
                await pipe.ttl(rate_limit_key)
                
                # 执行管道操作
                results = await pipe.execute()
            
            current_count = int(results[0])  # INCR结果
            ttl_seconds = int(results[2])    # TTL结果
            
            # 计算剩余次数
            remaining = max(0, self.RATE_LIMIT_MAX_REQUESTS - current_count)
            
            # 计算重置时间戳
            reset_timestamp = int(time.time()) + ttl_seconds
            
            # 判断是否允许请求
            allowed = current_count <= self.RATE_LIMIT_MAX_REQUESTS
            
            rate_limit_info = {
                "allowed": allowed,
                "limit": self.RATE_LIMIT_MAX_REQUESTS,
                "remaining": remaining,
                "reset": reset_timestamp,
            }
            
            logger.debug(f"速率限制检查: user_id={user_id}, api={api_name}, count={current_count}, remaining={remaining}")
            
            return rate_limit_info
            
        except Exception as e:
            logger.error(f"速率限制检查失败: {e}")
            # 发生错误时，允许请求通过，但记录错误
            return {
                "allowed": True,
                "limit": self.RATE_LIMIT_MAX_REQUESTS,
                "remaining": self.RATE_LIMIT_MAX_REQUESTS,
                "reset": int(time.time()) + self.RATE_LIMIT_WINDOW,
            }
    
    async def get_rate_limit_info(self, user_id: str, api_name: str) -> Dict[str, Any]:
        """
        获取当前速率限制信息（不增加计数）
        
        Args:
            user_id: 用户ID
            api_name: API名称
            
        Returns:
            速率限制信息
        """
        try:
            rate_limit_key = redis_key_builder.rate_limit_api(user_id, api_name)
            
            # 获取当前计数和TTL
            current_count = await self.redis.get(rate_limit_key, 0)
            client = await self.redis._get_client()
            ttl_seconds = await client.ttl(rate_limit_key)
            
            if ttl_seconds == -1:
                # 键存在但没有TTL，设置默认TTL
                await self.redis.expire(rate_limit_key, self.RATE_LIMIT_WINDOW)
                ttl_seconds = self.RATE_LIMIT_WINDOW
            elif ttl_seconds == -2:
                # 键不存在
                current_count = 0
                ttl_seconds = self.RATE_LIMIT_WINDOW
            
            current_count = int(current_count)
            remaining = max(0, self.RATE_LIMIT_MAX_REQUESTS - current_count)
            reset_timestamp = int(time.time()) + ttl_seconds
            
            return {
                "allowed": current_count < self.RATE_LIMIT_MAX_REQUESTS,
                "limit": self.RATE_LIMIT_MAX_REQUESTS,
                "remaining": remaining,
                "reset": reset_timestamp,
            }
            
        except Exception as e:
            logger.error(f"获取速率限制信息失败: {e}")
            return {
                "allowed": True,
                "limit": self.RATE_LIMIT_MAX_REQUESTS,
                "remaining": self.RATE_LIMIT_MAX_REQUESTS,
                "reset": int(time.time()) + self.RATE_LIMIT_WINDOW,
            }
