"""
Google OAuth 服务
"""
import httpx
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth.oauth_service import OAuthService
from app.models.database.user import User
from app.core.config import settings


class GoogleAuthService(OAuthService):
    """Google OAuth服务"""
    
    def __init__(self):
        super().__init__()
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
            print(f"Google认证失败: {e}")
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
            
            # 验证audience
            if token_info.get("aud") != self.client_id:
                raise ValueError("Invalid audience")
            
            # 验证issuer
            if not token_info.get("iss").startswith("https://accounts.google.com"):
                raise ValueError("Invalid issuer")
            
            return {
                "id": token_info["sub"],
                "email": token_info["email"],
                "name": token_info.get("name"),
                "picture": token_info.get("picture"),
                "verified_email": token_info.get("email_verified", False)
            }
