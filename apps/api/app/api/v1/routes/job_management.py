"""
统一Job管理API
提供Job系统的统一管理接口
"""
from typing import Optional

from app.core.dependencies import get_current_user, get_db
from shared.models.database.user import User
from app.repositories.job_repository import JobRepository
from app.services.state_machine import JobStateMachine
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from shared.core.exceptions.DomainExceptions import (
    JobOperationException,
    ValidationException,
    NotFoundException,
    PermissionDeniedException
)

router = APIRouter(tags=["Job管理"])


@router.get("/", summary="获取所有Job")
async def list_all_jobs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    job_type: Optional[str] = Query(None, description="任务类型过滤"),
    status: Optional[str] = Query(None, description="状态过滤"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取所有Job（管理员功能）"""
    try:
        # 检查用户权限（这里简化处理，实际应该检查管理员权限）
        if not current_user.is_superuser():
        if not current_user.is_superuser():
            raise PermissionDeniedException(
                resource="Job",
                user_message="需要管理员权限"
            )
        
        job_repo = JobRepository()
        
        # 获取所有Jobs
        jobs = await job_repo.get_jobs_by_user(
            db=db,
            user_id="all",  # 获取所有用户的Jobs
            limit=page_size,
            offset=(page - 1) * page_size
        )
        
        # 类型过滤
        if job_type:
            jobs = [job for job in jobs if job.job_type == job_type]
        
        # 状态过滤
        if status:
            jobs = [job for job in jobs if job.status == status]
        
        return {
            "jobs": [
                {
                    "job_id": job.job_id,
                    "job_type": job.job_type,
                    "status": job.status,
                    "user_id": job.user_id,
                    "created_at": job.created_at,
                    "updated_at": job.updated_at
                }
                for job in jobs
            ],
            "total": len(jobs),
            "page": page,
            "page_size": page_size
        }
        
    except PermissionDeniedException:
        raise
    except Exception as e:
        raise JobOperationException(
            internal_message=f"获取Jobs失败: {str(e)}"
        )


@router.get("/stats", summary="获取Job统计信息")
async def get_job_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取Job统计信息"""
    try:
        job_repo = JobRepository()
        
        # 获取各种状态的Job数量
        pending_jobs = await job_repo.get_jobs_by_status(db, "pending", limit=1000)
        processing_jobs = await job_repo.get_jobs_by_status(db, "processing", limit=1000)
        completed_jobs = await job_repo.get_jobs_by_status(db, "completed", limit=1000)
        failed_jobs = await job_repo.get_jobs_by_status(db, "failed", limit=1000)
        
        # 按类型统计
        kb_jobs = [job for job in pending_jobs + processing_jobs + completed_jobs + failed_jobs 
                  if job.job_type == "kb_management"]
        
        stats = {
            "total_jobs": len(pending_jobs) + len(processing_jobs) + len(completed_jobs) + len(failed_jobs),
            "by_status": {
                "pending": len(pending_jobs),
                "processing": len(processing_jobs),
                "completed": len(completed_jobs),
                "failed": len(failed_jobs)
            },
            "by_type": {
                "kb_management": len(kb_jobs)
            },
            "success_rate": len(completed_jobs) / max(1, len(completed_jobs) + len(failed_jobs))
        }
        
        return stats
        
    except Exception as e:
        raise JobOperationException(
            internal_message=f"获取统计信息失败: {str(e)}"
        )


@router.post("/{job_id}/retry", summary="重试Job")
async def retry_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """重试失败的Job"""
    try:
        job_repo = JobRepository()
        
        # 获取Job
        job = await job_repo.get_job_by_id(db, job_id)
        # 获取Job
        job = await job_repo.get_job_by_id(db, job_id)
        if not job:
            raise NotFoundException(
                resource="Job",
                resource_id=job_id,
                internal_message="Job not found"
            )
        
        # 检查权限
        if str(job.user_id) != str(current_user.id) and not current_user.is_superuser():
            raise PermissionDeniedException(
                resource="Job",
                user_message="无权限操作此Job"
            )
        
        # 检查Job状态
        if job.status != "failed":
            raise ValidationException(
                user_message="只能重试失败的Job",
                violations=[{"field": "status", "description": "Job status is not failed"}]
            )
        
        # 重置Job状态
        state_machine = JobStateMachine()
        await state_machine.transition(
            db, job_id, "pending",
            "manual_retry", None, "user"
        )
        
        # 重新启动工作流
        if job.job_type == "kb_management":
            from app.services.knowledge.kb_orchestrator import KBOrchestrator
            orchestrator = KBOrchestrator()
            await orchestrator.start_workflow(
                db=db,
                job_id=job_id,
                source_type=job.source_type,
                file_path=job.file_path,
                file_url=None,  # 需要从metadata获取
                user_id=str(job.user_id)
            )
        else:
            raise ValidationException(
                user_message=f"不支持的任务类型: {job.job_type}",
                violations=[{"field": "job_type", "description": "Unsupported job type"}]
            )
        
        return {
            "job_id": job_id,
            "status": "retrying",
            "message": "Job重试已启动"
        }
        
    except (NotFoundException, PermissionDeniedException, ValidationException):
        raise
    except Exception as e:
        raise JobOperationException(
            internal_message=f"重试Job失败: {str(e)}"
        )


@router.delete("/{job_id}", summary="删除Job")
async def delete_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除Job（仅限管理员）"""
    try:
        # 检查管理员权限
        if not current_user.is_superuser():
            raise PermissionDeniedException(
                resource="Job",
                user_message="需要管理员权限"
            )
        
        job_repo = JobRepository()
        
        # 获取Job
        job = await job_repo.get_job_by_id(db, job_id)
        if not job:
            raise NotFoundException(
                resource="Job",
                resource_id=job_id,
                internal_message="Job not found"
            )
        
        # 删除Job（级联删除相关记录）
        await db.delete(job)
        await db.commit()
        
        return {
            "job_id": job_id,
            "status": "deleted",
            "message": "Job已删除"
        }
        
    except (PermissionDeniedException, NotFoundException):
        raise
    except Exception as e:
        raise JobOperationException(
            internal_message=f"删除Job失败: {str(e)}"
        )
