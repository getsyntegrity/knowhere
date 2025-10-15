"""
统一状态机管理器
"""
import json
from typing import Optional, Dict, Any
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.state_machine.states import (
    is_valid_transition, is_terminal_state, get_job_status_from_state, get_prd_status_from_state
)
from app.models.database.job import Job
from app.models.database.job_state_history import JobStateHistory
from app.services.redis import RedisServiceFactory
from app.utils.redis_key_builder import redis_key_builder, RedisKeyType
from app.utils.json_utils import make_json_safe


class JobStateMachine:
    """Job状态机管理器 - 高内聚"""
    
    def __init__(self, redis_service=None):
        self.redis = redis_service or RedisServiceFactory.get_service()
    
    async def transition(
        self, 
        db: AsyncSession,
        job_id: str, 
        to_state: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        执行状态转换
        
        Args:
            db: 数据库会话
            job_id: Job ID
            to_state: 目标状态
            metadata: 转换时的额外信息
            
        Returns:
            bool: 转换是否成功
        """
        try:
            # 1. 获取当前Job
            job = await self._get_job(db, job_id)
            if not job:
                logger.error(f"Job {job_id} 不存在")
                return False
            
            # 2. 验证转换合法性
            if not self._validate_transition(job, to_state):
                logger.error(f"Job {job_id} 状态转换无效: {job.current_state} -> {to_state}")
                return False
            
            # 3. 记录状态历史
            await self._record_state_history(db, job_id, job.current_state, to_state, metadata)
            
            # 4. 更新Job状态
            old_state = job.current_state
            job.current_state = to_state
            job.status = get_job_status_from_state(to_state)
            status_for_cache = get_prd_status_from_state(to_state)
            
            # 5. 更新Redis缓存
            await self._update_redis_cache(job_id, to_state, status_for_cache)
            
            # 6. 提交数据库事务
            await db.commit()
            
            logger.info(f"Job {job_id} 状态转换成功: {old_state} -> {to_state}")
            return True
            
        except Exception as e:
            logger.error(f"Job {job_id} 状态转换失败: {e}")
            await db.rollback()
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
    
    def _validate_transition(self, job: Job, to_state: str) -> bool:
        """验证状态转换是否有效"""
        if not job.current_state:
            # 初始状态，只能转换到第一个状态
            if job.job_type == "table_fill":
                return to_state in ["uploading", "failed"]
            elif job.job_type == "kb_management":
                return to_state in ["uploading", "failed"]
            return False
        
        return is_valid_transition(job.job_type, job.current_state, to_state)
    
    async def _get_job(self, db: AsyncSession, job_id: str) -> Optional[Job]:
        """获取Job对象"""
        from sqlalchemy import select
        result = await db.execute(select(Job).where(Job.job_id == job_id))
        return result.scalar_one_or_none()
    
    async def _record_state_history(
        self, 
        db: AsyncSession, 
        job_id: str, 
        from_state: str, 
        to_state: str, 
        metadata: Optional[Dict[str, Any]] = None
    ):
        """记录状态历史"""
        # 安全地序列化metadata，处理不可序列化的对象
        serialized_metadata = None
        if metadata:
            try:
                safe_metadata = make_json_safe(metadata)
                serialized_metadata = json.dumps(safe_metadata, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"序列化metadata失败: {e}")
                serialized_metadata = json.dumps(
                    {"error": "metadata_serialization_failed"},
                    ensure_ascii=False
                )
        
        history = JobStateHistory(
            job_id=job_id,
            from_state=from_state or "pending",
            to_state=to_state,
            transition_metadata=serialized_metadata
        )
        db.add(history)
    
    async def _update_redis_cache(self, job_id: str, current_state: str, status: str):
        """更新Redis缓存"""
        try:
            # 更新状态缓存
            status_key = redis_key_builder.task_status(job_id)
            await self.redis.set(status_key, current_state, ttl=redis_key_builder.get_key_ttl(RedisKeyType.TASK))
            
            # 更新进度信息
            progress_key = redis_key_builder.task_progress(job_id)
            progress_data = {
                "status": status,
                "current_state": current_state,
                "timestamp": str(int(__import__('time').time()))
            }
            await self.redis.hset(progress_key, mapping=progress_data)
            await self.redis.expire(progress_key, redis_key_builder.get_key_ttl(RedisKeyType.TASK))
            
        except Exception as e:
            logger.error(f"更新Redis缓存失败: {e}")
    
    async def mark_failed(self, db: AsyncSession, job_id: str, error_message: str) -> bool:
        """标记Job为失败状态"""
        try:
            job = await self._get_job(db, job_id)
            if not job:
                return False
            
            job.error_message = error_message
            return await self.transition(db, job_id, "failed", {"error": error_message})
            
        except Exception as e:
            logger.error(f"标记Job {job_id} 失败状态时出错: {e}")
            return False
    
    async def mark_completed(self, db: AsyncSession, job_id: str, result_metadata: Optional[Dict[str, Any]] = None) -> bool:
        """标记Job为完成状态"""
        try:
            return await self.transition(db, job_id, "completed", result_metadata)
        except Exception as e:
            logger.error(f"标记Job {job_id} 完成状态时出错: {e}")
            return False
    
    async def handle_retry(self, db: AsyncSession, job_id: str, retry_metadata: Optional[Dict[str, Any]] = None) -> bool:
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
            
            # 确定重试目标状态
            retry_target_state = self._get_retry_target_state(job.job_type, current_state)
            
            retry_metadata = retry_metadata or {}
            retry_metadata["retry_reason"] = "task_retry"
            retry_metadata["retry_timestamp"] = str(int(__import__('time').time()))
            retry_metadata["retry_count"] = retry_metadata.get("retry_count", 0) + 1
            
            # 如果需要转换状态，执行转换
            if retry_target_state != current_state:
                logger.info(f"Job {job_id} 重试时状态转换: {current_state} -> {retry_target_state}")
                return await self.transition(db, job_id, retry_target_state, retry_metadata)
            else:
                # 如果重试状态是pending，需要重新启动整个工作流
                if retry_target_state == "pending":
                    logger.info(f"Job {job_id} 重试，重新启动工作流: {current_state} -> pending")
                    return await self.transition(db, job_id, "pending", retry_metadata)
                else:
                    # 保持当前状态，但记录重试信息
                    await self._record_state_history(db, job_id, current_state, current_state, retry_metadata)
                    
                    # 更新Redis缓存
                    await self._update_redis_cache(job_id, current_state, job.status)
                    
                    # 提交数据库事务
                    await db.commit()
                    
                    logger.info(f"Job {job_id} 重试处理成功，保持状态: {current_state}")
                    return True
            
        except Exception as e:
            logger.error(f"处理Job {job_id} 重试时出错: {e}")
            await db.rollback()
            return False
    
    def _get_retry_target_state(self, job_type: str, current_state: str) -> str:
        """获取重试目标状态"""
        # 定义重试状态映射 - 重试时应该回到上一个稳定的状态
        retry_state_mapping = {
            "table_fill": {
                "uploading": "pending",  # 上传失败，回到待处理
                "extracting_table": "uploaded",  # 提取表格失败，回到已上传
                "kb_searching": "table_extracted",  # 知识库检索失败，回到表格已提取
                "llm_processing": "kb_searched",  # LLM处理失败，回到知识库已检索
                "filling_table": "llm_processed",  # 填充表格失败，回到LLM已处理
                "generating_result": "table_filled",  # 生成结果失败，回到表格已填充
                "failed": "pending",  # 失败后重试，回到待处理
            },
            "kb_management": {
                "uploading": "pending",  # 上传失败，回到待处理
                "parsing": "uploaded",  # 解析失败，回到已上传
                "vectorizing": "parsing",  # 向量化失败，回到解析状态
                "storing_db": "vectorized",  # 存储失败，回到已向量化
                "failed": "pending",  # 失败后重试，回到待处理
            }
        }
        
        job_retry_mapping = retry_state_mapping.get(job_type, {})
        retry_state = job_retry_mapping.get(current_state, current_state)
        
        # 如果重试状态是pending，需要重新启动整个工作流
        if retry_state == "pending":
            # 对于pending状态，返回pending以重新启动工作流
            return "pending"
        
        return retry_state
    
    async def handle_failed_retry(self, db: AsyncSession, job_id: str, retry_metadata: Optional[Dict[str, Any]] = None) -> bool:
        """处理失败后的重试"""
        try:
            job = await self._get_job(db, job_id)
            if not job:
                logger.error(f"Job {job_id} 不存在")
                return False
            
            if job.current_state != "failed":
                logger.warning(f"Job {job_id} 当前状态不是failed，无法执行失败重试")
                return False
            
            retry_metadata = retry_metadata or {}
            retry_metadata["retry_reason"] = "failed_retry"
            retry_metadata["retry_timestamp"] = str(int(__import__('time').time()))
            retry_metadata["retry_count"] = retry_metadata.get("retry_count", 0) + 1
            
            # 失败后重试，回到pending状态
            logger.info(f"Job {job_id} 失败后重试，状态转换: failed -> pending")
            return await self.transition(db, job_id, "pending", retry_metadata)
            
        except Exception as e:
            logger.error(f"处理Job {job_id} 失败重试时出错: {e}")
            await db.rollback()
            return False
