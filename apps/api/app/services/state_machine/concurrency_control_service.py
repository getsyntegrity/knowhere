"""
并发控制服务 - 处理状态更新的竞争条件
"""
import asyncio
import random
import time
from typing import Any, Dict, Optional

from app.services.redis import RedisServiceFactory
from loguru import logger


class ConcurrencyControlService:
    """并发控制服务 - 处理状态更新的竞争条件"""
    
    def __init__(self, redis_service=None):
        self.redis = redis_service or RedisServiceFactory.get_service()
        self._lock_timeout = 30  # 分布式锁超时时间（秒）
        self._max_retries = 3  # 最大重试次数
        self._base_retry_delay = 0.1  # 基础重试延迟（秒）
    
    async def acquire_job_lock(self, job_id: str, timeout: Optional[int] = None) -> bool:
        """获取任务锁"""
        lock_key = f"job_state_lock:{job_id}"
        lock_timeout = timeout or self._lock_timeout
        
        try:
            # 使用Redis SET NX EX 实现分布式锁
            lock_value = f"{int(time.time())}:{random.randint(1000, 9999)}"
            result = await self.redis.set(
                lock_key, 
                lock_value, 
                nx=True, 
                ex=lock_timeout
            )
            
            if result:
                logger.debug(f"任务 {job_id} 锁获取成功")
                return True
            else:
                logger.debug(f"任务 {job_id} 锁获取失败，可能被其他进程持有")
                return False
                
        except Exception as e:
            logger.error(f"获取任务 {job_id} 锁失败: {e}")
            return False
    
    async def release_job_lock(self, job_id: str) -> bool:
        """释放任务锁"""
        lock_key = f"job_state_lock:{job_id}"
        
        try:
            await self.redis.delete(lock_key)
            logger.debug(f"任务 {job_id} 锁释放成功")
            return True
            
        except Exception as e:
            logger.error(f"释放任务 {job_id} 锁失败: {e}")
            return False
    
    async def with_job_lock(self, job_id: str, operation, *args, **kwargs):
        """在锁保护下执行操作"""
        lock_acquired = False
        
        try:
            # 获取锁
            lock_acquired = await self.acquire_job_lock(job_id)
            if not lock_acquired:
                raise Exception(f"无法获取任务 {job_id} 的锁")
            
            # 执行操作
            result = await operation(*args, **kwargs)
            return result
            
        except Exception as e:
            logger.error(f"在锁保护下执行操作失败: {e}")
            raise
        finally:
            # 释放锁
            if lock_acquired:
                await self.release_job_lock(job_id)
    
    async def retry_with_backoff(self, operation, *args, max_retries: Optional[int] = None, **kwargs):
        """指数退避重试"""
        max_retries = max_retries or self._max_retries
        
        for attempt in range(max_retries + 1):
            try:
                result = await operation(*args, **kwargs)
                return result
                
            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"操作重试 {max_retries} 次后仍然失败: {e}")
                    raise
                
                # 计算退避延迟
                delay = self._base_retry_delay * (2 ** attempt) + random.uniform(0, 0.1)
                logger.warning(f"操作失败，{delay:.2f}秒后重试 (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                
                await asyncio.sleep(delay)
        
        raise Exception("重试次数已用完")
    
    async def optimistic_update_with_retry(
        self, 
        job_id: str, 
        update_operation, 
        *args, 
        max_retries: Optional[int] = None,
        **kwargs
    ):
        """乐观锁更新 with 重试"""
        max_retries = max_retries or self._max_retries
        
        for attempt in range(max_retries + 1):
            try:
                # 在锁保护下执行更新
                result = await self.with_job_lock(job_id, update_operation, *args, **kwargs)
                return result
                
            except Exception as e:
                if "version" in str(e).lower() or "concurrent" in str(e).lower():
                    # 版本冲突，重试
                    if attempt < max_retries:
                        delay = self._base_retry_delay * (2 ** attempt)
                        logger.warning(f"检测到并发冲突，{delay:.2f}秒后重试 (尝试 {attempt + 1}/{max_retries + 1})")
                        await asyncio.sleep(delay)
                        continue
                
                # 其他错误或重试次数用完
                logger.error(f"乐观锁更新失败: {e}")
                raise
        
        raise Exception("乐观锁更新重试次数已用完")
    
    async def check_lock_status(self, job_id: str) -> Dict[str, Any]:
        """检查锁状态"""
        lock_key = f"job_state_lock:{job_id}"
        
        try:
            lock_value = await self.redis.get(lock_key)
            ttl = await self.redis.ttl(lock_key)
            
            return {
                "job_id": job_id,
                "is_locked": lock_value is not None,
                "lock_value": lock_value,
                "ttl": ttl,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"检查任务 {job_id} 锁状态失败: {e}")
            return {
                "job_id": job_id,
                "is_locked": False,
                "error": str(e),
                "timestamp": time.time()
            }
    
    async def force_release_lock(self, job_id: str) -> bool:
        """强制释放锁（谨慎使用）"""
        lock_key = f"job_state_lock:{job_id}"
        
        try:
            await self.redis.delete(lock_key)
            logger.warning(f"强制释放任务 {job_id} 锁")
            return True
            
        except Exception as e:
            logger.error(f"强制释放任务 {job_id} 锁失败: {e}")
            return False
    
    async def get_all_locks(self) -> Dict[str, Any]:
        """获取所有锁信息"""
        try:
            pattern = "job_state_lock:*"
            keys = await self.redis.keys(pattern)
            
            locks = {}
            for key in keys:
                job_id = key.replace("job_state_lock:", "")
                lock_info = await self.check_lock_status(job_id)
                locks[job_id] = lock_info
            
            return {
                "total_locks": len(locks),
                "locks": locks,
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"获取所有锁信息失败: {e}")
            return {
                "total_locks": 0,
                "locks": {},
                "error": str(e),
                "timestamp": time.time()
            }
    
    async def cleanup_expired_locks(self) -> int:
        """清理过期锁"""
        try:
            pattern = "job_state_lock:*"
            keys = await self.redis.keys(pattern)
            
            cleaned_count = 0
            for key in keys:
                ttl = await self.redis.ttl(key)
                if ttl <= 0:
                    await self.redis.delete(key)
                    cleaned_count += 1
                    logger.info(f"清理过期锁: {key}")
            
            if cleaned_count > 0:
                logger.info(f"清理了 {cleaned_count} 个过期锁")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"清理过期锁失败: {e}")
            return 0
