"""
Webhook配置管理API路由
"""
from typing import Optional

from app.core.dependencies import get_current_user, get_db
from shared.models.database.user import User
from shared.models.schemas.webhook import (WebhookConfigCreate,
                                        WebhookConfigResponse, WebhookLogList,
                                        WebhookLogResponse,
                                        WebhookStatsResponse,
                                        WebhookTestRequest,
                                        WebhookTestResponse)
from app.repositories.webhook_repository import WebhookRepository
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

# WebhookService已迁移到API服务

router = APIRouter(tags=["Webhook管理"])


@router.post("/config", response_model=WebhookConfigResponse, summary="创建Webhook配置")
async def create_webhook_config(
    request: WebhookConfigCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建Webhook配置"""
    try:
        # TODO: 实现Webhook配置存储
        # 这里应该存储到数据库，目前返回模拟数据
        import uuid
        
        config = {
            "id": str(uuid.uuid4()),
            "webhook_url": str(request.webhook_url),
            "events": request.events,
            "enabled": request.enabled,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        }
        
        response = WebhookConfigResponse(**config)
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建Webhook配置失败: {str(e)}"
        )


@router.get("/config", response_model=WebhookConfigResponse, summary="获取Webhook配置")
async def get_webhook_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取Webhook配置"""
    try:
        # TODO: 从数据库获取用户Webhook配置
        # 目前返回模拟数据
        import uuid
        
        config = {
            "id": str(uuid.uuid4()),
            "webhook_url": "https://example.com/webhook",
            "events": ["job.completed", "job.failed"],
            "enabled": True,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        }
        
        response = WebhookConfigResponse(**config)
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取Webhook配置失败: {str(e)}"
        )


@router.get("/logs", response_model=WebhookLogList, summary="获取Webhook日志")
async def get_webhook_logs(
    job_id: Optional[str] = Query(None, description="任务ID过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取Webhook日志"""
    try:
        webhook_repo = WebhookRepository()
        
        # 获取日志
        if job_id:
            logs = await webhook_repo.get_webhook_logs(
                db=db,
                job_id=job_id,
                limit=page_size,
                offset=(page - 1) * page_size
            )
        else:
            # 获取用户相关的所有日志
            logs = await webhook_repo.get_webhook_logs(
                db=db,
                job_id=None,
                limit=page_size,
                offset=(page - 1) * page_size
            )
        
        # 构建响应
        log_responses = []
        for log in logs:
            log_responses.append(WebhookLogResponse(
                id=log.id,
                job_id=log.job_id,
                webhook_url=log.webhook_url,
                attempt_number=log.attempt_number,
                response_status_code=log.response_status_code,
                response_body=log.response_body,
                error_message=log.error_message,
                created_at=log.created_at
            ))
        
        response = WebhookLogList(
            logs=log_responses,
            total=len(log_responses),
            page=page,
            page_size=page_size
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取Webhook日志失败: {str(e)}"
        )


@router.get("/stats", response_model=WebhookStatsResponse, summary="获取Webhook统计")
async def get_webhook_stats(
    job_id: Optional[str] = Query(None, description="任务ID过滤"),
    webhook_url: Optional[str] = Query(None, description="Webhook URL过滤"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取Webhook统计信息"""
    try:
        webhook_repo = WebhookRepository()
        
        stats = await webhook_repo.get_webhook_stats(
            db=db,
            job_id=job_id,
            webhook_url=webhook_url
        )
        
        response = WebhookStatsResponse(**stats)
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取Webhook统计失败: {str(e)}"
        )


@router.post("/test", response_model=WebhookTestResponse, summary="测试Webhook")
async def test_webhook(
    request: WebhookTestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """测试Webhook连接"""
    try:
        from datetime import datetime

        from app.services.webhook.webhook_service import WebhookService
        
        webhook_service = WebhookService()
        
        # 构建测试payload
        test_payload = {
            "event": "webhook.test",
            "message": "This is a test webhook from Knowhere",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_id": str(current_user.id)
        }
        
        # 发送测试Webhook
        result = await webhook_service.send_webhook(
            job_id="test",
            webhook_url=str(request.webhook_url),
            payload=test_payload,
            attempt_number=1
        )
        
        response = WebhookTestResponse(
            success=result.get("success", False),
            status_code=result.get("status_code"),
            response_body=result.get("response_body"),
            error_message=result.get("error"),
            test_time=datetime.utcnow()
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"测试Webhook失败: {str(e)}"
        )
