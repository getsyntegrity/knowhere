"""
Webhook服务
"""

from typing import Dict, Any, Optional, List
from ..client import KnowhereClient
from ..types import WebhookConfig, WebhookLogResponse


class WebhookService:
    """Webhook服务"""
    
    def __init__(self, client: KnowhereClient):
        self.client = client
    
    async def create_config(
        self,
        webhook_url: str,
        events: Optional[List[str]] = None,
        secret: Optional[str] = None
    ) -> WebhookConfig:
        """
        创建Webhook配置
        
        Args:
            webhook_url: Webhook URL
            events: 监听的事件类型（可选）
            secret: 签名密钥（可选）
            
        Returns:
            WebhookConfig: Webhook配置
        """
        data = {
            "webhook_url": webhook_url,
            "events": events or ["job.completed", "job.failed"],
            "secret": secret
        }
        
        response = await self.client._request(
            "POST",
            "/v1/webhooks/config",
            data=data
        )
        
        return WebhookConfig(**response.data)
    
    async def get_config(self) -> Optional[WebhookConfig]:
        """
        获取Webhook配置
        
        Returns:
            Optional[WebhookConfig]: Webhook配置，如果不存在则返回None
        """
        try:
            response = await self.client._request(
                "GET",
                "/v1/webhooks/config"
            )
            return WebhookConfig(**response.data)
        except Exception:
            return None
    
    async def update_config(
        self,
        webhook_url: Optional[str] = None,
        events: Optional[List[str]] = None,
        secret: Optional[str] = None
    ) -> WebhookConfig:
        """
        更新Webhook配置
        
        Args:
            webhook_url: 新的Webhook URL（可选）
            events: 新的事件类型（可选）
            secret: 新的签名密钥（可选）
            
        Returns:
            WebhookConfig: 更新后的Webhook配置
        """
        data = {}
        if webhook_url is not None:
            data["webhook_url"] = webhook_url
        if events is not None:
            data["events"] = events
        if secret is not None:
            data["secret"] = secret
        
        response = await self.client._request(
            "PUT",
            "/v1/webhooks/config",
            data=data
        )
        
        return WebhookConfig(**response.data)
    
    async def delete_config(self) -> bool:
        """
        删除Webhook配置
        
        Returns:
            bool: 删除是否成功
        """
        try:
            await self.client._request(
                "DELETE",
                "/v1/webhooks/config"
            )
            return True
        except Exception:
            return False
    
    async def get_logs(
        self,
        job_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[WebhookLogResponse]:
        """
        获取Webhook日志
        
        Args:
            job_id: 任务ID（可选，用于过滤特定任务的日志）
            limit: 返回数量限制
            offset: 偏移量
            
        Returns:
            List[WebhookLogResponse]: Webhook日志列表
        """
        params = {
            "limit": limit,
            "offset": offset
        }
        if job_id:
            params["job_id"] = job_id
        
        response = await self.client._request(
            "GET",
            "/v1/webhooks/logs",
            params=params
        )
        
        return [WebhookLogResponse(**log) for log in response.data]
