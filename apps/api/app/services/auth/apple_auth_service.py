"""
Apple OAuth 服务
"""
from typing import Any, Dict, Optional

import httpx
import jwt
from shared.core.config import settings
from shared.models.database.user import User
from app.services.auth.oauth_service import OAuthService
from sqlalchemy.ext.asyncio import AsyncSession
from shared.core.exceptions.DomainExceptions import SystemSettingMissingException, AuthException


class AppleAuthService(OAuthService):
    """Apple OAuth服务"""
    
    def __init__(self):
        super().__init__()
        # 验证配置
        if not settings.is_apple_oauth_enabled():
            raise SystemSettingMissingException(
                setting_name="APPLE_CLIENT_ID/APPLE_CLIENT_SECRET",
                internal_message="Apple OAuth not configured properly"
            )
        self.client_id = settings.APPLE_CLIENT_ID
        self.client_secret = settings.APPLE_CLIENT_SECRET
    
    async def authenticate_user(self, session: AsyncSession, id_token: str) -> Optional[User]:
        """验证Apple ID Token"""
        try:
            # 1. 验证ID Token
            user_info = await self._verify_id_token(id_token)
            
            # 2. 创建或更新用户
            user = await self.create_or_update_user(session, user_info, "apple")
            
            return user
        except Exception as e:
            from loguru import logger
            logger.error(f"Apple认证失败: {e}", exc_info=True)
            return None
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """获取Apple用户信息"""
        # Apple不提供用户信息API，只能从ID Token中获取
        return await self._verify_id_token(access_token)
    
    async def _verify_id_token(self, id_token: str) -> Dict[str, Any]:
        """验证Apple ID Token"""
        try:
            # 获取Apple的公钥
            apple_keys = await self._get_apple_public_keys()
            
            # 解码JWT header获取kid
            header = jwt.get_unverified_header(id_token)
            kid = header.get("kid")
            
            if not kid:
                raise AuthException(
                    user_message="Invalid authentication token",
                    reason="TOKEN_MISSING_KID"
                )
            
            # 找到对应的公钥
            key = None
            for apple_key in apple_keys.get("keys", []):
                if apple_key.get("kid") == kid:
                    key = jwt.algorithms.RSAAlgorithm.from_jwk(apple_key)
                    break
            
            if not key:
                raise AuthException(
                    user_message="Invalid authentication token",
                    reason="TOKEN_KEY_NOT_FOUND"
                )
            
            # 验证并解码token
            payload = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer="https://appleid.apple.com"
            )
            
            # Apple ID Token中的name字段只在首次登录时提供，后续登录可能为空
            name_parts = payload.get("name", {})
            if isinstance(name_parts, dict):
                first_name = name_parts.get("firstName", "")
                last_name = name_parts.get("lastName", "")
                full_name = f"{first_name} {last_name}".strip()
            else:
                full_name = ""
            
            return {
                "id": payload["sub"],
                "email": payload.get("email"),
                "name": full_name or payload.get("email", "").split("@")[0],  # 如果没有name，使用email前缀
                "picture": None,  # Apple不提供头像URL
                "verified_email": True,  # Apple ID Token已验证
                "access_token": None,  # Apple使用ID Token，不需要单独的access_token
                "refresh_token": None,
                "expires_at": None
            }
            
        except Exception as e:
            raise AuthException(
                user_message="Apple authentication failed",
                reason=f"TOKEN_VERIFICATION_FAILED: {str(e)}"
            )
    
    async def _get_apple_public_keys(self) -> Dict[str, Any]:
        """获取Apple公钥"""
        async with httpx.AsyncClient() as client:
            response = await client.get("https://appleid.apple.com/auth/keys")
            response.raise_for_status()
            return response.json()
