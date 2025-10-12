"""
GitHub OAuth 服务
"""
import httpx
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth.oauth_service import OAuthService
from app.models.database.user import User
from app.core.config import settings


class GitHubAuthService(OAuthService):
    """GitHub OAuth服务"""
    
    def __init__(self):
        super().__init__()
        self.client_id = settings.GITHUB_CLIENT_ID
        self.client_secret = settings.GITHUB_CLIENT_SECRET
    
    async def authenticate_user(self, session: AsyncSession, code: str) -> Optional[User]:
        """验证GitHub授权码"""
        try:
            # 1. 交换访问令牌
            access_token = await self._exchange_code_for_token(code)
            
            # 2. 获取用户信息
            user_info = await self.get_user_info(access_token)
            
            # 3. 创建或更新用户
            user = await self.create_or_update_user(session, user_info, "github")
            
            return user
        except Exception as e:
            print(f"GitHub认证失败: {e}")
            return None
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """获取GitHub用户信息"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            response.raise_for_status()
            return response.json()
    
    async def _exchange_code_for_token(self, code: str) -> str:
        """交换授权码获取访问令牌"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code
                },
                headers={"Accept": "application/json"}
            )
            response.raise_for_status()
            token_data = response.json()
            
            if "error" in token_data:
                raise ValueError(f"GitHub OAuth错误: {token_data['error']}")
            
            return token_data["access_token"]
