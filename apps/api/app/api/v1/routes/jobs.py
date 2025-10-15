"""
统一Jobs API路由（符合PRD规范）
"""
import os
import uuid
from typing import Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.dependencies import get_db, get_current_user
from app.core.response.ResponseResult import ResponseResult
from app.models.database.user import User
from app.models.schemas.job import (
    JobCreate,
    JobResponse,
    JobStatus,
    JobList,
    ConfirmUploadRequest
)
from app.repositories.job_repository import JobRepository
from app.services.storage.file_upload_service import FileUploadService
from app.services.knowledge.kb_orchestrator import KBOrchestrator
from app.services.table_fill.orchestrator import TableFillOrchestrator
from app.core.state_machine import KBManagementState, TableFillState, get_prd_status_from_state

router = APIRouter(tags=["Jobs"])


def infer_job_type(parsing_params: Optional[dict]) -> str:
    """
    根据parsing_params推断job_type
    
    Args:
        parsing_params: 解析参数
        
    Returns:
        str: job_type ("kb_management" 或 "table_fill")
    """
    if parsing_params and parsing_params.get("kb_dir"):
        return "kb_management"
    return "table_fill"


@router.post("", response_model=ResponseResult[JobResponse], summary="创建解析任务")
@router.post("/", include_in_schema=False)
async def create_job(
    request: JobCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    创建解析任务 - 符合PRD第5.1.3节规范
    """
    try:
        # 验证参数
        if request.source_type == "file" and not request.file_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_type为file时，file_name为必填参数"
            )
        if request.source_type == "url" and not request.source_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_type为url时，source_url为必填参数"
            )
        
        # 生成job_id
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        
        # 推断job_type
        job_type = infer_job_type(request.parsing_params)
        
        # 构建job元数据
        job_metadata = {
            "request_metadata": request.parsing_params or {},
            "data_id": request.data_id,
            "webhook": request.webhook.dict() if request.webhook else None,
            "result_mode": request.result_mode or "auto"
        }
        
        # 设置用户默认目录信息
        if request.parsing_params and "kb_dir" in request.parsing_params:
            job_metadata["kb_dir"] = request.parsing_params["kb_dir"]
        else:
            # 如果没有指定目录，使用默认目录
            job_metadata["kb_dir"] = "默认目录"
        
        if request.source_type == "file":
            # 文件上传模式 - 申请萝卜坑
            file_extension = os.path.splitext(request.file_name)[1]
            s3_key = f"uploads/{job_id}{file_extension}"
            job_metadata["source_file_name"] = request.file_name
            job_metadata["source_type"] = "file"
            
            # 创建状态为waiting_for_upload的job
            job_repo = JobRepository()
            job = await job_repo.create_job(
                db=db,
                job_id=job_id,
                user_id=str(current_user.id),
                job_type=job_type,
                source_type="file",
                file_path=None,  # 文件还未上传
                webhook_url=request.webhook.url if request.webhook else None,
                metadata=job_metadata,
                initial_state="uploading"
            )
            
            if not job:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="创建任务失败"
                )
            
            # 生成预签名URL
            upload_service = FileUploadService()
            upload_info = await upload_service.generate_upload_url(job_id, file_extension)
            
            # 更新job的s3_key
            await job_repo.update_job_s3_key(db, job_id, s3_key)
            
            # 构建响应
            response = JobResponse(
                job_id=job_id,
                status=get_prd_status_from_state(job.current_state),
                source_type="file",
                data_id=request.data_id,
                created_at=job.created_at,
                result_mode=request.result_mode or "auto",
                upload_url=upload_info["upload_url"],
                upload_headers=upload_info["upload_headers"],
                expires_in=upload_info["expires_in"]
            )
            
            return ResponseResult.ok_data(data=response)
            
        else:
            # URL模式 - 直接处理
            job_repo = JobRepository()
            parsed_url = urlparse(request.source_url)
            source_file_name = os.path.basename(parsed_url.path) or f"{job_id}"
            job_metadata["source_file_name"] = source_file_name
            job_metadata["source_url"] = request.source_url
            job_metadata["source_type"] = "url"
            job = await job_repo.create_job(
                db=db,
                job_id=job_id,
                user_id=str(current_user.id),
                job_type=job_type,
                source_type="url",
                file_path=None,
                webhook_url=request.webhook.url if request.webhook else None,
                metadata=job_metadata
            )
            
            if not job:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="创建任务失败"
                )
            
            # 启动工作流
            if job_type == "kb_management":
                orchestrator = KBOrchestrator()
                await orchestrator.start_workflow(
                    db=db,
                    job_id=job_id,
                    source_type="url",
                    file_path=None,
                    file_url=request.source_url,
                    user_id=str(current_user.id)
                )
            else:
                orchestrator = TableFillOrchestrator()
                await orchestrator.start_workflow(
                    db=db,
                    job_id=job_id,
                    source_type="url",
                    file_path=None,
                    file_url=request.source_url,
                    user_id=str(current_user.id)
                )
            
            # 构建响应
            response = JobResponse(
                job_id=job_id,
                status=get_prd_status_from_state(job.current_state),
                source_type="url",
                data_id=request.data_id,
                created_at=job.created_at,
                result_mode=request.result_mode or "auto"
            )
            
            return ResponseResult.ok_data(data=response)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建任务失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建任务失败: {str(e)}"
        )


@router.get("/page", response_model=ResponseResult[JobList], summary="获取任务列表")
async def list_jobs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    job_status: Optional[str] = Query(None, description="状态过滤"),
    job_type: Optional[str] = Query(None, description="任务类型过滤"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取任务列表
    """
    try:
        job_repo = JobRepository()
        
        # 获取任务列表
        jobs = await job_repo.get_jobs_by_user(
            db=db,
            user_id=str(current_user.id),
            limit=page_size,
            offset=(page - 1) * page_size
        )
        
        # 类型过滤
        if job_type:
            jobs = [job for job in jobs if job.job_type == job_type]
        
        # 状态过滤
        if job_status:
            jobs = [job for job in jobs if get_prd_status_from_state(job.current_state) == job_status]
        
        # 构建响应
        job_responses = []
        upload_service = FileUploadService()
        for job in jobs:
            job_metadata = job.job_metadata or {}
            job_result = job.job_result
            status_for_api = get_prd_status_from_state(job.current_state)
            result_mode = job_result.delivery_mode if job_result else job_metadata.get("result_mode", "auto")
            inline_result = job_result.inline_payload if job_result and job_result.delivery_mode == "inline" else None
            result_url = None
            if job_result and job_result.delivery_mode == "url" and job_result.result_s3_key:
                result_url = await upload_service.generate_download_url(job_result.result_s3_key)

            result_metadata = job_result.document_metadata if job_result else None

            job_responses.append(JobResponse(
                job_id=job.job_id,
                status=status_for_api,
                source_type=job.source_type,
                data_id=job_metadata.get("data_id"),
                created_at=job.created_at,
                result_mode=result_mode,
                result=inline_result,
                result_url=result_url,
                result_metadata=result_metadata,
                error={"message": job.error_message} if job.error_message else None
            ))
        
        response = JobList(
            jobs=job_responses,
            total=len(job_responses),
            page=page,
            page_size=page_size
        )
        
        return ResponseResult.ok_data(data=response)
        
    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务列表失败: {str(e)}"
        )


@router.get("/{job_id}", response_model=ResponseResult[JobStatus], summary="获取任务状态")
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取任务状态 - 符合PRD第5.1.3节规范
    """
    try:
        job_repo = JobRepository()
        
        # 获取Job
        job = await job_repo.get_job_by_id(db, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="任务不存在"
            )
        
        # 检查权限
        if str(job.user_id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限访问此任务"
            )
        
        # 获取进度信息
        progress = None
        if job.current_state and job.current_state != "pending":
            # 从Redis获取详细进度信息
            from app.services.redis import RedisServiceFactory
            redis_service = RedisServiceFactory.get_service()
            from app.utils.redis_key_builder import redis_key_builder
            
            progress_key = redis_key_builder.task_progress(job_id)
            progress = await redis_service.hgetall(progress_key)
        
        status_for_api = get_prd_status_from_state(job.current_state)

        job_metadata = job.job_metadata or {}

        # 结果交付信息
        job_result = job.job_result
        result_mode = job_result.delivery_mode if job_result else job_metadata.get("result_mode", "auto")
        inlined_result = job_result.inline_payload if job_result and job_result.delivery_mode == "inline" else None
        result_url = None
        if job_result and job_result.delivery_mode == "url" and job_result.result_s3_key:
            upload_service = FileUploadService()
            result_url = await upload_service.generate_download_url(job_result.result_s3_key)

        # 构建响应
        result_metadata = job_result.document_metadata if job_result else None

        response = JobStatus(
            job_id=job.job_id,
            status=status_for_api,
            source_type=job.source_type,
            data_id=job.job_metadata.get("data_id") if job.job_metadata else None,
            created_at=job.created_at,
            updated_at=job.updated_at,
            current_state=job.current_state,
            progress=progress,
            error={"message": job.error_message} if job.error_message else None,
            result=inlined_result,
            result_url=result_url,
            result_mode=result_mode,
            result_metadata=result_metadata,
            file_path=job.file_path,
            s3_key=job.s3_key,
            webhook_url=job.webhook_url,
            webhook_enabled=job.webhook_enabled
        )
        
        return ResponseResult.ok_data(data=response)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务状态失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务状态失败: {str(e)}"
        )


@router.post("/{job_id}/confirm-upload", response_model=ResponseResult[dict], summary="确认文件上传")
async def confirm_upload(
    job_id: str,
    request: Optional[ConfirmUploadRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    确认文件上传完成 - 备用机制
    """
    try:
        job_repo = JobRepository()
        
        # 获取Job
        job = await job_repo.get_job_by_id(db, job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="任务不存在"
            )
        
        # 检查权限
        if str(job.user_id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限访问此任务"
            )
        
        # 检查任务状态
        if get_prd_status_from_state(job.current_state) != "waiting_for_upload":
            # 如果已经被webhook触发，返回成功（幂等性）
            return ResponseResult.ok_data(data={"message": "任务状态已更新"})
        
        # 验证S3文件存在
        if not job.s3_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="任务缺少S3键信息"
            )
        
        upload_service = FileUploadService()
        file_info = await upload_service.verify_s3_file_exists(job.s3_key)
        
        if not file_info.get("exists"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="S3文件不存在，请先上传文件"
            )
        
        # 更新任务状态
        from app.core.state_machine import JobStateMachine
        state_machine = JobStateMachine()
        
        if job.job_type == "kb_management":
            await state_machine.transition(db, job_id, KBManagementState.UPLOADED.value)
        else:
            await state_machine.transition(db, job_id, TableFillState.UPLOADED.value)
        
        # 触发任务处理
        if job.job_type == "kb_management":
            orchestrator = KBOrchestrator()
            await orchestrator.start_workflow(
                db=db,
                job_id=job_id,
                source_type="file",
                file_path=None,
                file_url=None,
                user_id=str(current_user.id)
            )
        else:
            orchestrator = TableFillOrchestrator()
            await orchestrator.start_workflow(
                db=db,
                job_id=job_id,
                source_type="file",
                file_path=None,
                file_url=None,
                user_id=str(current_user.id)
            )
        
        return ResponseResult.ok_data(data={"message": "文件上传确认成功，任务已开始处理"})
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"确认上传失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"确认上传失败: {str(e)}"
        )
