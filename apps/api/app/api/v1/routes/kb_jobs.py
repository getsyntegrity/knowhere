"""
知识库任务API路由
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, get_current_user, get_redis_service
from app.core.response.ResponseResult import ResponseResult
from app.models.database.user import User
from app.models.schemas.kb_job import (
    KBJobCreate,
    KBJobResponse,
    KBJobStatus,
    KBJobList,
    KBUploadResponse,
    KBDownloadResponse
)
from app.repositories.job_repository import JobRepository
from app.services.storage.file_upload_service import FileUploadService
from app.services.knowledge.kb_orchestrator import KBOrchestrator
from app.core.state_machine import KBManagementState
from app.utils.FileDownUpUtils import s3_upload_file
from app.core.config import settings
import uuid

router = APIRouter(tags=["Knowledge Base Jobs"])


@router.post("/jobs", response_model=ResponseResult[KBJobResponse], summary="创建知识库任务")
async def create_kb_job(
    file: Optional[UploadFile] = File(None, description="要上传的文件"),
    file_url: Optional[str] = Form(None, description="文件URL"),
    webhook_url: Optional[str] = Form(None, description="Webhook URL"),
    metadata: Optional[str] = Form(None, description="额外元数据（JSON字符串）"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建知识库任务 - 支持文件上传和URL下载"""
    try:
        import json
        import tempfile
        import os
        
        # 验证参数：必须提供file或file_url之一，不能同时提供
        if not file and not file_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="必须提供文件上传或文件URL"
            )
        if file and file_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能同时提供文件上传和文件URL"
            )
        
        # 解析元数据
        job_metadata = {}
        if metadata:
            try:
                job_metadata = json.loads(metadata)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="元数据格式错误，必须是有效的JSON字符串"
                )
        
        # 确定源类型和文件路径
        source_type = "direct_upload" if file else "url"
        file_path = None
        temp_file_path = None
        
        if file:
            # 处理文件上传
            temp_dir = getattr(settings, 'TMP_PATH', '/tmp')
            os.makedirs(temp_dir, exist_ok=True)
            
            # 生成临时文件路径
            temp_filename = f"temp_{uuid.uuid4().hex}_{file.filename}"
            temp_file_path = os.path.join(temp_dir, temp_filename)
            
            # 保存上传的文件
            with open(temp_file_path, "wb") as f:
                content = await file.read()
                f.write(content)
            
            file_path = temp_file_path
            
            # 添加文件信息到元数据
            job_metadata.update({
                "original_filename": file.filename,
                "file_size": file.size,
                "content_type": file.content_type
            })
        
        # 获取用户配置
        from app.services.redis.user_redis_service import UserRedisService
        redis_service = await get_redis_service()
        user_redis_service = UserRedisService(redis_service)
        user_config = await user_redis_service.get_user_config(str(current_user.id))
        
        if not user_config:
            # 初始化用户配置
            from app.services.user.user_config_service import UserConfigService
            user_dic_str = UserConfigService.init_user(str(current_user.id))
            user_config = json.loads(user_dic_str) if isinstance(user_dic_str, str) else user_dic_str
            await user_redis_service.save_user_config(str(current_user.id), user_config)
        
        # 验证目录存在性
        kb_dir = job_metadata.get("kb_dir", "默认目录")
        from app.repositories.knowledge_base_repository import get_directories_by_user
        user_directories = await get_directories_by_user(db, str(current_user.id))
        
        # 检查目录是否存在
        directory_exists = any(dir.title == kb_dir for dir in user_directories)
        if not directory_exists:
            # 如果目录不存在，创建默认目录
            from app.models.schemas.files import FileDirectoryCreateDto
            from app.repositories.knowledge_base_repository import create_directory
            
            create_request = FileDirectoryCreateDto(
                title=kb_dir,
                parent_id=None,
                user_id=str(current_user.id)
            )
            
            success = await create_directory(db, create_request)
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"创建目录失败: {kb_dir}"
                )
        
        # 构建Job元数据，包含用户配置
        full_job_metadata = {
            "user_config": user_config,
            "request_metadata": job_metadata,
            "doc_type": job_metadata.get("doc_type", "auto"),
            "smart_title_parse": job_metadata.get("smart_title_parse", True),
            "summary_image": job_metadata.get("summary_image", True),
            "summary_table": job_metadata.get("summary_table", True),
            "summary_txt": job_metadata.get("summary_txt", True),
            "add_frag_desc": job_metadata.get("add_frag_desc", ""),
            "kb_dir": kb_dir,
        }
        
        # 创建Job
        job_repo = JobRepository()
        job = await job_repo.create_job(
            db=db,
            user_id=str(current_user.id),
            job_type="kb_management",
            source_type=source_type,
            file_path=file_path,
            webhook_url=webhook_url,
            metadata=full_job_metadata
        )
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="创建任务失败"
            )
        
        # 启动工作流
        orchestrator = KBOrchestrator()
        await orchestrator.start_workflow(
            db=db,
            job_id=job.job_id,
            source_type=source_type,
            file_path=file_path,
            file_url=file_url,
            user_id=str(current_user.id)
        )
        
        # 构建响应
        response = KBJobResponse(
            job_id=job.job_id,
            status=job.status,
            current_state=job.current_state,
            source_type=job.source_type,
            file_path=job.file_path,
            s3_key=job.s3_key,
            result_s3_key=job.result_s3_key,
            webhook_url=job.webhook_url,
            webhook_enabled=job.webhook_enabled,
            error_message=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at
        )
        
        return ResponseResult.ok_data(data=response)
        
    except HTTPException:
        raise
    except Exception as e:
        # 如果出错，清理临时文件
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建知识库任务失败: {str(e)}"
        )




@router.get("/jobs/{job_id}", response_model=ResponseResult[KBJobStatus], summary="获取知识库任务状态")
async def get_kb_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取知识库任务状态"""
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
        
        # 构建下载链接（如果任务完成）
        download_url = None
        if job.status == "completed" and job.result_s3_key:
            upload_service = FileUploadService()
            download_url = await upload_service.generate_download_url(job.result_s3_key)
        
        response = KBJobStatus(
            job_id=job.job_id,
            status=job.status,
            current_state=job.current_state,
            progress=progress,
            error_message=job.error_message,
            result_s3_key=job.result_s3_key,
            download_url=download_url,
            created_at=job.created_at,
            updated_at=job.updated_at
        )
        
        return ResponseResult.ok_data(data=response)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务状态失败: {str(e)}"
        )


@router.get("/jobs/{job_id}/download", response_model=ResponseResult[KBDownloadResponse], summary="下载知识库结果")
async def download_kb_result(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """下载知识库结果"""
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
        if job.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="任务尚未完成"
            )
        
        if not job.result_s3_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="结果文件不存在"
            )
        
        # 生成下载链接
        upload_service = FileUploadService()
        download_url = await upload_service.generate_download_url(job.result_s3_key)
        
        # 获取文件信息
        file_info = await upload_service.get_file_info(job.result_s3_key)
        
        response = KBDownloadResponse(
            download_url=download_url,
            expires_in=3600,  # 1小时过期
            file_size=file_info.get("size") if file_info else None,
            content_type=file_info.get("content_type") if file_info else None
        )
        
        return ResponseResult.ok_data(data=response)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成下载链接失败: {str(e)}"
        )


@router.get("/jobs", response_model=ResponseResult[KBJobList], summary="获取知识库任务列表")
async def list_kb_jobs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: Optional[str] = Query(None, description="状态过滤"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取知识库任务列表"""
    try:
        job_repo = JobRepository()
        
        # 获取任务列表
        jobs = await job_repo.get_jobs_by_user(
            db=db,
            user_id=str(current_user.id),
            limit=page_size,
            offset=(page - 1) * page_size
        )
        
        # 过滤知识库任务
        kb_jobs = [job for job in jobs if job.job_type == "kb_management"]
        
        # 状态过滤
        if status:
            kb_jobs = [job for job in kb_jobs if job.status == status]
        
        # 构建响应
        job_responses = []
        for job in kb_jobs:
            job_responses.append(KBJobResponse(
                job_id=job.job_id,
                status=job.status,
                current_state=job.current_state,
                source_type=job.source_type,
                file_path=job.file_path,
                s3_key=job.s3_key,
                result_s3_key=job.result_s3_key,
                webhook_url=job.webhook_url,
                webhook_enabled=job.webhook_enabled,
                error_message=job.error_message,
                created_at=job.created_at,
                updated_at=job.updated_at
            ))
        
        response = KBJobList(
            jobs=job_responses,
            total=len(kb_jobs),
            page=page,
            page_size=page_size
        )
        
        return ResponseResult.ok_data(data=response)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务列表失败: {str(e)}"
        )


@router.post("/jobs/{job_id}/retry", response_model=ResponseResult[dict], summary="重试知识库任务")
async def retry_kb_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """重试知识库任务"""
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
        if job.status not in ["failed", "cancelled"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只有失败或已取消的任务才能重试"
            )
        
        # 重新启动工作流
        orchestrator = KBOrchestrator()
        await orchestrator.start_workflow(
            db=db,
            job_id=job.job_id,
            source_type=job.source_type,
            file_path=job.file_path,
            file_url=job.file_path,  # 这里可能需要根据实际情况调整
            user_id=str(current_user.id)
        )
        
        return ResponseResult.build_msg(200, "任务重试成功")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重试任务失败: {str(e)}"
        )


@router.post("/jobs/{job_id}/cancel", response_model=ResponseResult[dict], summary="取消知识库任务")
async def cancel_kb_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """取消知识库任务"""
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
        if job.status not in ["pending", "running"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只有等待中或运行中的任务才能取消"
            )
        
        # 更新任务状态为已取消
        await job_repo.update_job_status(db, job_id, "cancelled", "任务被用户取消")
        
        return ResponseResult.build_msg(200, "任务已取消")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"取消任务失败: {str(e)}"
        )
