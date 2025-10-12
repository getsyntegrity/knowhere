"""
Webhook仓储层
"""
from typing import Optional, List, Dict, Any
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.database.webhook_log import WebhookLog


class WebhookRepository:
    """Webhook仓储类"""
    
    async def log_webhook_attempt(
        self,
        db: AsyncSession,
        job_id: str,
        webhook_url: str,
        attempt_number: int,
        request_payload: Dict[str, Any],
        signature: str,
        idempotency_key: str,
        response_status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """记录Webhook尝试日志"""
        try:
            import json
            
            webhook_log = WebhookLog(
                job_id=job_id,
                webhook_url=webhook_url,
                attempt_number=attempt_number,
                request_payload=json.dumps(request_payload) if request_payload else None,
                signature=signature,
                idempotency_key=idempotency_key,
                response_status_code=response_status_code,
                response_body=response_body,
                error_message=error_message
            )
            
            db.add(webhook_log)
            await db.commit()
            
            logger.info(f"Webhook日志记录成功: job_id={job_id}, attempt={attempt_number}")
            return True
            
        except Exception as e:
            logger.error(f"记录Webhook日志失败: {e}")
            await db.rollback()
            return False
    
    async def get_webhook_logs(
        self,
        db: AsyncSession,
        job_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[WebhookLog]:
        """获取Webhook日志"""
        try:
            result = await db.execute(
                select(WebhookLog)
                .where(WebhookLog.job_id == job_id)
                .order_by(desc(WebhookLog.created_at))
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"获取Webhook日志失败: {e}")
            return []
    
    async def get_webhook_logs_by_url(
        self,
        db: AsyncSession,
        webhook_url: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[WebhookLog]:
        """根据URL获取Webhook日志"""
        try:
            result = await db.execute(
                select(WebhookLog)
                .where(WebhookLog.webhook_url == webhook_url)
                .order_by(desc(WebhookLog.created_at))
                .limit(limit)
                .offset(offset)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"根据URL获取Webhook日志失败: {e}")
            return []
    
    async def get_failed_webhook_logs(
        self,
        db: AsyncSession,
        limit: int = 100
    ) -> List[WebhookLog]:
        """获取失败的Webhook日志"""
        try:
            result = await db.execute(
                select(WebhookLog)
                .where(
                    and_(
                        WebhookLog.response_status_code.isnot(None),
                        WebhookLog.response_status_code >= 400
                    )
                )
                .order_by(desc(WebhookLog.created_at))
                .limit(limit)
            )
            return result.scalars().all()
        except Exception as e:
            logger.error(f"获取失败Webhook日志失败: {e}")
            return []
    
    async def get_webhook_stats(
        self,
        db: AsyncSession,
        job_id: Optional[str] = None,
        webhook_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取Webhook统计信息"""
        try:
            query = select(WebhookLog)
            conditions = []
            
            if job_id:
                conditions.append(WebhookLog.job_id == job_id)
            if webhook_url:
                conditions.append(WebhookLog.webhook_url == webhook_url)
            
            if conditions:
                query = query.where(and_(*conditions))
            
            result = await db.execute(query)
            logs = result.scalars().all()
            
            total_attempts = len(logs)
            successful_attempts = len([log for log in logs if log.is_success()])
            failed_attempts = len([log for log in logs if log.is_failed()])
            
            return {
                "total_attempts": total_attempts,
                "successful_attempts": successful_attempts,
                "failed_attempts": failed_attempts,
                "success_rate": successful_attempts / total_attempts if total_attempts > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"获取Webhook统计失败: {e}")
            return {
                "total_attempts": 0,
                "successful_attempts": 0,
                "failed_attempts": 0,
                "success_rate": 0
            }
