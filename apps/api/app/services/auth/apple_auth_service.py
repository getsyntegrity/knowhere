"""
Apple OAuth 服务
"""
import httpx
import jwt
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth.oauth_service import OAuthService
from app.models.database.user import User
from app.core.config import settings


class AppleAuthService(OAuthService):
    """Apple OAuth服务"""
    
    def __init__(self):
        super().__init__()
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
            print(f"Apple认证失败: {e}")
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
                raise ValueError("Invalid token header")
            
            # 找到对应的公钥
            key = None
            for apple_key in apple_keys.get("keys", []):
                if apple_key.get("kid") == kid:
                    key = jwt.algorithms.RSAAlgorithm.from_jwk(apple_key)
                    break
            
            if not key:
                raise ValueError("Public key not found")
            
            # 验证并解码token
            payload = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                audience=self.client_id,
                issuer="https://appleid.apple.com"
            )
            
            return {
                "id": payload["sub"],
                "email": payload.get("email"),
                "name": payload.get("name", {}).get("firstName", "") + " " + payload.get("name", {}).get("lastName", ""),
                "verified_email": True  # Apple ID Token已验证
            }
            
        except Exception as e:
            raise ValueError(f"Apple ID Token验证失败: {e}")
    
    async def _get_apple_public_keys(self) -> Dict[str, Any]:
        """获取Apple公钥"""
        async with httpx.AsyncClient() as client:
            response = await client.get("https://appleid.apple.com/auth/keys")
            response.raise_for_status()
            return response.json()
