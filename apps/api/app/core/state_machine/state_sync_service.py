"""
状态同步服务 - Redis和数据库状态同步
"""
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.database.job import Job
from app.services.redis import RedisServiceFactory
from app.utils.redis_key_builder import redis_key_builder, RedisKeyType


class StateSyncService:
    """状态同步服务 - Redis和数据库状态同步"""
    
    def __init__(self, redis_service=None):
        self.redis = redis_service or RedisServiceFactory.get_service()
    
    async def sync_job_state_to_redis(self, db: AsyncSession, job_id: str) -> bool:
        """将数据库状态同步到Redis"""
        try:
            # 从数据库获取Job状态
            job = await self._get_job(db, job_id)
            if not job:
                logger.warning(f"Job {job_id} 不存在，无法同步到Redis")
                return False
            
            # 更新Redis缓存
            await self._update_redis_from_job(job)
            
            logger.info(f"Job {job_id} 状态已同步到Redis: {job.current_state}")
            return True
            
        except Exception as e:
            logger.error(f"同步Job {job_id} 状态到Redis失败: {e}")
            return False
    
    async def sync_job_state_from_redis(self, db: AsyncSession, job_id: str) -> bool:
        """将Redis状态同步到数据库"""
        try:
            # 从Redis获取状态
            redis_state = await self._get_redis_state(job_id)
            if not redis_state:
                logger.warning(f"Job {job_id} 在Redis中不存在，无法同步到数据库")
                return False
            
            # 从数据库获取Job
            job = await self._get_job(db, job_id)
            if not job:
                logger.warning(f"Job {job_id} 在数据库中不存在，无法同步")
                return False
            
            # 检查状态是否一致
            if job.current_state == redis_state:
                logger.debug(f"Job {job_id} 状态已一致，无需同步")
                return True
            
            # 更新数据库状态
            job.current_state = redis_state
            job.status = self._get_job_status_from_state(redis_state)
            job.updated_at = datetime.utcnow()
            
            await db.commit()
            
            logger.info(f"Job {job_id} 状态已从Redis同步到数据库: {redis_state}")
            return True
            
        except Exception as e:
            logger.error(f"同步Job {job_id} 状态从Redis到数据库失败: {e}")
            await db.rollback()
            return False
    
    async def check_state_consistency(self, db: AsyncSession, job_id: str) -> Dict[str, Any]:
        """检查状态一致性"""
        try:
            # 获取数据库状态
            job = await self._get_job(db, job_id)
            db_state = job.current_state if job else None
            
            # 获取Redis状态
            redis_state = await self._get_redis_state(job_id)
            
            # 检查一致性
            is_consistent = db_state == redis_state
            
            result = {
                "job_id": job_id,
                "is_consistent": is_consistent,
                "db_state": db_state,
                "redis_state": redis_state,
                "timestamp": time.time()
            }
            
            if not is_consistent:
                logger.warning(f"Job {job_id} 状态不一致: DB={db_state}, Redis={redis_state}")
            
            return result
            
        except Exception as e:
            logger.error(f"检查Job {job_id} 状态一致性失败: {e}")
            return {
                "job_id": job_id,
                "is_consistent": False,
                "error": str(e),
                "timestamp": time.time()
            }
    
    async def repair_inconsistent_states(self, db: AsyncSession, job_ids: List[str]) -> Dict[str, bool]:
        """修复不一致的状态"""
        results = {}
        
        for job_id in job_ids:
            try:
                # 检查一致性
                consistency_check = await self.check_state_consistency(db, job_id)
                
                if consistency_check["is_consistent"]:
                    results[job_id] = True
                    continue
                
                # 以数据库状态为准进行修复
                job = await self._get_job(db, job_id)
                if job and job.current_state:
                    # 同步到Redis
                    await self._update_redis_from_job(job)
                    results[job_id] = True
                    logger.info(f"Job {job_id} 状态已修复，以数据库为准")
                else:
                    results[job_id] = False
                    logger.error(f"Job {job_id} 在数据库中不存在或状态为空")
                
            except Exception as e:
                logger.error(f"修复Job {job_id} 状态失败: {e}")
                results[job_id] = False
        
        return results
    
    async def batch_sync_all_states(self, db: AsyncSession) -> Dict[str, Any]:
        """批量同步所有状态"""
        try:
            # 获取所有处理中的任务
            processing_tasks_key = redis_key_builder.set_processing_tasks()
            redis_task_ids = await self.redis.smembers(processing_tasks_key)
            
            # 获取数据库中的处理中任务
            db_tasks = await self._get_processing_jobs_from_db(db)
            db_task_ids = {task.job_id for task in db_tasks}
            
            # 统计信息
            stats = {
                "redis_tasks": len(redis_task_ids),
                "db_tasks": len(db_task_ids),
                "sync_success": 0,
                "sync_failed": 0,
                "inconsistent_tasks": []
            }
            
            # 同步Redis任务到数据库
            for task_id in redis_task_ids:
                if task_id in db_task_ids:
                    # 检查一致性
                    consistency = await self.check_state_consistency(db, task_id)
                    if not consistency["is_consistent"]:
                        stats["inconsistent_tasks"].append(task_id)
                        # 尝试修复
                        if await self.sync_job_state_from_redis(db, task_id):
                            stats["sync_success"] += 1
                        else:
                            stats["sync_failed"] += 1
                    else:
                        stats["sync_success"] += 1
                else:
                    # Redis中存在但数据库中不存在，清理Redis
                    await self._cleanup_redis_task(task_id)
                    stats["sync_success"] += 1
            
            # 同步数据库任务到Redis
            for task in db_tasks:
                if task.job_id not in redis_task_ids:
                    if await self.sync_job_state_to_redis(db, task.job_id):
                        stats["sync_success"] += 1
                    else:
                        stats["sync_failed"] += 1
            
            logger.info(f"批量状态同步完成: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"批量状态同步失败: {e}")
            return {"error": str(e)}
    
    # 私有方法
    
    async def _get_job(self, db: AsyncSession, job_id: str) -> Optional[Job]:
        """获取Job对象"""
        result = await db.execute(select(Job).where(Job.job_id == job_id))
        return result.scalar_one_or_none()
    
    async def _get_processing_jobs_from_db(self, db: AsyncSession) -> List[Job]:
        """从数据库获取处理中的任务"""
        result = await db.execute(
            select(Job).where(Job.status.in_(["pending", "processing"]))
        )
        return result.scalars().all()
    
    async def _get_redis_state(self, job_id: str) -> Optional[str]:
        """从Redis获取状态"""
        try:
            status_key = redis_key_builder.task_status(job_id)
            return await self.redis.get(status_key)
        except Exception as e:
            logger.error(f"从Redis获取Job {job_id} 状态失败: {e}")
            return None
    
    async def _update_redis_from_job(self, job: Job):
        """从Job对象更新Redis"""
        try:
            # 更新状态缓存
            status_key = redis_key_builder.task_status(job.job_id)
            await self.redis.set(
                status_key, 
                job.current_state or "pending", 
                ttl=redis_key_builder.get_key_ttl(RedisKeyType.TASK)
            )
            
            # 更新进度信息
            progress_key = redis_key_builder.task_progress(job.job_id)
            progress_data = {
                "status": job.status,
                "current_state": job.current_state or "pending",
                "timestamp": str(int(time.time()))
            }
            await self.redis.hset(progress_key, mapping=progress_data)
            await self.redis.expire(progress_key, redis_key_builder.get_key_ttl(RedisKeyType.TASK))
            
            # 添加到处理中任务集合
            if job.status in ["pending", "processing"]:
                processing_tasks_key = redis_key_builder.set_processing_tasks()
                await self.redis.sadd(processing_tasks_key, job.job_id)
                await self.redis.expire(processing_tasks_key, redis_key_builder.get_key_ttl(RedisKeyType.SET))
            
        except Exception as e:
            logger.error(f"从Job更新Redis失败: {e}")
    
    async def _cleanup_redis_task(self, task_id: str):
        """清理Redis中的任务数据"""
        try:
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
            
            logger.info(f"Redis任务 {task_id} 数据已清理")
            
        except Exception as e:
            logger.error(f"清理Redis任务 {task_id} 数据失败: {e}")
    
    def _get_job_status_from_state(self, state: str) -> str:
        """根据状态获取Job状态"""
        if not state:
            return "pending"
        
        if state == "failed":
            return "failed"
        if state == "completed":
            return "completed"
        if state == "pending":
            return "pending"
        
        return "processing"
