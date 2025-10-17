"""
统一状态机服务 - 核心状态机逻辑
"""
import asyncio
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.state_machine.states import (
    JobState, JobStatus, is_valid_transition, is_terminal_state, 
    get_job_status_from_state, get_prd_status_from_state, 
    get_state_timeout, can_retry_from_state, get_retry_target_state
)
from app.models.database.job import Job
from app.models.database.job_state_audit_log import JobStateAuditLog
from app.services.redis import RedisServiceFactory
from app.utils.redis_key_builder import redis_key_builder, RedisKeyType
from app.utils.json_utils import make_json_safe


class StateMachineService:
    """统一状态机服务 - 核心状态机逻辑"""
    
    def __init__(self, redis_service=None):
        self.redis = redis_service or RedisServiceFactory.get_service()
    
    async def transition(
        self, 
        db: AsyncSession,
        job_id: str, 
        to_state: str, 
        transition_reason: str = "normal_transition",
        operator_id: Optional[str] = None,
        operator_type: str = "system",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        执行状态转换
        
        Args:
            db: 数据库会话
            job_id: Job ID
            to_state: 目标状态
            transition_reason: 转换原因
            operator_id: 操作者ID
            operator_type: 操作者类型
            metadata: 转换时的额外信息
            
        Returns:
            bool: 转换是否成功
        """
        # 使用乐观锁重试机制
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # 1. 获取当前Job（使用乐观锁）
                job = await self._get_job_with_version(db, job_id)
                if not job:
                    logger.error(f"Job {job_id} 不存在")
                    return False
                
                # 2. 验证转换合法性
                if not self._validate_transition(job, to_state):
                    logger.error(f"Job {job_id} 状态转换无效: {job.current_state} -> {to_state}")
                    return False
                
                # 3. 记录状态历史
                await self._record_state_audit_log(
                    db, job_id, job.current_state, to_state, 
                    transition_reason, operator_id, operator_type, metadata
                )
                
                # 4. 更新Job状态（使用乐观锁）
                old_state = job.current_state
                old_version = job.version
                success = await self._update_job_state(
                    db, job_id, to_state, old_version, metadata
                )
                
                if success:
                    # 5. 更新Redis缓存
                    await self._update_redis_cache(job_id, to_state, metadata)
                    
                    # 6. 设置状态超时
                    await self._set_state_timeout(job_id, to_state)
                    
                    # 7. 提交数据库事务
                    await db.commit()
                    
                    logger.info(f"Job {job_id} 状态转换成功: {old_state} -> {to_state}")
                    return True
                else:
                    # 乐观锁冲突，重试
                    if attempt < max_retries - 1:
                        logger.warning(f"Job {job_id} 状态更新冲突，重试 {attempt + 1}/{max_retries}")
                        await asyncio.sleep(0.1 * (2 ** attempt))  # 指数退避
                        continue
                    else:
                        logger.error(f"Job {job_id} 状态更新失败，重试次数已用完")
                        return False
                
            except Exception as e:
                logger.error(f"Job {job_id} 状态转换失败: {e}")
                await db.rollback()
                return False
        
        return False
    
    async def get_current_state(self, db: AsyncSession, job_id: str) -> Optional[str]:
        """获取当前状态"""
        try:
            # 优先从Redis获取
            redis_key = redis_key_builder.task_status(job_id)
            cached_state = await self.redis.get(redis_key)
            if cached_state:
                return cached_state
            
            # 从数据库获取
            job = await self._get_job(db, job_id)
            return job.current_state if job else None
            
        except Exception as e:
            logger.error(f"获取Job {job_id} 状态失败: {e}")
            return None
    
    async def is_terminal_state(self, db: AsyncSession, job_id: str) -> bool:
        """检查是否为终态"""
        current_state = await self.get_current_state(db, job_id)
        return is_terminal_state(current_state) if current_state else False
    
    async def mark_failed(
        self, 
        db: AsyncSession, 
        job_id: str, 
        error_message: str,
        operator_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """标记Job为失败状态"""
        try:
            # 更新错误信息
            await self._update_job_error(db, job_id, error_message)
            
            # 执行状态转换
            transition_metadata = (metadata or {}).copy()
            transition_metadata["error_message"] = error_message
            return await self.transition(
                db, job_id, JobState.FAILED.value, 
                "mark_failed", operator_id, "system",
                transition_metadata
            )
            
        except Exception as e:
            logger.error(f"标记Job {job_id} 失败状态时出错: {e}")
            return False
    
    async def mark_completed(
        self, 
        db: AsyncSession, 
        job_id: str, 
        result_metadata: Optional[Dict[str, Any]] = None,
        operator_id: Optional[str] = None
    ) -> bool:
        """标记Job为完成状态"""
        try:
            return await self.transition(
                db, job_id, JobState.COMPLETED.value, 
                "mark_completed", operator_id, "system", result_metadata
            )
        except Exception as e:
            logger.error(f"标记Job {job_id} 完成状态时出错: {e}")
            return False
    
    async def handle_retry(
        self, 
        db: AsyncSession, 
        job_id: str, 
        retry_metadata: Optional[Dict[str, Any]] = None,
        operator_id: Optional[str] = None
    ) -> bool:
        """处理任务重试"""
        try:
            job = await self._get_job(db, job_id)
            if not job:
                logger.error(f"Job {job_id} 不存在")
                return False
            
            current_state = job.current_state
            if not current_state:
                logger.error(f"Job {job_id} 没有当前状态")
                return False
            
            # 检查是否支持重试
            if not can_retry_from_state(current_state):
                logger.warning(f"Job {job_id} 当前状态 {current_state} 不支持重试")
                return False
            
            # 确定重试目标状态
            retry_target_state = get_retry_target_state(current_state)
            
            retry_metadata = retry_metadata or {}
            retry_metadata["retry_reason"] = "task_retry"
            retry_metadata["retry_timestamp"] = str(int(time.time()))
            retry_metadata["retry_count"] = retry_metadata.get("retry_count", 0) + 1
            
            # 执行重试状态转换
            if retry_target_state != current_state:
                logger.info(f"Job {job_id} 重试时状态转换: {current_state} -> {retry_target_state}")
                return await self.transition(
                    db, job_id, retry_target_state, 
                    "retry_transition", operator_id, "retry", retry_metadata
                )
            else:
                # 同状态重试，只记录重试信息
                await self._record_state_audit_log(
                    db, job_id, current_state, current_state, 
                    "retry_same_state", operator_id, "retry", retry_metadata
                )
                
                # 更新Redis缓存
                await self._update_redis_cache(job_id, current_state, retry_metadata)
                
                # 重新设置超时
                await self._set_state_timeout(job_id, current_state)
                
                # 提交数据库事务
                await db.commit()
                
                logger.info(f"Job {job_id} 重试处理成功，保持状态: {current_state}")
                return True
            
        except Exception as e:
            logger.error(f"处理Job {job_id} 重试时出错: {e}")
            await db.rollback()
            return False
    
    async def check_timeout_tasks(self, db: AsyncSession) -> List[str]:
        """检查超时任务"""
        try:
            timeout_tasks = []
            
            # 获取所有处理中的任务
            processing_tasks_key = redis_key_builder.set_processing_tasks()
            task_ids = await self.redis.smembers(processing_tasks_key)
            
            for task_id in task_ids:
                if await self._is_task_timeout(task_id):
                    # 标记为超时失败
                    await self.mark_failed(
                        db, task_id, "任务执行超时", 
                        "system", {"timeout_reason": "state_timeout"}
                    )
                    timeout_tasks.append(task_id)
            
            return timeout_tasks
            
        except Exception as e:
            logger.error(f"检查超时任务失败: {e}")
            return []
    
    # 私有方法
    
    
    async def _get_job(self, db: AsyncSession, job_id: str) -> Optional[Job]:
        """获取Job对象"""
        result = await db.execute(select(Job).where(Job.job_id == job_id))
        return result.scalar_one_or_none()
    
    async def _get_job_with_version(self, db: AsyncSession, job_id: str) -> Optional[Job]:
        """获取Job对象（包含版本号）"""
        result = await db.execute(select(Job).where(Job.job_id == job_id))
        return result.scalar_one_or_none()
    
    def _validate_transition(self, job: Job, to_state: str) -> bool:
        """验证状态转换是否有效"""
        if not job.current_state:
            # 初始状态，只能转换到第一个状态
            return to_state in [JobState.UPLOADING.value, JobState.FAILED.value]
        
        # 检查completed状态不能转换
        if job.current_state == JobState.COMPLETED.value:
            logger.warning(f"Job {job.job_id} 已完成，不允许状态转换")
            return False
        
        return is_valid_transition(job.job_type, job.current_state, to_state)
    
    async def _record_state_audit_log(
        self, 
        db: AsyncSession, 
        job_id: str, 
        from_state: str, 
        to_state: str, 
        transition_reason: str,
        operator_id: Optional[str],
        operator_type: str,
        metadata: Optional[Dict[str, Any]]
    ):
        """记录状态转换审计日志"""
        # 安全地序列化metadata
        serialized_metadata = None
        if metadata:
            try:
                safe_metadata = make_json_safe(metadata)
                serialized_metadata = safe_metadata
            except Exception as e:
                logger.warning(f"序列化metadata失败: {e}")
                serialized_metadata = {"error": "metadata_serialization_failed"}
        
        audit_log = JobStateAuditLog(
            job_id=job_id,
            from_state=from_state,
            to_state=to_state,
            transition_reason=transition_reason,
            operator_id=operator_id,
            operator_type=operator_type,
            transition_metadata=serialized_metadata
        )
        db.add(audit_log)
    
    async def _update_job_state(
        self, 
        db: AsyncSession, 
        job_id: str, 
        to_state: str, 
        old_version: int,
        metadata: Optional[Dict[str, Any]]
    ) -> bool:
        """更新Job状态（使用乐观锁）"""
        try:
            # 更新状态和版本号
            result = await db.execute(
                update(Job)
                .where(Job.job_id == job_id, Job.version == old_version)
                .values(
                    current_state=to_state,
                    status=get_job_status_from_state(to_state),
                    version=old_version + 1,
                    updated_at=datetime.utcnow()
                )
            )
            
            return result.rowcount > 0
            
        except Exception as e:
            logger.error(f"更新Job状态失败: {e}")
            return False
    
    async def _update_job_error(self, db: AsyncSession, job_id: str, error_message: str):
        """更新Job错误信息"""
        try:
            await db.execute(
                update(Job)
                .where(Job.job_id == job_id)
                .values(error_message=error_message)
            )
        except Exception as e:
            logger.error(f"更新Job错误信息失败: {e}")
    
    async def _update_redis_cache(self, job_id: str, current_state: str, metadata: Optional[Dict[str, Any]]):
        """更新Redis缓存"""
        try:
            # 更新状态缓存
            status_key = redis_key_builder.task_status(job_id)
            await self.redis.set(status_key, current_state, ttl=redis_key_builder.get_key_ttl(RedisKeyType.TASK))
            
            # 更新进度信息
            progress_key = redis_key_builder.task_progress(job_id)
            progress_data = {
                "status": get_prd_status_from_state(current_state),
                "current_state": current_state,
                "timestamp": str(int(time.time()))
            }
            if metadata:
                progress_data.update(metadata)
            
            await self.redis.hset(progress_key, mapping=progress_data)
            await self.redis.expire(progress_key, redis_key_builder.get_key_ttl(RedisKeyType.TASK))
            
        except Exception as e:
            logger.error(f"更新Redis缓存失败: {e}")
    
    async def _set_state_timeout(self, job_id: str, state: str):
        """设置状态超时"""
        try:
            timeout = get_state_timeout(state)
            if timeout > 0:
                timeout_key = f"job_timeout:{job_id}"
                await self.redis.set(timeout_key, state, ex=timeout)
        except Exception as e:
            logger.error(f"设置状态超时失败: {e}")
    
    async def _is_task_timeout(self, task_id: str) -> bool:
        """检查任务是否超时"""
        try:
            timeout_key = f"job_timeout:{task_id}"
            return await self.redis.exists(timeout_key) == 0
        except Exception as e:
            logger.error(f"检查任务超时失败: {e}")
            return False
