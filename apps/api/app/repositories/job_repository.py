"""
Job仓储层
"""
from typing import Any, Dict, List, Optional, Sequence
from datetime import datetime

from shared.models.database.job import Job
from shared.models.database.job_state_history import JobStateHistory
from app.services.state_machine import JobStateMachine
from loguru import logger
from sqlalchemy import and_, desc, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class JobRepository:
    """Job仓储类"""
    
    def __init__(self):
        self.state_machine = JobStateMachine()
    
    async def create_job(
        self, 
        db: AsyncSession, 
        user_id: str, 
        job_type: str, 
        source_type: str,
        job_id: Optional[str] = None,
        file_path: Optional[str] = None,
        webhook_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        initial_state: Optional[str] = "pending",
        s3_key: Optional[str] = None
    ) -> Optional[Job]:
        """创建Job"""
        try:
            job_kwargs = dict(
                user_id=user_id,
                job_type=job_type,
                status=initial_state or "pending",
                source_type=source_type,
                file_path=file_path,
                webhook_url=webhook_url,
                webhook_enabled=bool(webhook_url),
                job_metadata=metadata,
                s3_key=s3_key
            )
            if job_id:
                job_kwargs["job_id"] = job_id
            
            job = Job(**job_kwargs)
            
            db.add(job)
            await db.commit()
            # Skip db.refresh() — all fields are already set in-memory.
            # This avoids an extra SELECT round-trip after INSERT.

            logger.info(f"Job {job.job_id} 创建成功")
            return job
            
        except IntegrityError as e:
            logger.error(f"创建Job失败: {e}")
            await db.rollback()
            raise
        except Exception as e:
            logger.error(f"创建Job失败: {e}")
            await db.rollback()
            return None
    
    async def get_job_by_id(self, db: AsyncSession, job_id: str) -> Optional[Job]:
        """根据ID获取Job (only loads job_result; state_history loaded on demand)"""
        try:
            stmt = (
                select(Job)
                .options(selectinload(Job.job_result))
                .where(Job.job_id == job_id)
            )
            result = await db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"获取Job {job_id} 失败: {e}")
            return None
    
    async def get_jobs_by_user(
        self,
        db: AsyncSession,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        job_type: Optional[str] = None,
        job_status: Optional[str] = None,
    ) -> Sequence[Job]:
        """获取用户的Jobs"""
        try:
            stmt = (
                select(Job)
                .options(selectinload(Job.job_result))
                .where(Job.user_id == user_id)
                .order_by(desc(Job.created_at))
                .limit(limit)
                .offset(offset)
            )
            if created_after:
                stmt = stmt.where(Job.created_at >= created_after)
            if created_before:
                stmt = stmt.where(Job.created_at <= created_before)
            if job_type:
                stmt = stmt.where(Job.job_type == job_type)
            if job_status:
                stmt = stmt.where(Job.status == job_status)
            result = await db.execute(stmt)
            return result.scalars().all()
        except Exception as e:
            logger.error(f"获取用户 {user_id} Jobs失败: {e}")
            return []
    
    async def count_jobs_by_user(
        self,
        db: AsyncSession,
        user_id: str,
        created_after: Optional[datetime] = None,
        created_before: Optional[datetime] = None,
        job_type: Optional[str] = None,
        job_status: Optional[str] = None,
    ) -> int:
        """获取用户的Jobs总数"""
        try:
            from sqlalchemy import func
            stmt = select(func.count()).select_from(Job).where(Job.user_id == user_id)
            if created_after:
                stmt = stmt.where(Job.created_at >= created_after)
            if created_before:
                stmt = stmt.where(Job.created_at <= created_before)
            if job_type:
                stmt = stmt.where(Job.job_type == job_type)
            if job_status:
                stmt = stmt.where(Job.status == job_status)
            result = await db.execute(stmt)
            return result.scalar() or 0
        except Exception as e:
            logger.error(f"获取用户 {user_id} Jobs总数失败: {e}")
            return 0
    
    async def update_job_state(
        self, 
        db: AsyncSession, 
        job_id: str, 
        to_state: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """更新Job状态（通过状态机）"""
        return await self.state_machine.transition(
            db, job_id, to_state, 
            "repository_update", None, "system", metadata
        )
    
    async def update_job_s3_key(
        self,
        db: AsyncSession,
        job_id: str,
        s3_key: str
    ) -> bool:
        """更新Job的S3键"""
        try:
            stmt = (
                update(Job)
                .where(Job.job_id == job_id)
                .values(s3_key=s3_key)
            )
            result = await db.execute(stmt)
            await db.commit()
            return result.rowcount > 0

        except Exception as e:
            logger.error(f"更新Job {job_id} S3键失败: {e}")
            await db.rollback()
            return False
    
    async def update_job_file_url(
        self,
        db: AsyncSession,
        job_id: str,
        file_url: str
    ) -> bool:
        """更新Job的文件URL (direct UPDATE + Redis, no ORM load)"""
        try:
            from sqlalchemy import func
            from sqlalchemy.dialects.postgresql import JSONB, array as pg_array
            from shared.services.redis import RedisServiceFactory
            from shared.services.redis.job_metadata_service import JobMetadataService

            # Direct UPDATE using jsonb_set to patch only the file_url key
            stmt = (
                update(Job)
                .where(Job.job_id == job_id)
                .values(
                    job_metadata=func.jsonb_set(
                        func.coalesce(Job.job_metadata.cast(JSONB), func.cast("{}", JSONB)),
                        pg_array(["file_url"]),
                        func.to_jsonb(file_url),
                    )
                )
            )
            result = await db.execute(stmt)
            await db.commit()

            if result.rowcount == 0:
                return False

            # Update Redis cache
            redis_service = RedisServiceFactory.get_service()
            metadata_service = JobMetadataService(redis_service)
            await metadata_service.update_metadata(job_id, {"file_url": file_url})
            return True

        except Exception as e:
            logger.error(f"更新Job {job_id} 文件URL失败: {e}")
            await db.rollback()
            return False
    
    async def mark_job_failed(
        self, 
        db: AsyncSession, 
        job_id: str, 
        error_message: str
    ) -> bool:
        """标记Job为失败"""
        return await self.state_machine.mark_failed(db, job_id, error_message)
    
    async def mark_job_completed(
        self, 
        db: AsyncSession, 
        job_id: str, 
        result_metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """标记Job为完成"""
        return await self.state_machine.mark_completed(db, job_id, result_metadata)
    
    async def get_job_state_history(
        self, 
        db: AsyncSession, 
        job_id: str
    ) -> Sequence[JobStateHistory]:
        """获取Job状态历史"""
        try:
            result = await db.execute(
                select(JobStateHistory)
                .where(JobStateHistory.job_id == job_id)
                .order_by(JobStateHistory.created_at)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"获取Job {job_id} 状态历史失败: {e}")
            return []
    
    async def get_jobs_by_status(
        self, 
        db: AsyncSession, 
        status: str, 
        limit: int = 100
    ) -> Sequence[Job]:
        """根据状态获取Jobs"""
        try:
            result = await db.execute(
                select(Job)
                .options(selectinload(Job.job_result))
                .where(Job.status == status)
                .order_by(Job.created_at)
                .limit(limit)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"获取状态为 {status} 的Jobs失败: {e}")
            return []
    
    async def update_job_status(
        self,
        db: AsyncSession,
        job_id: str,
        status: str,
        error_message: Optional[str] = None
    ) -> bool:
        """更新Job状态 (direct UPDATE, no ORM load)"""
        try:
            values: Dict[str, Any] = {"status": status}
            if error_message:
                values["error_message"] = error_message

            stmt = update(Job).where(Job.job_id == job_id).values(**values)
            result = await db.execute(stmt)
            await db.commit()

            if result.rowcount > 0:
                logger.info(f"Job {job_id} 状态更新为 {status}")
                return True
            return False
        except Exception as e:
            await db.rollback()
            logger.error(f"更新Job {job_id} 状态失败: {e}")
            return False
    
    async def get_job_state_metadata(
        self, 
        db: AsyncSession, 
        job_id: str, 
        state: str, 
        metadata_key: str
    ) -> Optional[Any]:
        """获取Job状态历史中的特定元数据"""
        try:
            result = await db.execute(
                select(JobStateHistory.transition_metadata)
                .where(
                    and_(
                        JobStateHistory.job_id == job_id,
                        JobStateHistory.to_state == state
                    )
                )
                .order_by(desc(JobStateHistory.created_at))
                .limit(1)
            )
            metadata = result.scalar_one_or_none()
            
            if metadata:
                # 如果metadata是字符串，尝试解析JSON
                if isinstance(metadata, str):
                    try:
                        import json
                        metadata = json.loads(metadata)
                    except json.JSONDecodeError as e:
                        logger.error(f"解析Job {job_id} 状态 {state} 元数据JSON失败: {e}")
                        return None
                
                # 如果metadata是字典，返回指定key的值
                if isinstance(metadata, dict):
                    return metadata.get(metadata_key)
            
            return None
            
        except Exception as e:
            logger.error(f"获取Job {job_id} 状态 {state} 元数据 {metadata_key} 失败: {e}")
            return None
    
    async def get_job_metadata(
        self,
        db: AsyncSession,
        job_id: str,
        redis_service: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        获取job_metadata（优先从Redis读取，2小时缓存）

        Args:
            db: 数据库会话
            job_id: 任务ID
            redis_service: Redis服务

        Returns:
            job_metadata字典或None
        """
        # 1. 尝试从Redis获取
        if redis_service:
            from shared.services.redis.job_metadata_service import \
                JobMetadataService
            metadata_service = JobMetadataService(redis_service)
            metadata = await metadata_service.get_metadata(job_id)
            if metadata:
                return metadata

        # 2. Lightweight scalar query — only fetch the JSON column, no ORM load
        try:
            result = await db.execute(
                select(Job.job_metadata).where(Job.job_id == job_id)
            )
            metadata = result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"获取Job {job_id} metadata失败: {e}")
            metadata = None

        if metadata:
            # 回写到Redis（2小时缓存）
            if redis_service:
                from shared.services.redis.job_metadata_service import \
                    JobMetadataService
                metadata_service = JobMetadataService(redis_service)
                await metadata_service.save_metadata(job_id, metadata)
            return metadata

        return None
