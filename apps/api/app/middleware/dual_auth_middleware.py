"""
双重认证中间件：JWT + API Key
优化版本：统一使用Authorization头部，支持Bearer格式
"""
from typing import Optional

from shared.core.database import get_db
from app.core.jwt import jwt_strategy
from shared.models.database.user import User
from app.services.auth.api_key_service import APIKeyService
from fastapi import Request, status
from shared.core.exceptions.domain_exceptions import AuthException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger


class DualAuthMiddleware:
    """双重认证中间件：JWT + API Key
    
    优化特性：
    - 统一使用Authorization头部
    - 支持Bearer sk_xxxx格式的API Key
    - 支持Bearer JWT格式的JWT token
    - 改进错误处理和日志记录
    """
    
    def __init__(self):
        self.api_key_service = APIKeyService()
        self.jwt_scheme = HTTPBearer(auto_error=False)
    
    async def __call__(self, request: Request, call_next):
        """中间件主入口"""
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            self._raise_auth_error("Missing Authorization header")
        
        try:
            # 1. 优先尝试API Key认证 (Bearer sk_格式)
            user = await self._authenticate_api_key(request)
            if user:
                request.state.user = user
                request.state.auth_type = "api_key"
                logger.debug(f"API Key认证成功：用户 {user.email}")
                return await call_next(request)
            
            # 2. 尝试JWT认证 (Bearer JWT格式)
            user = await self._authenticate_jwt(request)
            if user:
                request.state.user = user
                request.state.auth_type = "jwt"
                logger.debug(f"JWT认证成功：用户 {user.email}")
                return await call_next(request)
            
            # 3. 两种认证都失败
            self._raise_auth_error("Invalid or expired token")
            
        except AuthException:
            raise
        except Exception as e:
            logger.error(f"认证过程中发生错误: {e}")
            self._raise_auth_error("Authentication failed")
    
    def _raise_auth_error(self, detail: str) -> None:
        """抛出认证错误"""
        raise AuthException(
            user_message=detail
        )
    
    async def _authenticate_jwt(self, request: Request) -> Optional[User]:
        """JWT认证 - 只接受标准JWT token，不接受API Key"""
        try:
            credentials: HTTPAuthorizationCredentials = await self.jwt_scheme(request)
            if not credentials:
                return None
            
            # 检查是否是API Key格式
            if credentials.credentials.startswith("sk_"):
                return None
            
            # 验证JWT令牌
            try:
                payload = jwt_strategy.read_token(credentials.credentials)
                if not payload:
                    return None
            except Exception as e:
                logger.debug(f"JWT token验证失败: {e}")
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
                if user and not user.is_active:
                    logger.debug(f"JWT认证失败：用户未激活 {user_id}")
                    return None
                return user
                
        except Exception as e:
            logger.debug(f"JWT认证失败: {e}")
            return None
    
    async def _authenticate_api_key(self, request: Request) -> Optional[User]:
        """API Key认证 - 支持 Authorization: Bearer sk_xxxx 格式"""
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer sk_"):
            return None
        
        api_key = auth_header.split(" ", 1)[1] if len(auth_header.split(" ", 1)) > 1 else None
        if not api_key:
            return None
        
        try:
            async with get_db() as db:
                user = await self.api_key_service.validate_api_key(db, api_key)
                if user and not user.is_active:
                    logger.debug(f"API Key认证失败：用户未激活 {user.id}")
                    return None
                return user
        except Exception as e:
            logger.debug(f"API Key认证失败: {e}")
            return None


# 创建中间件实例
dual_auth_middleware = DualAuthMiddleware()
