"""
Moesif API监控中间件
"""
import json
import time
from typing import Dict, Any, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

from app.core.config import settings


class MoesifMiddleware(BaseHTTPMiddleware):
    """Moesif API监控中间件"""
    
    def __init__(self, app, moesif_application_id: str = None):
        super().__init__(app)
        self.moesif_application_id = moesif_application_id or settings.MOESIF_APPLICATION_ID
        self.moesif_client = None
        
        if self.moesif_application_id:
            try:
                from moesifapi.moesif_api_client import MoesifAPIClient
                from moesifapi.configuration import Configuration
                
                configuration = Configuration()
                configuration.api_key = self.moesif_application_id
                
                self.moesif_client = MoesifAPIClient(configuration)
                logger.info("Moesif客户端初始化成功")
                
            except ImportError:
                logger.warning("Moesif SDK未安装，跳过API监控")
            except Exception as e:
                logger.error(f"Moesif客户端初始化失败: {e}")
    
    async def dispatch(self, request: Request, call_next):
        """处理请求和响应"""
        start_time = time.time()
        
        # 获取请求信息
        request_data = await self._extract_request_data(request)
        
        # 处理请求
        response = await call_next(request)
        
        # 计算处理时间
        process_time = time.time() - start_time
        
        # 获取响应信息
        response_data = self._extract_response_data(response, process_time)
        
        # 发送到Moesif
        if self.moesif_client:
            await self._send_to_moesif(request_data, response_data)
        
        return response
    
    async def _extract_request_data(self, request: Request) -> Dict[str, Any]:
        """提取请求数据"""
        try:
            # 获取请求体
            body = None
            if request.method in ["POST", "PUT", "PATCH"]:
                try:
                    body = await request.body()
                    if body:
                        # 尝试解析JSON
                        try:
                            body = json.loads(body.decode())
                        except:
                            # 如果不是JSON，保持原始字节
                            body = body.decode('utf-8', errors='ignore')
                except:
                    body = None
            
            # 获取查询参数
            query_params = dict(request.query_params)
            
            # 获取用户ID（从JWT或API Key）
            user_id = await self._get_user_id(request)
            
            # 获取会话ID
            session_token = request.headers.get('x-session-token')
            
            return {
                "time": int(time.time() * 1000),  # 毫秒时间戳
                "uri": str(request.url),
                "verb": request.method,
                "headers": dict(request.headers),
                "api_version": request.headers.get('x-api-version', '1.0'),
                "ip_address": request.client.host if request.client else None,
                "user_id": user_id,
                "session_token": session_token,
                "body": body,
                "query_params": query_params
            }
            
        except Exception as e:
            logger.error(f"提取请求数据失败: {e}")
            return {}
    
    def _extract_response_data(self, response: Response, process_time: float) -> Dict[str, Any]:
        """提取响应数据"""
        try:
            return {
                "time": int(time.time() * 1000),
                "status": response.status_code,
                "headers": dict(response.headers),
                "body": None,  # 响应体通常很大，不记录
                "transfer_encoding": response.headers.get('transfer-encoding'),
                "content_length": response.headers.get('content-length'),
                "process_time_ms": round(process_time * 1000, 2)
            }
            
        except Exception as e:
            logger.error(f"提取响应数据失败: {e}")
            return {}
    
    async def _get_user_id(self, request: Request) -> Optional[str]:
        """获取用户ID"""
        try:
            # 从Authorization header获取
            auth_header = request.headers.get('authorization')
            if auth_header:
                if auth_header.startswith('Bearer '):
                    # JWT token
                    token = auth_header[7:]
                    # TODO: 解析JWT获取用户ID
                    # 这里需要实现JWT解析逻辑
                    pass
                elif auth_header.startswith('ApiKey '):
                    # API Key
                    api_key = auth_header[7:]
                    # TODO: 从API Key获取用户ID
                    # 这里需要查询数据库获取用户ID
                    pass
            
            # 从X-User-ID header获取（如果前端设置）
            return request.headers.get('x-user-id')
            
        except Exception as e:
            logger.error(f"获取用户ID失败: {e}")
            return None
    
    async def _send_to_moesif(self, request_data: Dict[str, Any], response_data: Dict[str, Any]):
        """发送数据到Moesif"""
        try:
            if not self.moesif_client:
                return
            
            # 构建Moesif事件
            event = {
                "request": request_data,
                "response": response_data,
                "user_id": request_data.get("user_id"),
                "session_token": request_data.get("session_token"),
                "tags": self._get_event_tags(request_data, response_data),
                "metadata": self._get_event_metadata(request_data, response_data)
            }
            
            # 异步发送（不等待响应）
            import asyncio
            asyncio.create_task(self._send_event_async(event))
            
        except Exception as e:
            logger.error(f"发送Moesif事件失败: {e}")
    
    async def _send_event_async(self, event: Dict[str, Any]):
        """异步发送事件到Moesif"""
        try:
            # 这里应该使用Moesif的异步API
            # 由于Moesif Python SDK是同步的，我们在线程池中执行
            import asyncio
            import concurrent.futures
            
            def send_sync():
                try:
                    # 使用正确的Moesif API方法
                    if hasattr(self.moesif_client, 'create_event'):
                        self.moesif_client.create_event(event)
                    elif hasattr(self.moesif_client, 'create_events'):
                        self.moesif_client.create_events([event])
                    else:
                        logger.warning("Moesif客户端不支持create_event或create_events方法")
                except Exception as e:
                    logger.error(f"Moesif同步发送失败: {e}")
            
            # 在线程池中执行同步调用
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                await loop.run_in_executor(executor, send_sync)
                
        except Exception as e:
            logger.error(f"异步发送Moesif事件失败: {e}")
    
    def _get_event_tags(self, request_data: Dict[str, Any], response_data: Dict[str, Any]) -> Dict[str, str]:
        """获取事件标签"""
        tags = {}
        
        # 根据路径添加标签
        uri = request_data.get("uri", "")
        if "/kb" in uri:
            tags["feature"] = "knowledge_base"
        elif "/billing" in uri:
            tags["feature"] = "billing"
        elif "/auth" in uri:
            tags["feature"] = "authentication"
        
        # 根据状态码添加标签
        status = response_data.get("status", 200)
        if 200 <= status < 300:
            tags["status"] = "success"
        elif 400 <= status < 500:
            tags["status"] = "client_error"
        elif 500 <= status < 600:
            tags["status"] = "server_error"
        
        return tags
    
    def _get_event_metadata(self, request_data: Dict[str, Any], response_data: Dict[str, Any]) -> Dict[str, Any]:
        """获取事件元数据"""
        metadata = {}
        
        # 添加处理时间
        process_time = response_data.get("process_time_ms", 0)
        metadata["process_time_ms"] = process_time
        
        # 添加请求大小
        body = request_data.get("body")
        if body:
            if isinstance(body, str):
                metadata["request_size_bytes"] = len(body.encode())
            elif isinstance(body, dict):
                metadata["request_size_bytes"] = len(json.dumps(body).encode())
        
        # 添加响应大小
        content_length = response_data.get("content_length")
        if content_length:
            metadata["response_size_bytes"] = int(content_length)
        
        return metadata
