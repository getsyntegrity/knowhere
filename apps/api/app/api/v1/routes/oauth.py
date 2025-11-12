"""
OAuth 认证 API
"""
from uuid import UUID

from app.core.database import get_db
from app.core.jwt import auth_backend
from app.core.users import get_user_manager
from app.models.database.user import User
from app.models.schemas.oauth import (AppleLoginRequest, GitHubLoginRequest,
                                      GoogleLoginRequest, OAuthLoginResponse)
from app.services.auth.apple_auth_service import AppleAuthService
from app.services.auth.github_auth_service import GitHubAuthService
from app.services.auth.google_auth_service import GoogleAuthService
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_users import FastAPIUsers
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
    google_service = GoogleAuthService()
    
    try:
        user = await google_service.authenticate_user(db, request.id_token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google认证失败"
            )
        
        # 生成JWT令牌 - 使用FastAPI Users的JWT策略
        from app.core.jwt import jwt_strategy
        access_token = jwt_strategy.create_access_token({"sub": str(user.id)})
        
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google登录失败: {str(e)}"
        )


@router.post("/apple", summary="Apple登录")
async def apple_login(
    request: AppleLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """Apple OAuth登录"""
    apple_service = AppleAuthService()
    
    try:
        user = await apple_service.authenticate_user(db, request.id_token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Apple认证失败"
            )
        
        # 生成JWT令牌 - 使用FastAPI Users的JWT策略
        from app.core.jwt import jwt_strategy
        access_token = jwt_strategy.create_access_token({"sub": str(user.id)})
        
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Apple登录失败: {str(e)}"
        )


@router.post("/github", summary="GitHub登录")
async def github_login(
    request: GitHubLoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """GitHub OAuth登录"""
    github_service = GitHubAuthService()
    
    try:
        user = await github_service.authenticate_user(db, request.code)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitHub认证失败"
            )
        
        # 生成JWT令牌 - 使用FastAPI Users的JWT策略
        from app.core.jwt import jwt_strategy
        access_token = jwt_strategy.create_access_token({"sub": str(user.id)})
        
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"GitHub登录失败: {str(e)}"
        )
