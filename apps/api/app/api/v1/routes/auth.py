"""
认证相关 API - 使用 FastAPI Users
"""
from uuid import UUID

from app.core.dependencies import get_current_user_dual_auth
from app.core.jwt import auth_backend
from app.core.permissions import require_admin
from app.core.users import get_user_manager
from shared.models.database.user import User
from shared.models.schemas.user import UserCreate, UserRead, UserUpdate
from fastapi import APIRouter, Depends, Request
from fastapi_users import FastAPIUsers
from shared.core.billing import MicroDollar

router = APIRouter(tags=["Authentication"])

# 使用 FastAPI Users 的路由
fastapi_users = FastAPIUsers[User, UUID](get_user_manager, [auth_backend])

# 注册 FastAPI Users 的路由
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/jwt",
    tags=["auth"]
)

router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    tags=["auth"]
)

router.include_router(
    fastapi_users.get_reset_password_router(),
    prefix="/reset-password",
    tags=["auth"]
)

router.include_router(
    fastapi_users.get_verify_router(UserRead),
    prefix="/verify",
    tags=["auth"]
)

router.include_router(
    fastapi_users.get_users_router(UserRead, UserUpdate),
    prefix="/users",
    tags=["users"]
)


# 自定义路由
@router.get("/me", summary="获取当前用户信息")
async def get_current_user_info(request: Request, user: User = Depends(get_current_user_dual_auth)):
    """获取当前用户信息 - 支持JWT和API Key双重认证"""
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "user_type": user.user_type,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "credits_balance": MicroDollar(user.credits_balance).to_ui_string(),
        "avatar_url": user.avatar_url,
        "phone": user.phone,
        "create_time": user.create_time
    }

@router.post("/renew-token", summary="续期访问令牌")
async def renew_token(user: User = Depends(get_current_user_dual_auth)):
    """续期访问令牌 - 在token有效时获取新的7天token"""
    from app.core.jwt import jwt_strategy

    # 使用JWT策略创建新的token，传入User对象
    new_access_token = await jwt_strategy.write_token(user)
    
    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }

@router.post("/admin-only", summary="管理员专用接口")
async def admin_only_endpoint(user: User = Depends(require_admin)):
    """管理员专用接口示例"""
    return {"message": "管理员访问成功"}