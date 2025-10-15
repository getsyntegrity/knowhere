from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Union
from loguru import logger

from app.core.database import get_db
from app.core.permissions import current_user
from app.core.jwt import auth_backend
from app.core.users import get_user_manager, UserManager
from app.models.database.user import User
from app.models.schemas.user import UserResponse
# 延迟导入以避免循环导入
# from app.services.redis import RedisService, RedisServiceFactory
from app.services.auth.api_key_service import APIKeyService

# 保持向后兼容的认证函数
async def get_current_user(
        user: User = Depends(current_user)
) -> UserResponse:
    """
    获取当前用户 - 使用 FastAPI Users
    """
    return UserResponse.model_validate(user)

async def get_redis_service():
    """
    依赖函数：获取Redis服务实例
    """
    from app.services.redis import RedisServiceFactory
    return RedisServiceFactory.get_service()

async def get_redis_service_factory():
    """
    依赖函数：获取Redis服务工厂实例
    """
    from app.services.redis import RedisServiceFactory
    return RedisServiceFactory

# 添加get_current_user别名，用于向后兼容
# get_current_user 已经在上面定义了

# API Key认证相关依赖
async def get_current_user_by_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    通过API Key获取当前用户
    """
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return None
    
    api_key_service = APIKeyService()
    try:
        user = await api_key_service.validate_api_key(db, api_key)
        return user
    except Exception:
        return None

async def get_current_user_by_jwt(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    通过JWT获取当前用户
    使用FastAPI Users标准实现
    """
    try:
        # 检查Authorization头部
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None
        
        token = auth_header.split(" ")[1]
        if not token:
            return None
        
        # 使用FastAPI Users的JWT策略验证token
        strategy = auth_backend.get_strategy()
        
        # 创建用户管理器实例
        from app.core.users import get_user_db
        user_db = await anext(get_user_db(db))
        user_manager = UserManager(user_db)
        
        payload = await strategy.read_token(token, user_manager)
        
        if not payload:
            logger.debug("JWT token验证失败：无效的token")
            return None
        
        # payload应该是字典，包含JWT的claims
        if isinstance(payload, dict):
            user_id = payload.get("sub")
        else:
            # 如果payload是User对象，直接返回
            if hasattr(payload, 'id'):
                user = payload
                if not user.is_active:
                    logger.debug(f"JWT token验证失败：用户未激活 {user.id}")
                    return None
                logger.debug(f"JWT认证成功：用户 {user.email}")
                return user
            else:
                logger.debug("JWT token验证失败：无效的payload格式")
                return None
        
        if not user_id:
            logger.debug("JWT token验证失败：缺少用户ID")
            return None
        
        # 获取用户
        user = await user_manager.get(user_id)
        if not user:
            logger.debug(f"JWT token验证失败：用户不存在 {user_id}")
            return None
        
        # 检查用户是否激活
        if not user.is_active:
            logger.debug(f"JWT token验证失败：用户未激活 {user_id}")
            return None
        
        logger.debug(f"JWT认证成功：用户 {user.email}")
        return user
        
    except Exception as e:
        logger.debug(f"JWT认证过程中发生错误: {e}")
        return None

async def get_current_user_dual_auth(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    双重认证：JWT + API Key
    优先使用JWT，如果JWT失败则尝试API Key
    使用FastAPI Users标准实现
    """
    # 1. 尝试JWT认证
    user = await get_current_user_by_jwt(request, db)
    if user:
        return user
    
    # 2. 尝试API Key认证
    user = await get_current_user_by_api_key(request, db)
    if user:
        logger.debug(f"API Key认证成功：用户 {user.email}")
        return user
    
    # 3. 认证失败
    logger.warning(f"双重认证失败：请求来源 {request.client.host if request.client else 'unknown'}")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please provide valid JWT token or API Key."
    )

async def require_api_key_auth(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    要求API Key认证
    """
    user = await get_current_user_by_api_key(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key authentication required"
        )
    return user

async def get_current_user_with_auth_type(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> tuple[User, str]:
    """
    获取当前用户和认证类型
    返回: (user, auth_type) 其中 auth_type 为 "jwt" 或 "api_key"
    使用FastAPI Users标准实现
    """
    # 1. 尝试JWT认证
    user = await get_current_user_by_jwt(request, db)
    if user:
        return user, "jwt"
    
    # 2. 尝试API Key认证
    user = await get_current_user_by_api_key(request, db)
    if user:
        return user, "api_key"
    
    # 3. 认证失败
    logger.warning(f"认证失败：无法确定认证类型，请求来源 {request.client.host if request.client else 'unknown'}")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please provide valid JWT token or API Key."
    )

# 新增：仅JWT认证的依赖
async def require_jwt_auth(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    要求JWT认证
    如果JWT认证失败，抛出异常
    """
    user = await get_current_user_by_jwt(request, db)
    if not user:
        logger.warning(f"JWT认证失败：请求来源 {request.client.host if request.client else 'unknown'}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT authentication required. Please provide valid JWT token."
        )
    return user

# 新增：认证类型检查装饰器
def require_auth_type(auth_type: str):
    """
    认证类型检查装饰器
    auth_type: "jwt", "api_key", 或 "any"
    """
    def auth_checker(
        request: Request,
        db: AsyncSession = Depends(get_db)
    ) -> User:
        if auth_type == "jwt":
            return require_jwt_auth(request, db)
        elif auth_type == "api_key":
            return require_api_key_auth(request, db)
        elif auth_type == "any":
            return get_current_user_dual_auth(request, db)
        else:
            raise ValueError(f"不支持的认证类型: {auth_type}")
    
    return auth_checker

# 新增：获取认证信息的工具函数
async def get_auth_info(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    获取认证信息
    返回包含用户信息和认证类型的字典
    """
    try:
        user, auth_type = await get_current_user_with_auth_type(request, db)
        return {
            "user": user,
            "auth_type": auth_type,
            "is_authenticated": True,
            "user_id": str(user.id),
            "email": user.email,
            "username": user.username
        }
    except HTTPException:
        return {
            "user": None,
            "auth_type": None,
            "is_authenticated": False,
            "user_id": None,
            "email": None,
            "username": None
        }