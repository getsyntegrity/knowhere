"""
API Key 认证中间件
"""

from shared.core.database import get_db
from app.services.auth.api_key_service import APIKeyService
from shared.core.exceptions.DomainExceptions import AuthException, KnowhereException
from fastapi import Request, status


class APIKeyAuthMiddleware:
    """API Key认证中间件"""
    
    def __init__(self):
        self.api_key_service = APIKeyService()
    
    async def __call__(self, request: Request, call_next):
        # 检查是否需要API Key认证
        if self._requires_api_key_auth(request):
            # 获取API Key
            api_key = request.headers.get("X-API-Key")
            if not api_key:
                raise AuthException(
                    user_message="API Key required"
                )
            
            # 验证API Key
            try:
                async with get_db() as db:
                    user = await self.api_key_service.validate_api_key(db, api_key)
                    if not user:
                        raise AuthException(
                            user_message="Invalid API Key"
                        )
                    
                    # 将用户信息添加到请求状态
                    request.state.user = user
                    request.state.auth_type = "api_key"
                    request.state.api_key = api_key
            except KnowhereException:
                raise
            except Exception as e:
                print(f"API Key认证失败: {e}")
                raise AuthException(
                    user_message="API Key authentication failed",
                    internal_message=f"API Key authentication failed: {str(e)}"
                )
        
        # 继续处理请求
        response = await call_next(request)
        return response
    
    def _requires_api_key_auth(self, request: Request) -> bool:
        """判断是否需要API Key认证"""
        # 只对API路径进行认证
        if not request.url.path.startswith("/api/v1/"):
            return False
        
        # 排除认证相关路径
        excluded_paths = [
            "/api/v1/auth/",
            "/api/v1/oauth/",
            "/api/v1/billing/credits",
            "/api/v1/billing/usage",
            "/api/v1/billing/history"
        ]
        
        for path in excluded_paths:
            if request.url.path.startswith(path):
                return False
        
        return True


# 创建中间件实例
api_key_auth_middleware = APIKeyAuthMiddleware()
