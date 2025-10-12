"""
双重认证中间件：JWT + API Key
"""
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.jwt import jwt_strategy
from app.services.auth.api_key_service import APIKeyService
from app.models.database.user import User


class DualAuthMiddleware:
    """双重认证中间件：JWT + API Key"""
    
    def __init__(self):
        self.api_key_service = APIKeyService()
        self.jwt_scheme = HTTPBearer(auto_error=False)
    
    async def __call__(self, request: Request, call_next):
        # 1. 检查JWT Token
        if "Authorization" in request.headers:
            try:
                user = await self._authenticate_jwt(request)
                if user:
                    request.state.user = user
                    request.state.auth_type = "jwt"
                    return await call_next(request)
            except Exception:
                pass
        
        # 2. 检查API Key
        if "X-API-Key" in request.headers:
            try:
                user = await self._authenticate_api_key(request)
                if user:
                    request.state.user = user
                    request.state.auth_type = "api_key"
                    return await call_next(request)
            except Exception:
                pass
        
        # 3. 认证失败
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    async def _authenticate_jwt(self, request: Request) -> Optional[User]:
        """JWT认证"""
        try:
            credentials: HTTPAuthorizationCredentials = await self.jwt_scheme(request)
            if not credentials:
                return None
            
            # 验证JWT令牌 - 使用FastAPI Users的JWT策略
            try:
                payload = jwt_strategy.read_token(credentials.credentials)
                if not payload:
                    return None
            except Exception:
                return None
            
            # 获取用户信息
            user_id = payload.get("sub")
            if not user_id:
                return None
            
            # 从数据库获取用户
            async with get_db() as db:
                from sqlalchemy import select
                result = await db.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                return user
                
        except Exception as e:
            print(f"JWT认证失败: {e}")
            return None
    
    async def _authenticate_api_key(self, request: Request) -> Optional[User]:
        """API Key认证"""
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            return None
        
        try:
            async with get_db() as db:
                user = await self.api_key_service.validate_api_key(db, api_key)
                return user
        except Exception as e:
            print(f"API Key认证失败: {e}")
            return None


# 创建中间件实例
dual_auth_middleware = DualAuthMiddleware()
