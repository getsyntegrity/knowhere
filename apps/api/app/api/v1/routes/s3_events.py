"""
S3事件Webhook路由
"""
import json
import os
import hmac
import hashlib
import base64
import aiohttp
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, status, Request, Header
from loguru import logger

from app.models.schemas.s3_event import S3Event
from app.models.schemas.oss_event import OSSEvent
from app.repositories.job_repository import JobRepository
from app.core.config import settings
from app.services.storage.file_upload_service import FileUploadService
from app.services.knowledge.kb_orchestrator import KBOrchestrator
from app.services.table_fill.orchestrator import TableFillOrchestrator
from app.core.state_machine import JobStatus
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


def verify_oss_signature(request_body: bytes, headers: Dict[str, str]) -> bool:
    """
    验证OSS事件回调签名
    
    Args:
        request_body: 请求体
        headers: 请求头
        
    Returns:
        bool: 验证是否通过
    """
    try:
        from app.core.config import settings
        
        # 如果禁用签名验证，直接返回True
        if not getattr(settings, 'OSS_EVENT_VERIFY_SIGNATURE', True):
            return True
        
        # OSS回调签名验证
        # 实际实现需要根据OSS文档验证签名
        # 这里简化处理，生产环境需要完整实现
        callback_key = getattr(settings, 'OSS_EVENT_CALLBACK_KEY', '')
        if not callback_key:
            logger.warning("OSS_EVENT_CALLBACK_KEY未配置，跳过签名验证")
            return True
        
        # TODO: 实现OSS签名验证逻辑
        # OSS RBCallback签名验证需要：
        # 1. 从headers中获取签名信息
        # 2. 使用callback_key计算签名
        # 3. 对比签名是否一致
        
        return True
    except Exception as e:
        logger.error(f"OSS签名验证失败: {e}")
        return False


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


@router.get("/s3-events", response_model=dict, summary="S3事件Webhook GET")
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
        return {"message": "SNS订阅确认成功"}
    
    return {"message": "GET请求处理完成"}


@router.post("/s3-events", response_model=dict, summary="S3事件Webhook POST")
async def handle_s3_events(
    request: Request,
    x_amz_sns_message_type: str = Header(None, alias="x-amz-sns-message-type"),
    x_minio_auth_token: str = Header(None, alias="x-minio-auth-token"),
    authorization: str = Header(None)
):
    """
    处理S3事件通知POST请求 - 支持AWS SNS、MinIO和OSS
    """
    logger.info(f"======== S3事件请求 =========")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Client IP: {request.client.host}")
    try:
        # 获取请求体
        body = await request.body()
        headers = dict(request.headers)
        
        # 判断事件来源
        if x_amz_sns_message_type:
            # AWS SNS事件
            result = await handle_sns_event(body)
            if result:
                return result
        elif _is_oss_event(headers):
            # OSS事件（包含阿里云 MNS 通知代理场景）
            await handle_oss_event(body, headers)
        elif x_minio_auth_token:
            # MinIO事件（仅当提供专用的 x-minio-auth-token 时识别）
            await handle_minio_event(body, x_minio_auth_token)
        else:
            # 直接S3事件（用于测试）
            await handle_direct_s3_event(body)
        
        return {"message": "事件处理成功"}
        
    except Exception as e:
        logger.error(f"处理S3事件失败: {e}")
        # 即使处理失败也返回200，避免S3重试
        return {"message": "事件处理完成"}


async def handle_sns_event(body: bytes):
    """
    处理AWS SNS事件
    """
    try:
        # 解析SNS消息
        sns_message = json.loads(body.decode('utf-8'))
        
        # 检查消息类型
        message_type = sns_message.get('Type')
        logger.info(f"SNS消息类型: {message_type}")
        
        if message_type == 'SubscriptionConfirmation':
            # 处理订阅确认
            logger.info("收到SNS订阅确认请求")
            subscribe_url = sns_message.get('SubscribeURL')
            if subscribe_url:
                logger.info(f"SNS订阅确认URL: {subscribe_url}")
                # 访问确认URL来确认订阅
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(subscribe_url) as response:
                            if response.status == 200:
                                logger.info("SNS订阅确认成功")
                                return {"message": "SNS订阅确认成功"}
                            else:
                                logger.error(f"SNS订阅确认失败，状态码: {response.status}")
                                return {"message": "SNS订阅确认失败"}
                except Exception as e:
                    logger.error(f"访问SNS订阅确认URL失败: {e}")
                    return {"message": "SNS订阅确认失败"}
            else:
                logger.warning("SNS订阅确认消息中没有SubscribeURL")
                return {"message": "SNS订阅确认失败"}
        
        elif message_type == 'Notification':
            # 处理通知消息
            logger.info("收到SNS通知消息")
            logger.info(f"SNS消息内容: {sns_message}")
            
            # 解析S3事件
            try:
                s3_event_data = json.loads(sns_message['Message'])
                logger.info(f"S3事件数据: {s3_event_data}")
                s3_event = S3Event(**s3_event_data)
                
                # 处理上传事件
                await process_upload_events(s3_event)
            except Exception as e:
                logger.error(f"解析S3事件数据失败: {e}")
                logger.error(f"SNS消息: {sns_message}")
                # 尝试直接处理SNS消息作为S3事件
                try:
                    s3_event = S3Event(**sns_message)
                    await process_upload_events(s3_event)
                except Exception as e2:
                    logger.error(f"直接解析SNS消息为S3事件也失败: {e2}")
                    raise
        else:
            logger.warning(f"未知的SNS消息类型: {message_type}")
            return {"message": f"未知的SNS消息类型: {message_type}"}
        
    except Exception as e:
        logger.error(f"处理SNS事件失败: {e}")
        raise


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


def _is_oss_event(headers: Dict[str, str]) -> bool:
    """
    判断是否为OSS事件
    
    Args:
        headers: 请求头
        
    Returns:
        bool: 是否为OSS事件
    """
    # OSS事件的特征标识
    # 可以通过以下方式识别：
    # 1. 检查S3_TYPE环境变量
    # 2. 检查特定的请求头（如果有）
    # 3. 检查请求体格式
    
    storage_type = os.getenv('S3_TYPE', 's3').lower()
    if storage_type == 'oss':
        return True
    
    # 也可以检查请求头中是否有OSS特有的标识
    # 例如：'x-oss-pub-key-url' 或其他OSS特定的header
    if 'x-oss-pub-key-url' in headers:
        return True
    
    # 识别阿里云 MNS 通知代理头/UA
    if 'x-mns-version' in headers or 'x-mns-signing-cert-url' in headers:
        return True
    user_agent = headers.get('user-agent') or headers.get('User-Agent')
    if user_agent and 'Aliyun Notification Service Agent' in user_agent:
        return True
    
    return False


async def handle_oss_event(body: bytes, headers: Dict[str, str]):
    """
    处理OSS事件
    """
    try:
        # 验证签名
        if not verify_oss_signature(body, headers):
            logger.warning("OSS事件签名验证失败")
            return
        
        # 解析OSS事件（兼容 MNS 外层 envelope）
        event_data = json.loads(body.decode('utf-8'))
        logger.info(f"OSS事件数据: {event_data}")
        # 如果是 MNS 推送，实际事件位于 Message 字段中
        if isinstance(event_data, dict) and 'Message' in event_data:
            try:
                inner = event_data.get('Message')
                if isinstance(inner, str):
                    event_data = json.loads(inner)
                    logger.info(f"解包MNS Message后的事件数据: {event_data}")
                elif isinstance(inner, dict):
                    event_data = inner
            except Exception as _:
                # 无法解包则按原样继续，后续分支会报未知格式
                pass
        
        # 判断事件格式
        if 'events' in event_data:
            # 标准OSS事件格式
            oss_event = OSSEvent(**event_data)
        elif 'Records' in event_data:
            # 兼容S3事件格式（OSS可能使用类似的格式）
            # 尝试转换为OSS事件格式
            oss_event = _convert_s3_format_to_oss(event_data)
        else:
            logger.error(f"未知的OSS事件格式: {event_data}")
            return
        
        # 转换为S3Event格式，复用现有处理逻辑
        s3_event = oss_event.to_s3_event()
        
        # 处理上传事件
        await process_upload_events(s3_event)
        
    except Exception as e:
        logger.error(f"处理OSS事件失败: {e}")
        raise


def _convert_s3_format_to_oss(event_data: Dict[str, Any]) -> OSSEvent:
    """
    将S3格式的事件转换为OSS事件格式
    
    Args:
        event_data: S3格式的事件数据
        
    Returns:
        OSSEvent: OSS事件对象
    """
    from app.models.schemas.oss_event import OSSEventRecord
    
    # 如果事件已经是S3格式，尝试转换为OSS格式
    records = event_data.get('Records', [])
    oss_records = []
    
    for record in records:
        oss_record = OSSEventRecord(
            eventName=record.get('eventName', '').replace('s3:', ''),
            eventSource='acs:oss',
            eventTime=record.get('eventTime', ''),
            region=record.get('awsRegion', ''),
            oss={
                'bucket': record.get('s3', {}).get('bucket', {}),
                'object': record.get('s3', {}).get('object', {})
            }
        )
        oss_records.append(oss_record)
    
    return OSSEvent(events=oss_records)


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
            # 从S3事件记录中获取对象键
            s3_key = event.object_key or event.s3.get('object', {}).get('key')
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
                if job.status != "waiting-file":
                    logger.info(f"Job {job_id} 状态不是waiting-file: {job.status}")
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
                
                # 文件上传完成后，转换到pending状态
                await state_machine.transition(
                    db, job_id, JobStatus.PENDING.value,
                    "s3_upload_completed", None, "system"
                )
                
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
