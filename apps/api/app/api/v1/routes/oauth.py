"""
OAuth 认证 API
"""
from uuid import UUID

from shared.core.database import get_db
from app.core.jwt import auth_backend
from app.core.users import get_user_manager
from shared.models.database.user import User
from shared.models.schemas.oauth import (AppleLoginRequest, GitHubLoginRequest,
                                      GoogleLoginRequest, OAuthLoginResponse)
from app.services.auth.apple_auth_service import AppleAuthService
from app.services.auth.github_auth_service import GitHubAuthService
from app.services.auth.google_auth_service import GoogleAuthService
from fastapi import APIRouter, Depends, Query, status
from fastapi_users import FastAPIUsers
from shared.core.exceptions.DomainExceptions import AuthException, SystemSettingMissingException
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["OAuth Authentication"])

# 创建 FastAPI Users 实例用于生成JWT令牌
fastapi_users = FastAPIUsers[User, UUID](get_user_manager, [auth_backend])


@router.post("/google", summary="Google登录")
async def google_login(
    request: GoogleLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """Google OAuth登录"""
    from shared.core.config import settings
    
    # 检查是否启用Google OAuth
    if not settings.is_google_oauth_enabled():
        raise SystemSettingMissingException(
            internal_message="Google OAuth is not enabled"
        )
    
    try:
        google_service = GoogleAuthService()
    except ValueError as e:
        raise SystemSettingMissingException(
            internal_message=str(e)
        )
    
    try:
        user = await google_service.authenticate_user(db, request.id_token)
        if not user:
            raise AuthException(
                user_message="Google认证失败",
                internal_message="Google user not found"
            )
        
        # 生成JWT令牌 - 使用FastAPI Users的JWT策略
        from app.core.jwt import jwt_strategy
        access_token = await jwt_strategy.write_token(user)
        
        return OAuthLoginResponse(
            access_token=access_token,
            token_type="bearer",
            user_info={
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "avatar_url": user.avatar_url,
                "user_type": user.user_type,
                "credits_balance": user.credits_balance
            }
        )
        
    except Exception as e:
        raise AuthException(
            user_message=f"Google登录失败: {str(e)}",
            internal_message=f"Google login failed: {str(e)}"
        )


@router.post("/apple", summary="Apple登录")
async def apple_login(
    request: AppleLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """Apple OAuth登录"""
    from shared.core.config import settings
    
    # 检查是否启用Apple OAuth
    if not settings.is_apple_oauth_enabled():
        raise SystemSettingMissingException(
            internal_message="Apple OAuth is not enabled"
        )
    
    try:
        apple_service = AppleAuthService()
    except ValueError as e:
        raise SystemSettingMissingException(
            internal_message=str(e)
        )
    
    try:
        user = await apple_service.authenticate_user(db, request.id_token)
        if not user:
            raise AuthException(
                user_message="Apple认证失败",
                internal_message="Apple user not found"
            )
        
        # 生成JWT令牌 - 使用FastAPI Users的JWT策略
        from app.core.jwt import jwt_strategy
        access_token = await jwt_strategy.write_token(user)
        
        return OAuthLoginResponse(
            access_token=access_token,
            token_type="bearer",
            user_info={
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "avatar_url": user.avatar_url,
                "user_type": user.user_type,
                "credits_balance": user.credits_balance
            }
        )
        
    except Exception as e:
        raise AuthException(
            user_message=f"Apple登录失败: {str(e)}",
            internal_message=f"Apple login failed: {str(e)}"
        )


@router.post("/github", summary="GitHub登录")
async def github_login(
    request: GitHubLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """GitHub OAuth登录"""
    from shared.core.config import settings
    
    # 检查是否启用GitHub OAuth
    if not settings.is_github_oauth_enabled():
        raise SystemSettingMissingException(
            internal_message="GitHub OAuth is not enabled"
        )
    
    try:
        github_service = GitHubAuthService()
    except ValueError as e:
        raise SystemSettingMissingException(
            internal_message=str(e)
        )
    
    try:
        user = await github_service.authenticate_user(db, request.code)
        if not user:
            raise AuthException(
                user_message="GitHub认证失败",
                internal_message="GitHub user not found"
            )
        
        # 生成JWT令牌 - 使用FastAPI Users的JWT策略
        from app.core.jwt import jwt_strategy
        access_token = await jwt_strategy.write_token(user)
        
        return OAuthLoginResponse(
            access_token=access_token,
            token_type="bearer",
            user_info={
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "avatar_url": user.avatar_url,
                "user_type": user.user_type,
                "credits_balance": user.credits_balance
            }
        )
        
    except Exception as e:
        raise AuthException(
            user_message=f"GitHub登录失败: {str(e)}",
            internal_message=f"GitHub login failed: {str(e)}"
        )
