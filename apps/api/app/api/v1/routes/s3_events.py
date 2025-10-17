"""
S3事件Webhook路由
"""
import json
import os
import hmac
import hashlib
import base64
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, status, Request, Header
from loguru import logger

from app.core.response.ResponseResult import ResponseResult
from app.models.schemas.s3_event import S3Event
from app.repositories.job_repository import JobRepository
from app.services.storage.file_upload_service import FileUploadService
from app.services.knowledge.kb_orchestrator import KBOrchestrator
from app.services.table_fill.orchestrator import TableFillOrchestrator
from app.core.state_machine import KBManagementState, TableFillState, get_prd_status_from_state
from app.core.database import get_db_context

router = APIRouter(tags=["Internal"])


def verify_sns_signature(request_body: bytes, signature: str, message: str) -> bool:
    """
    验证SNS消息签名
    
    Args:
        request_body: 请求体
        signature: 签名
        message: 消息内容
        
    Returns:
        bool: 验证是否通过
    """
    try:
        # 这里简化处理，实际应该使用AWS SDK验证
        # 在生产环境中应该实现完整的SNS签名验证
        return True
    except Exception as e:
        logger.error(f"SNS签名验证失败: {e}")
        return False


def verify_minio_signature(auth_token: str, expected_token: str) -> bool:
    """
    验证MinIO webhook签名
    
    Args:
        auth_token: 请求中的认证token
        expected_token: 期望的token
        
    Returns:
        bool: 验证是否通过
    """
    if not expected_token:
        return True  # 如果没有配置token，跳过验证
    
    return auth_token == expected_token


def extract_job_id_from_s3_key(s3_key: str) -> str:
    """
    从S3键中提取job_id
    
    Args:
        s3_key: S3键，格式为 uploads/{job_id}.ext
        
    Returns:
        str: job_id
    """
    if not s3_key.startswith("uploads/"):
        return None
    
    # 移除前缀并提取文件名（不含扩展名）
    filename = s3_key[8:]  # 移除 "uploads/" 前缀
    job_id = os.path.splitext(filename)[0]
    
    return job_id


@router.get("/s3-events", response_model=ResponseResult[dict], summary="S3事件Webhook GET")
async def handle_s3_events_get(
    request: Request,
    x_amz_sns_message_type: str = Header(None, alias="x-amz-sns-message-type"),
    x_minio_auth_token: str = Header(None, alias="x-minio-auth-token"),
    authorization: str = Header(None)
):
    """
    处理S3事件通知GET请求 - 主要用于SNS订阅确认
    """
    logger.info(f"======== S3事件GET请求 =========")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Client IP: {request.client.host}")
    
    # 检查是否是SNS订阅确认请求
    if x_amz_sns_message_type == "SubscriptionConfirmation":
        logger.info("收到SNS订阅确认请求")
        return ResponseResult.ok_data(data={"message": "SNS订阅确认成功"})
    
    return ResponseResult.ok_data(data={"message": "GET请求处理完成"})


@router.post("/s3-events", response_model=ResponseResult[dict], summary="S3事件Webhook POST")
async def handle_s3_events(
    request: Request,
    x_amz_sns_message_type: str = Header(None, alias="x-amz-sns-message-type"),
    x_minio_auth_token: str = Header(None, alias="x-minio-auth-token"),
    authorization: str = Header(None)
):
    """
    处理S3事件通知POST请求 - 支持AWS SNS和MinIO
    """
    logger.info(f"======== S3事件请求 =========")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Client IP: {request.client.host}")
    try:
        # 获取请求体
        body = await request.body()
        
        # 判断事件来源
        if x_amz_sns_message_type:
            # AWS SNS事件
            await handle_sns_event(body)
        elif x_minio_auth_token or authorization:
            # MinIO事件
            await handle_minio_event(body, x_minio_auth_token)
        else:
            # 直接S3事件（用于测试）
            await handle_direct_s3_event(body)
        
        return ResponseResult.ok_data(data={"message": "事件处理成功"})
        
    except Exception as e:
        logger.error(f"处理S3事件失败: {e}")
        # 即使处理失败也返回200，避免S3重试
        return ResponseResult.ok_data(data={"message": "事件处理完成"})


async def handle_sns_event(body: bytes):
    """
    处理AWS SNS事件
    """
    try:
        # 解析SNS消息
        sns_message = json.loads(body.decode('utf-8'))
        
        # 验证消息类型
        if sns_message.get('Type') != 'Notification':
            logger.warning(f"非通知类型的SNS消息: {sns_message.get('Type')}")
            return
        
        # 解析S3事件
        s3_event_data = json.loads(sns_message['Message'])
        s3_event = S3Event(**s3_event_data)
        
        # 处理上传事件
        await process_upload_events(s3_event)
        
    except Exception as e:
        logger.error(f"处理SNS事件失败: {e}")


async def handle_minio_event(body: bytes, auth_token: str):
    """
    处理MinIO事件
    """
    try:
        # 验证认证token
        from app.core.config import settings
        expected_token = getattr(settings, 'S3_WEBHOOK_AUTH_TOKEN', '')
        
        if not verify_minio_signature(auth_token, expected_token):
            logger.warning("MinIO webhook认证失败")
            return
        
        # 解析S3事件
        s3_event_data = json.loads(body.decode('utf-8'))
        s3_event = S3Event(**s3_event_data)
        
        # 处理上传事件
        await process_upload_events(s3_event)
        
    except Exception as e:
        logger.error(f"处理MinIO事件失败: {e}")


async def handle_direct_s3_event(body: bytes):
    """
    处理直接S3事件（用于测试）
    """
    try:
        # 解析S3事件
        s3_event_data = json.loads(body.decode('utf-8'))
        s3_event = S3Event(**s3_event_data)
        
        # 处理上传事件
        await process_upload_events(s3_event)
        
    except Exception as e:
        logger.error(f"处理直接S3事件失败: {e}")


async def process_upload_events(s3_event: S3Event):
    """
    处理文件上传事件
    
    Args:
        s3_event: S3事件对象
    """
    try:
        # 获取上传事件
        upload_events = s3_event.get_upload_events()
        
        for event in upload_events:
            s3_key = event.object_key
            if not s3_key:
                continue
            
            # 提取job_id
            job_id = extract_job_id_from_s3_key(s3_key)
            if not job_id:
                logger.warning(f"无法从S3键提取job_id: {s3_key}")
                continue
            
            logger.info(f"处理S3上传事件: {s3_key} -> job_id: {job_id}")
            
            # 查找对应的job
            async with get_db_context() as db:
                job_repo = JobRepository()
                job = await job_repo.get_job_by_id(db, job_id)
                
                if not job:
                    logger.warning(f"未找到对应的job: {job_id}")
                    continue
                
                # 检查job状态
                if get_prd_status_from_state(job.current_state) != "waiting_for_upload":
                    logger.info(f"Job {job_id} 状态不是waiting_for_upload: {job.current_state}")
                    continue
                
                # 验证S3文件存在
                upload_service = FileUploadService()
                file_info = await upload_service.verify_s3_file_exists(s3_key)
                
                if not file_info.get("exists"):
                    logger.warning(f"S3文件不存在: {s3_key}")
                    continue
                
                # 更新job状态
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
                        user_id=str(job.user_id)
                    )
                else:
                    orchestrator = TableFillOrchestrator()
                    await orchestrator.start_workflow(
                        db=db,
                        job_id=job_id,
                        source_type="file",
                        file_path=None,
                        file_url=None,
                        user_id=str(job.user_id)
                    )
                
                logger.info(f"Job {job_id} 已触发处理流程")
        
    except Exception as e:
        logger.error(f"处理上传事件失败: {e}")
        raise
