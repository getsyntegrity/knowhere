"""
Google OAuth 服务
"""
from typing import Any, Dict, Optional

import httpx
from shared.core.config import settings
from shared.models.database.user import User
from app.services.auth.oauth_service import OAuthService
from sqlalchemy.ext.asyncio import AsyncSession
from shared.core.exceptions.domain_exceptions import SystemSettingMissingException, AuthException


class GoogleAuthService(OAuthService):
    """Google OAuth服务"""
    
    def __init__(self):
        super().__init__()
        # 验证配置
        if not settings.is_google_oauth_enabled():
            raise SystemSettingMissingException(
                setting_name="GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET",
                internal_message="Google OAuth not configured properly"
            )
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
    
    async def authenticate_user(self, session: AsyncSession, id_token: str) -> Optional[User]:
        """验证Google ID Token"""
        try:
            # 1. 验证ID Token
            user_info = await self._verify_id_token(id_token)
            
            # 2. 创建或更新用户
            user = await self.create_or_update_user(session, user_info, "google")
            
            return user
        except Exception as e:
            from loguru import logger
            logger.error(f"Google认证失败: {e}", exc_info=True)
            return None
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """获取Google用户信息"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            return response.json()
    
    async def _verify_id_token(self, id_token: str) -> Dict[str, Any]:
        """验证Google ID Token"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
            )
            response.raise_for_status()
            token_info = response.json()
            
            if token_info.get("aud") != self.client_id:
                raise AuthException(
                    user_message="Invalid authentication token",
                    reason="TOKEN_INVALID_AUDIENCE"
                )
            
            if not token_info.get("iss").startswith("https://accounts.google.com"):
                raise AuthException(
                    user_message="Invalid authentication token",
                    reason="TOKEN_INVALID_ISSUER"
                )
            
            return {
                "id": token_info["sub"],
                "email": token_info["email"],
                "name": token_info.get("name"),
                "picture": token_info.get("picture"),
                "verified_email": token_info.get("email_verified", False)
            }
