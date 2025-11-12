"""
Webhook推送服务（API服务专用）
负责发送Webhook请求并记录日志
"""
import json
import hmac
import hashlib
import uuid
import asyncio
import aiohttp
from typing import Dict, Any, Optional
from datetime import datetime
from loguru import logger

from app.core.config import settings
from app.repositories.webhook_repository import WebhookRepository
from app.core.database import get_db_context


class WebhookService:
    """Webhook推送服务"""
    
    def __init__(self):
        self.webhook_repo = WebhookRepository()
        self.signing_secret = getattr(settings, 'WEBHOOK_SIGNING_SECRET', 'default_secret')
        self.max_retries = 5
        self.base_delay = 1  # 基础延迟（秒）
        self.max_delay = 60  # 最大延迟（秒）
    
    async def send_webhook(
        self, 
        job_id: str, 
        webhook_url: str, 
        payload: Dict[str, Any],
        attempt_number: int = 1
    ) -> Dict[str, Any]:
        """
        发送Webhook
        
        Args:
            job_id: 任务ID
            webhook_url: Webhook URL
            payload: 推送数据
            attempt_number: 尝试次数
            
        Returns:
            Dict: 发送结果
        """
        idempotency_key = str(uuid.uuid4())
        signature = self._generate_signature(payload)
        
        try:
            # 构建请求头
            headers = {
                'Content-Type': 'application/json',
                'X-Webhook-Signature': signature,
                'X-Webhook-Idempotency-Key': idempotency_key,
                'X-Webhook-Timestamp': str(int(datetime.utcnow().timestamp())),
                'User-Agent': 'Knowhere-Webhook/1.0'
            }
            
            # 发送请求
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response_body = await response.text()
                    
                    # 记录Webhook日志
                    await self._log_webhook_attempt(
                        job_id=job_id,
                        webhook_url=webhook_url,
                        attempt_number=attempt_number,
                        request_payload=payload,
                        signature=signature,
                        idempotency_key=idempotency_key,
                        response_status_code=response.status,
                        response_body=response_body,
                        error_message=None
                    )
                    
                    if 200 <= response.status < 300:
                        logger.info(f"Webhook发送成功: job_id={job_id}, status={response.status}")
                        return {
                            "success": True,
                            "status_code": response.status,
                            "response_body": response_body,
                            "attempt_number": attempt_number
                        }
                    else:
                        logger.warning(f"Webhook发送失败: job_id={job_id}, status={response.status}")
                        return {
                            "success": False,
                            "status_code": response.status,
                            "response_body": response_body,
                            "attempt_number": attempt_number
                        }
                        
        except asyncio.TimeoutError:
            error_msg = "Webhook请求超时"
            logger.error(f"Webhook超时: job_id={job_id}")
            await self._log_webhook_attempt(
                job_id, webhook_url, attempt_number, payload, 
                signature, idempotency_key, None, None, error_msg
            )
            return {"success": False, "error": error_msg, "attempt_number": attempt_number}
            
        except Exception as e:
            error_msg = f"Webhook发送异常: {str(e)}"
            logger.error(f"Webhook异常: job_id={job_id}, error={e}")
            await self._log_webhook_attempt(
                job_id, webhook_url, attempt_number, payload,
                signature, idempotency_key, None, None, error_msg
            )
            return {"success": False, "error": error_msg, "attempt_number": attempt_number}
    
    def _generate_signature(self, payload: Dict[str, Any]) -> str:
        """生成HMAC-SHA256签名"""
        payload_str = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        signature = hmac.new(
            self.signing_secret.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return f"sha256={signature}"
    
    def _calculate_delay(self, attempt: int) -> float:
        """计算重试延迟（指数退避 + 抖动）"""
        import random
        
        # 指数退避
        delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
        
        # 添加抖动（±25%）
        jitter = random.uniform(0.75, 1.25)
        delay = delay * jitter
        
        return delay
    
    async def _log_webhook_attempt(
        self,
        job_id: str,
        webhook_url: str,
        attempt_number: int,
        request_payload: Dict[str, Any],
        signature: str,
        idempotency_key: str,
        response_status_code: Optional[int],
        response_body: Optional[str],
        error_message: Optional[str]
    ):
        """记录Webhook尝试日志"""
        try:
            async with get_db_context() as db:
                await self.webhook_repo.log_webhook_attempt(
                    db=db,
                    job_id=job_id,
                    webhook_url=webhook_url,
                    attempt_number=attempt_number,
                    request_payload=request_payload,
                    signature=signature,
                    idempotency_key=idempotency_key,
                    response_status_code=response_status_code,
                    response_body=response_body,
                    error_message=error_message
                )
        except Exception as e:
            logger.error(f"记录Webhook日志失败: {e}")

