"""
Knowhere HTTP 客户端
"""

import json
from typing import Any, Dict, Optional, Union
import httpx
from .types import KnowhereClientConfig, ApiResponse, ApiError
from .services import TableFillService, KnowledgeBaseService, WebhookService, JobManagementService


class KnowhereClient:
    """Knowhere API 客户端"""

    def __init__(self, config: Union[KnowhereClientConfig, Dict[str, Any]]):
        """
        初始化客户端
        
        Args:
            config: 客户端配置，可以是 KnowhereClientConfig 实例或字典
        """
        if isinstance(config, dict):
            config = KnowhereClientConfig(**config)
        
        self.config = config
        self.base_url = config.base_url.rstrip('/')
        
        # 设置默认请求头
        self.headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'knowhere-sdk-python/0.0.1',
        }
        
        if config.headers:
            self.headers.update(config.headers)
            
        if config.api_key:
            self.headers['Authorization'] = f'Bearer {config.api_key}'
        
        # 初始化各个服务模块
        self.table_fill = TableFillService(self)
        self.kb = KnowledgeBaseService(self)
        self.webhook = WebhookService(self)
        self.jobs = JobManagementService(self)

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ApiResponse:
        """
        发送 HTTP 请求
        
        Args:
            method: HTTP 方法
            endpoint: API 端点
            data: 请求体数据
            params: URL 参数
            headers: 额外请求头
            
        Returns:
            ApiResponse: API 响应
            
        Raises:
            ApiError: API 错误
        """
        url = f"{self.base_url}{endpoint}"
        request_headers = {**self.headers}
        if headers:
            request_headers.update(headers)

        try:
            async with httpx.AsyncClient(timeout=self.config.timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    headers=request_headers,
                )
                
                # 尝试解析 JSON 响应
                try:
                    response_data = response.json()
                except json.JSONDecodeError:
                    response_data = response.text

                if not response.is_success:
                    raise ApiError(
                        message=f"HTTP {response.status_code}: {response.reason_phrase}",
                        status=response.status_code,
                        status_text=response.reason_phrase,
                        data=response_data,
                    )

                return ApiResponse(
                    data=response_data,
                    status=response.status_code,
                    status_text=response.reason_phrase,
                    headers=dict(response.headers),
                )

        except httpx.TimeoutException:
            raise ApiError("Request timeout")
        except httpx.RequestError as e:
            raise ApiError(f"Request failed: {str(e)}")

    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ApiResponse:
        """GET 请求"""
        return await self._request("GET", endpoint, params=params, headers=headers)

    async def post(
        self,
        endpoint: str,
        data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ApiResponse:
        """POST 请求"""
        return await self._request("POST", endpoint, data=data, params=params, headers=headers)

    async def put(
        self,
        endpoint: str,
        data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ApiResponse:
        """PUT 请求"""
        return await self._request("PUT", endpoint, data=data, params=params, headers=headers)

    async def patch(
        self,
        endpoint: str,
        data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ApiResponse:
        """PATCH 请求"""
        return await self._request("PATCH", endpoint, data=data, params=params, headers=headers)

    async def delete(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ApiResponse:
        """DELETE 请求"""
        return await self._request("DELETE", endpoint, params=params, headers=headers)

    def sync_get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ApiResponse:
        """同步 GET 请求"""
        import asyncio
        return asyncio.run(self.get(endpoint, params, headers))

    def sync_post(
        self,
        endpoint: str,
        data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ApiResponse:
        """同步 POST 请求"""
        import asyncio
        return asyncio.run(self.post(endpoint, data, params, headers))

    def sync_put(
        self,
        endpoint: str,
        data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ApiResponse:
        """同步 PUT 请求"""
        import asyncio
        return asyncio.run(self.put(endpoint, data, params, headers))

    def sync_patch(
        self,
        endpoint: str,
        data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ApiResponse:
        """同步 PATCH 请求"""
        import asyncio
        return asyncio.run(self.patch(endpoint, data, params, headers))

    def sync_delete(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> ApiResponse:
        """同步 DELETE 请求"""
        import asyncio
        return asyncio.run(self.delete(endpoint, params, headers))
