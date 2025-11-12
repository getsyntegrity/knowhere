"""
Redis重试机制工具
"""
import asyncio
import random
from typing import Any, Callable

from loguru import logger

from app.core.exceptions.redis_exceptions import (
    RedisConnectionError,
    RedisOperationError,
    RedisTimeoutError,
)


class RedisRetry:
    """Redis操作重试机制"""
    
    @staticmethod
    async def with_retry(
        operation: Callable,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ) -> Any:
        """
        执行Redis操作并支持重试
        
        Args:
            operation: 要执行的操作函数
            max_retries: 最大重试次数
            base_delay: 基础延迟时间（秒）
            max_delay: 最大延迟时间（秒）
            exponential_base: 指数退避基数
            jitter: 是否添加随机抖动
        
        Returns:
            操作结果
            
        Raises:
            RedisOperationError: 重试次数用尽后仍失败
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return await operation()
            except (RedisConnectionError, RedisOperationError, RedisTimeoutError) as e:
                last_exception = e
                
                if attempt == max_retries:
                    logger.error(f"Redis操作失败，已重试{max_retries}次: {e}")
                    raise RedisOperationError(f"Redis操作失败，已重试{max_retries}次: {e}")
                
                # 计算延迟时间
                delay = min(base_delay * (exponential_base ** attempt), max_delay)
                
                # 添加随机抖动
                if jitter:
                    delay *= (0.5 + random.random() * 0.5)
                
                logger.warning(f"Redis操作失败，{delay:.2f}秒后重试 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                await asyncio.sleep(delay)
        
        # 理论上不会到达这里
        raise RedisOperationError(f"Redis操作失败: {last_exception}")
    
    @staticmethod
    async def with_circuit_breaker(
        operation: Callable,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type = Exception
    ) -> Any:
        """
        带熔断器的Redis操作
        
        Args:
            operation: 要执行的操作函数
            failure_threshold: 失败阈值
            recovery_timeout: 恢复超时时间
            expected_exception: 预期的异常类型
        
        Returns:
            操作结果
        """
        # 这里可以实现熔断器逻辑
        # 为了简化，暂时直接执行操作
        return await operation()


class RedisHealthChecker:
    """Redis健康检查器"""
    
    def __init__(self, redis_client):
        self.redis_client = redis_client
        self._is_healthy = True
        self._last_check = 0
        self._check_interval = 30  # 30秒检查一次
    
    async def is_healthy(self) -> bool:
        """检查Redis是否健康"""
        import time
        current_time = time.time()
        
        # 如果距离上次检查时间不足，直接返回缓存结果
        if current_time - self._last_check < self._check_interval:
            return self._is_healthy
        
        try:
            # 执行PING命令检查连接
            await self.redis_client.ping()
            self._is_healthy = True
            self._last_check = current_time
            return True
        except Exception as e:
            logger.error(f"Redis健康检查失败: {e}")
            self._is_healthy = False
            self._last_check = current_time
            return False
    
    async def wait_for_healthy(self, timeout: float = 30.0) -> bool:
        """等待Redis恢复健康"""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if await self.is_healthy():
                return True
            await asyncio.sleep(1)
        
        return False
