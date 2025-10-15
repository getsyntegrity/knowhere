"""
Job结果仓储
"""
from typing import Dict, Any, List, Optional

from uuid import uuid4

from loguru import logger
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.database.job_result import JobResult, JobChunk


class JobResultRepository:
    """Job结果持久化访问层"""

    async def get_by_job_id(
        self,
        db: AsyncSession,
        job_id: str,
        with_chunks: bool = False
    ) -> Optional[JobResult]:
        """根据Job ID获取结果"""
        stmt = select(JobResult).where(JobResult.job_id == job_id)
        if with_chunks:
            stmt = stmt.options(selectinload(JobResult.chunks))
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_job_result(
        self,
        db: AsyncSession,
        job_id: str,
        delivery_mode: str,
        document_metadata: Optional[Dict[str, Any]] = None,
        *,
        inline_payload: Optional[Dict[str, Any]] = None,
        result_s3_key: Optional[str] = None,
        result_size: Optional[int] = None
    ) -> JobResult:
        """创建或更新Job结果"""
        existing = await self.get_by_job_id(db, job_id)
        if existing:
            existing.delivery_mode = delivery_mode
            existing.document_metadata = document_metadata or {}
            existing.inline_payload = inline_payload
            existing.result_s3_key = result_s3_key
            existing.result_size = result_size
            await db.commit()
            await db.refresh(existing)
            logger.info(f"更新JobResult成功: job_id={job_id}, mode={delivery_mode}")
            return existing

        job_result = JobResult(
            job_id=job_id,
            delivery_mode=delivery_mode,
            document_metadata=document_metadata or {},
            inline_payload=inline_payload,
            result_s3_key=result_s3_key,
            result_size=result_size
        )
        db.add(job_result)
        await db.commit()
        await db.refresh(job_result)
        logger.info(f"创建JobResult成功: job_id={job_id}, mode={delivery_mode}")
        return job_result

    async def replace_chunks(
        self,
        db: AsyncSession,
        job_result_id: str,
        chunks: List[Dict[str, Any]]
    ) -> None:
        """替换指定JobResult的Chunk列表"""
        await db.execute(delete(JobChunk).where(JobChunk.job_result_id == job_result_id))

        if chunks:
            chunk_models = []
            for index, chunk in enumerate(chunks):
                chunk_identifier = chunk.get("chunk_id") or str(uuid4())
                chunk_models.append(JobChunk(
                    job_result_id=job_result_id,
                    chunk_id=chunk_identifier,
                    chunk_type=chunk.get("type", "paragraph"),
                    text=chunk.get("text"),
                    path=chunk.get("metadata", {}).get("path"),
                    chunk_metadata=chunk.get("metadata"),
                    sort_order=chunk.get("order", index)
                ))
            db.add_all(chunk_models)

        await db.commit()

    async def delete_by_job_id(self, db: AsyncSession, job_id: str) -> None:
        """删除某个Job的结果及Chunk"""
        result = await self.get_by_job_id(db, job_id)
        if not result:
            return
        await db.delete(result)
        await db.commit()
