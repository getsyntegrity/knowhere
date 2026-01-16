"""
GitHub OAuth 服务
"""
from typing import Any, Dict, Optional

import httpx
from shared.core.config import settings
from shared.models.database.user import User
from app.services.auth.oauth_service import OAuthService
from sqlalchemy.ext.asyncio import AsyncSession
from shared.core.exceptions.DomainExceptions import SystemSettingMissingException, AuthException


class GitHubAuthService(OAuthService):
    """GitHub OAuth服务"""
    
    def __init__(self):
        super().__init__()
        # 验证配置
        if not settings.is_github_oauth_enabled():
            raise SystemSettingMissingException(
                setting_name="GITHUB_CLIENT_ID/GITHUB_CLIENT_SECRET",
                internal_message="GitHub OAuth not configured properly"
            )
        self.client_id = settings.GITHUB_CLIENT_ID
        self.client_secret = settings.GITHUB_CLIENT_SECRET
    
    async def authenticate_user(self, session: AsyncSession, code: str) -> Optional[User]:
        """验证GitHub授权码"""
        try:
            # 1. 交换授权码获取访问令牌
            token_data = await self._exchange_code_for_token(code)
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            
            # 计算过期时间（GitHub的access_token可能有过期时间）
            expires_at = None
            if token_data.get("expires_in"):
                from datetime import datetime, timedelta
                expires_at = datetime.utcnow() + timedelta(seconds=token_data["expires_in"])
            
            # 2. 获取用户信息
            github_user_info = await self.get_user_info(access_token)
            
            # 3. 转换为统一格式
            user_info = self._normalize_user_info(github_user_info, access_token, refresh_token, expires_at)
            
            # 4. 创建或更新用户
            user = await self.create_or_update_user(session, user_info, "github")
            
            return user
        except Exception as e:
            from loguru import logger
            logger.error(f"GitHub认证失败: {e}", exc_info=True)
            return None
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """获取GitHub用户信息"""
        async with httpx.AsyncClient() as client:
            # 1. 获取基本用户信息
            response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            response.raise_for_status()
            user_data = response.json()
            
            # 2. 如果email为空，尝试获取用户邮箱列表（需要user:email scope）
            if not user_data.get("email"):
                try:
                    email_response = await client.get(
                        "https://api.github.com/user/emails",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Accept": "application/vnd.github.v3+json"
                        }
                    )
                    email_response.raise_for_status()
                    emails = email_response.json()
                    # 查找主邮箱（primary=True）或第一个已验证的邮箱
                    primary_email = next((e for e in emails if e.get("primary")), None)
                    verified_email = next((e for e in emails if e.get("verified")), None)
                    user_data["email"] = (primary_email or verified_email or emails[0] if emails else {}).get("email")
                except Exception:
                    # 如果获取邮箱失败，继续使用空邮箱
                    pass
            
            return user_data
    
    async def _exchange_code_for_token(self, code: str) -> Dict[str, Any]:
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
                raise AuthException(
                    user_message="GitHub authentication failed",
                    reason=f"GITHUB_OAUTH_ERROR: {token_data['error']}"
                )
            
            return token_data
    
    def _normalize_user_info(self, github_data: Dict[str, Any], access_token: str, refresh_token: Optional[str] = None, expires_at: Optional[Any] = None) -> Dict[str, Any]:
        """将GitHub用户信息转换为统一格式"""
        from datetime import datetime, timedelta
        
        # GitHub API返回的字段：
        # - id: 数字ID（需要转换为字符串）
        # - login: 用户名
        # - name: 显示名称（可能为空）
        # - email: 邮箱（可能为空，需要额外请求）
        # - avatar_url: 头像URL
        # - bio: 个人简介
        
        # 如果email为空，尝试获取主邮箱
        email = github_data.get("email")
        if not email:
            # GitHub API需要user:email scope才能获取邮箱
            # 如果scope不足，email可能为空
            email = None
        
        # 使用传入的过期时间（已在authenticate_user中计算）
        expires_at_value = expires_at
        
        # 处理邮箱：如果仍然为空，使用login作为占位符（但标记为未验证）
        final_email = email
        verified_email = email is not None
        
        if not final_email:
            # 如果没有邮箱，使用login作为占位符，但这不是真实邮箱
            # 注意：这种情况下用户可能无法接收邮件通知
            final_email = f"{github_data.get('login')}@github.local"
            verified_email = False
        
        return {
            "id": str(github_data["id"]),  # GitHub返回的是数字ID，转换为字符串
            "email": final_email,
            "name": github_data.get("name") or github_data.get("login"),  # 优先使用name，否则使用login
            "picture": github_data.get("avatar_url"),
            "verified_email": verified_email,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at_value
        }
