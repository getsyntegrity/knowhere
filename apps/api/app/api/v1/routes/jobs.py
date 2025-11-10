"""
统一Jobs API路由（符合PRD规范）
"""

import os
import uuid
from typing import Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.core.dependencies import get_db, get_current_user_dual_auth
from app.core.constants.system import SystemConstants
from app.models.database.user import User
from app.models.schemas.job import (
    JobCreate,
    JobResponse,
    JobResult,
    JobList,
    ConfirmUploadRequest,
)
from app.repositories.job_repository import JobRepository
from app.services.storage.file_upload_service import FileUploadService
from app.services.knowledge.kb_orchestrator import KBOrchestrator
from app.core.state_machine import (
    JobStatus,
    JobStateMachine,
)

router = APIRouter(tags=["Jobs"])


# ==================== 公共工具函数 ====================


def get_supported_formats() -> str:
    """获取所有支持的文件格式字符串"""
    all_supported_extensions = []
    for category in SystemConstants.SUPPORTED_EXTENSIONS.values():
        all_supported_extensions.extend(category)
    return ", ".join(sorted(all_supported_extensions))


async def transition_to_uploaded(
    db: AsyncSession,
    job_id: str,
    job_type: str,
    trigger: str = "manual_upload_completed",
):
    """
    将任务状态转换为uploaded

    Args:
        db: 数据库会话
        job_id: 任务ID
        job_type: 任务类型
        trigger: 触发原因
    """
    state_machine = JobStateMachine()

    # 文件上传完成后，转换到pending状态
    await state_machine.transition(
        db, job_id, JobStatus.PENDING.value, trigger, None, "system"
    )


async def start_workflow_for_job(
    db: AsyncSession,
    job_id: str,
    job_type: str,
    source_type: str,
    user_id: str,
    file_path: Optional[str] = None,
    file_url: Optional[str] = None,
):
    """
    为任务启动工作流

    Args:
        db: 数据库会话
        job_id: 任务ID
        job_type: 任务类型
        source_type: 来源类型
        user_id: 用户ID
        file_path: 文件路径
        file_url: 文件URL
    """
    if job_type == "kb_management":
        orchestrator = KBOrchestrator()
        await orchestrator.start_workflow(
            db=db,
            job_id=job_id,
            source_type=source_type,
            file_path=file_path,
            file_url=file_url,
            user_id=user_id,
        )
    else:
        raise ValueError(f"不支持的任务类型: {job_type}")


def check_job_permission(job, current_user: User) -> None:
    """
    检查任务权限

    Args:
        job: 任务对象
        current_user: 当前用户

    Raises:
        HTTPException: 权限不足时抛出异常
    """
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    if str(job.user_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="无权限访问此任务"
        )


def create_job_response(
    job_id: str,
    job,
    source_type: str,
    data_id: Optional[str],
    upload_url: Optional[str] = None,
    upload_headers: Optional[dict] = None,
    expires_in: Optional[int] = None,
) -> JobResponse:
    """
    创建JobResponse对象

    Args:
        job_id: 任务ID
        job: 任务对象
        source_type: 来源类型
        data_id: 数据ID
        upload_url: 上传URL（仅文件模式）
        upload_headers: 上传头（仅文件模式）
        expires_in: 过期时间（仅文件模式）

    Returns:
        JobResponse: 任务响应对象
    """
    return JobResponse(
        job_id=job_id,
        status=job.status,
        source_type=source_type,
        data_id=data_id,
        created_at=job.created_at,
        upload_url=upload_url,
        upload_headers=upload_headers,
        expires_in=expires_in,
    )


def validate_file_type(file_name: str) -> bool:
    """
    验证文件类型是否支持所有SUPPORTED_EXTENSIONS格式

    Args:
        file_name: 文件名

    Returns:
        bool: 是否支持的文件类型
    """
    if not file_name:
        return False

    file_extension = os.path.splitext(file_name)[1].lower()

    # 支持所有文件类型
    all_supported_extensions = []
    for category in SystemConstants.SUPPORTED_EXTENSIONS.values():
        all_supported_extensions.extend(category)

    return file_extension in all_supported_extensions


@router.post("", response_model=JobResponse, summary="创建解析任务")
@router.post("/", include_in_schema=False)
async def create_job(
    request: JobCreate,
    current_user: User = Depends(get_current_user_dual_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    创建解析任务 - 符合PRD第5.1.3节规范
    """
    try:
        # 验证参数
        if request.source_type == "file" and not request.file_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_type为file时，file_name为必填参数",
            )
        if request.source_type == "url" and not request.source_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_type为url时，source_url为必填参数",
            )

        # 验证文件类型
        if request.source_type == "file" and not validate_file_type(request.file_name):
            supported_formats = get_supported_formats()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的文件类型。仅支持以下格式：{supported_formats}",
            )
        elif request.source_type == "url":
            # 验证URL文件类型
            parsed_url = urlparse(request.source_url)
            url_file_name = (
                os.path.basename(parsed_url.path) or f"url_file_{uuid.uuid4().hex[:8]}"
            )
            if not validate_file_type(url_file_name):
                supported_formats = get_supported_formats()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"URL文件类型不支持。仅支持以下格式：{supported_formats}",
                )

        # 生成job_id
        job_id = f"job_{uuid.uuid4().hex[:12]}"

        job_type = "kb_management"

        # 1. 获取用户配置（1天缓存）
        from app.services.redis import RedisServiceFactory
        from app.services.redis.user_redis_service import UserRedisService
        from app.services.user.user_config_service import UserConfigService
        import json
        
        redis_service = RedisServiceFactory.get_service()
        user_redis_service = UserRedisService(redis_service)
        
        user_config = await user_redis_service.get_user_config(str(current_user.id))
        if not user_config:
            user_config_str = UserConfigService.init_user(str(current_user.id))
            user_config = json.loads(user_config_str)
            await user_redis_service.save_user_config(str(current_user.id), user_config)
    
        logger.debug(f"user_config: {user_config}")
        
        # 2. 构建job_metadata（包含user_config）
        from app.models.schemas.job_metadata import JobMetadataHelper
        job_metadata = JobMetadataHelper.create_from_request(request, user_config)

        if request.source_type == "file":
            # 文件上传模式 - 申请萝卜坑
            file_extension = os.path.splitext(request.file_name)[1]
            s3_key = f"uploads/{job_id}{file_extension}"
            job_metadata["source_file_name"] = request.file_name
            job_metadata["source_type"] = "file"

            # 创建状态为waiting-file的job
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
                initial_state="waiting-file",
            )

            if not job:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="创建任务失败",
                )

            # 生成预签名URL
            upload_service = FileUploadService()
            upload_info = await upload_service.generate_upload_url(
                job_id, file_extension
            )

            # 更新job的s3_key
            await job_repo.update_job_s3_key(db, job_id, s3_key)

            # 3. 保存到Redis（2小时缓存）
            from app.services.redis.job_metadata_service import JobMetadataService
            metadata_service = JobMetadataService(redis_service)
            await metadata_service.save_metadata(job_id, job_metadata)

            # 构建响应
            response = create_job_response(
                job_id=job_id,
                job=job,
                source_type="file",
                data_id=request.data_id,
                upload_url=upload_info["upload_url"],
                upload_headers=upload_info["upload_headers"],
                expires_in=upload_info["expires_in"],
            )

            return response

        else:
            # URL模式 - 创建Job后异步下载和上传
            try:
                # 解析URL获取文件名和扩展名
                parsed_url = urlparse(request.source_url)
                source_file_name = os.path.basename(parsed_url.path) or f"url_file_{uuid.uuid4().hex[:8]}"
                
                # 提前验证文件类型（快速失败）
                if not validate_file_type(source_file_name):
                    supported_formats = get_supported_formats()
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"URL文件类型不支持。仅支持以下格式：{supported_formats}",
                    )
                
                # 生成S3键（在API层面确定，避免异步任务中再更新）
                file_extension = os.path.splitext(source_file_name)[1] or ".pdf"
                s3_key = f"uploads/{job_id}{file_extension}"
                
                job_metadata.update(
                    {
                        "source_file_name": source_file_name,
                        "source_url": request.source_url,
                        "source_type": "url",
                    }
                )

                # 创建状态为pending的job（文件将异步上传）
                job_repo = JobRepository()
                job = await job_repo.create_job(
                    db=db,
                    job_id=job_id,
                    user_id=str(current_user.id),
                    job_type=job_type,
                    source_type="url",
                    file_path=None,
                    webhook_url=request.webhook.url if request.webhook else None,
                    metadata=job_metadata,
                    initial_state=JobStatus.WAITING_FILE.value,  # 使用pending状态
                    s3_key=s3_key,  # 预设s3_key
                )

                if not job:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="创建任务失败",
                    )

                # 保存到Redis（2小时缓存）
                from app.services.redis.job_metadata_service import JobMetadataService
                metadata_service = JobMetadataService(redis_service)
                await metadata_service.save_metadata(job_id, job_metadata)

                # 异步启动URL文件下载和上传任务
                from app.core.tasks.kb_tasks import upload_url_file_task
                upload_url_file_task.apply_async(
                    args=[job_id, request.source_url, str(current_user.id)],
                    kwargs={'job_type': job_type}
                )

                # 构建响应
                response = create_job_response(
                    job_id=job_id,
                    job=job,
                    source_type="url",
                    data_id=request.data_id,
                )

                return response

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"URL任务创建失败: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"URL任务创建失败: {str(e)}",
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建任务失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建任务失败: {str(e)}",
        )


@router.get("/page", response_model=JobList, summary="获取任务列表")
async def list_jobs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    job_status: Optional[str] = Query(None, description="状态过滤"),
    job_type: Optional[str] = Query(None, description="任务类型过滤"),
    current_user: User = Depends(get_current_user_dual_auth),
    db: AsyncSession = Depends(get_db),
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
            offset=(page - 1) * page_size,
        )

        # 类型过滤
        if job_type:
            jobs = [job for job in jobs if job.job_type == job_type]

        # 状态过滤
        if job_status:
            jobs = [
                job
                for job in jobs
                if job.status == job_status
            ]

        # 构建响应
        job_responses = []
        upload_service = FileUploadService()
        from app.services.redis import RedisServiceFactory
        from app.models.schemas.job_metadata import JobMetadataHelper
        
        redis_service = RedisServiceFactory.get_service()
        for job in jobs:
            # 使用统一接口获取job_metadata
            job_metadata = await job_repo.get_job_metadata(db, job.job_id, redis_service)
            job_result = job.job_result
            status_for_api = job.status
            
            result_url = None
            result = None
            result_url_expires_at = job.created_at  # 默认使用创建时间
            
            if job_result and job_result.result_s3_key:
                result_url_info = await upload_service.generate_download_url(
                    job_result.result_s3_key
                )
                result_url = result_url_info["download_url"]
                
                # 从 inline_payload 获取 checksum（只包含 checksum）
                if job_result.inline_payload:
                    result = job_result.inline_payload
                
                # 处理result_url_expires_at字段
                if result_url:
                    from datetime import datetime, timedelta
                    expires_in = result_url_info.get("expires_in", 3600)
                    result_url_expires_at = datetime.now() + timedelta(seconds=expires_in)

            job_responses.append(
                JobResult(
                    job_id=job.job_id,
                    status=status_for_api,
                    source_type=job.source_type,
                    data_id=JobMetadataHelper.get_field(job_metadata, "data_id"),
                    created_at=job.created_at,
                    progress=None,  # 任务列表不显示详细进度
                    error={"message": job.error_message} if job.error_message else None,
                    result=result,
                    result_url=result_url,
                    result_url_expires_at=result_url_expires_at,
                )
            )

        response = JobList(
            jobs=job_responses, total=len(job_responses), page=page, page_size=page_size
        )

        return response

    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务列表失败: {str(e)}",
        )


@router.get(
    "/{job_id}", response_model=JobResult, summary="获取任务结果"
)
async def get_job_result(
    job_id: str,
    response: Response,
    current_user: User = Depends(get_current_user_dual_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    获取任务结果 - 符合PRD第5.1.3节规范
    """
    try:
        # 速率限制检查
        from app.services.redis import RedisServiceFactory
        from app.services.redis.rate_limit_service import RateLimitService

        redis_service = RedisServiceFactory.get_service()
        rate_limit_service = RateLimitService(redis_service)

        rate_limit_info = await rate_limit_service.check_rate_limit(
            str(current_user.id), "get_job_result"
        )

        # 设置响应头
        response.headers["RateLimit-Limit"] = str(rate_limit_info["limit"])
        response.headers["RateLimit-Remaining"] = str(rate_limit_info["remaining"])
        response.headers["RateLimit-Reset"] = str(rate_limit_info["reset"])

        # 如果超过限制，返回429错误
        if not rate_limit_info["allowed"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="请求过于频繁，请稍后再试",
            )

        job_repo = JobRepository()

        # 获取Job并检查权限
        job = await job_repo.get_job_by_id(db, job_id)
        check_job_permission(job, current_user)

        status_for_api = job.status

        # 获取进度信息，当任务状态为running时，从Redis获取详细进度信息
        progress = None
        if status_for_api == "running":
            # TODO：从Redis获取详细进度信息，并转换为progress格式
            # from app.services.redis import RedisServiceFactory
            # redis_service = RedisServiceFactory.get_service()
            # from app.utils.redis_key_builder import redis_key_builder

            # progress_key = redis_key_builder.task_progress(job_id)
            # progress = await redis_service.hgetall(progress_key)
            progress = {"total_pages": 10, "processed_pages": 5}

        # 使用统一接口获取job_metadata
        from app.services.redis import RedisServiceFactory
        from app.models.schemas.job_metadata import JobMetadataHelper
        
        redis_service = RedisServiceFactory.get_service()
        job_metadata = await job_repo.get_job_metadata(db, job_id, redis_service)

        # 结果交付信息
        job_result = job.job_result
        result_url = None
        result = None
        result_url_expires_at = job.created_at  # 默认使用创建时间
        
        if job_result and job_result.result_s3_key:
            upload_service = FileUploadService()
            result_url_info = await upload_service.generate_download_url(
                job_result.result_s3_key
            )
            result_url = result_url_info["download_url"]
            expires_in = result_url_info["expires_in"]
            
            # 从 inline_payload 获取 checksum 和 statistics
            if job_result.inline_payload:
                result = job_result.inline_payload
            
            # 处理result_url_expires_at字段
            if result_url:
                from datetime import datetime, timedelta
                result_url_expires_at = datetime.now() + timedelta(seconds=expires_in)

        response_data = JobResult(
            job_id=job.job_id,
            status=status_for_api,
            source_type=job.source_type,
            data_id=JobMetadataHelper.get_field(job_metadata, "data_id"),
            created_at=job.created_at,
            progress=progress,
            error={"message": job.error_message} if job.error_message else None,
            result=result,
            result_url=result_url,
            result_url_expires_at=result_url_expires_at,
        )

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务结果失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务结果失败: {str(e)}",
        )


@router.post(
    "/{job_id}/confirm-upload",
    response_model=dict,
    summary="确认文件上传",
)
async def confirm_upload(
    job_id: str,
    request: Optional[ConfirmUploadRequest] = None,
    current_user: User = Depends(get_current_user_dual_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    确认文件上传完成 - 备用机制
    """
    try:
        job_repo = JobRepository()

        # 获取Job并检查权限
        job = await job_repo.get_job_by_id(db, job_id)
        check_job_permission(job, current_user)

        # 检查任务状态
        logger.info(f"Confirm upload - Job {job_id} current status: {job.status}")
        if job.status not in [JobStatus.PENDING.value, JobStatus.WAITING_FILE.value]:
            # 如果已经被webhook触发，返回成功（幂等性）
            logger.info(f"Job {job_id} already processed, status: {job.status}")
            return {"message": "任务状态已更新"}

        # 验证S3文件存在
        if not job.s3_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="任务缺少S3键信息"
            )

        upload_service = FileUploadService()
        file_info = await upload_service.verify_s3_file_exists(job.s3_key)

        if not file_info.get("exists"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="S3文件不存在，请先上传文件",
            )

        # 更新任务状态
        await transition_to_uploaded(
            db, job_id, job.job_type, "manual_upload_completed"
        )

        # 触发任务处理
        await start_workflow_for_job(
            db=db,
            job_id=job_id,
            job_type=job.job_type,
            source_type="file",
            user_id=str(current_user.id),
        )

        return {"message": "文件上传确认成功，任务已开始处理"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"确认上传失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"确认上传失败: {str(e)}",
        )
