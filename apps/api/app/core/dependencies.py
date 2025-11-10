from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Union, Tuple, Dict, Any
from loguru import logger

from app.core.database import get_db
from app.core.permissions import current_user
from app.core.jwt import auth_backend
from app.core.users import get_user_manager, UserManager
from app.models.database.user import User
from app.models.schemas.user import UserResponse
from app.services.auth.api_key_service import APIKeyService

# ============================================================================
# 工具函数和常量
# ============================================================================

class AuthError(Exception):
    """认证错误基类"""
    pass

class APIKeyAuthError(AuthError):
    """API Key认证错误"""
    pass

class JWTAuthError(AuthError):
    """JWT认证错误"""
    pass

def _extract_bearer_token(auth_header: str) -> Optional[str]:
    """从Authorization头部提取Bearer token"""
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    return auth_header.split(" ", 1)[1] if len(auth_header.split(" ", 1)) > 1 else None

def _is_api_key_format(token: str) -> bool:
    """检查token是否为API Key格式"""
    return token.startswith("sk_")

# ============================================================================
# 基础依赖函数
# ============================================================================

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
    # Redis服务已在共享包中
    from app.services.redis import RedisServiceFactory
    return RedisServiceFactory.get_service()

async def get_redis_service_factory():
    """
    依赖函数：获取Redis服务工厂实例
    """
    # Redis服务已在共享包中
    from app.services.redis import RedisServiceFactory
    return RedisServiceFactory

# ============================================================================
# 认证核心函数
# ============================================================================

async def _authenticate_api_key(request: Request, db: AsyncSession) -> Optional[User]:
    """
    通过API Key认证用户
    支持 Authorization: Bearer sk_xxxx 格式
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    
    token = _extract_bearer_token(auth_header)
    if not token or not _is_api_key_format(token):
        return None
    
    try:
        api_key_service = APIKeyService()
        user = await api_key_service.validate_api_key(db, token)
        logger.debug(f"API Key认证成功：用户 {user.email if user else 'None'}")
        return user
    except Exception as e:
        logger.debug(f"API Key认证失败: {e}")
        return None

async def _authenticate_jwt(request: Request, db: AsyncSession) -> Optional[User]:
    """
    通过JWT认证用户
    只接受标准JWT token，不接受API Key
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    
    token = _extract_bearer_token(auth_header)
    if not token or _is_api_key_format(token):
        return None
    
    try:
        logger.debug("开始JWT认证流程")
        # 使用FastAPI Users的JWT策略验证token
        strategy = auth_backend.get_strategy()
        logger.debug("获取JWT策略成功")
        
        from app.core.users import get_user_db
        logger.debug("开始获取用户数据库会话")
        user_db = await anext(get_user_db(db))
        logger.debug("获取用户数据库会话成功")
        
        user_manager = UserManager(user_db)
        logger.debug("创建用户管理器成功")
        
        logger.debug("开始验证JWT token")
        payload = await strategy.read_token(token, user_manager)
        logger.debug(f"JWT token验证结果: {payload is not None}")
        
        if not payload:
            return None
        
        # 处理payload
        if isinstance(payload, dict):
            user_id = payload.get("sub")
            logger.debug(f"从payload获取用户ID: {user_id}")
            if not user_id:
                return None
            logger.debug("开始获取用户信息")
            user = await user_manager.get(user_id)
            logger.debug(f"获取用户信息结果: {user is not None}")
        else:
            # 如果payload是User对象，直接返回
            user = payload if hasattr(payload, 'id') else None
            logger.debug(f"payload是User对象: {user is not None}")
        
        if not user or not user.is_active:
            logger.debug(f"用户无效或未激活: user={user is not None}, active={user.is_active if user else False}")
            return None
        
        logger.debug(f"JWT认证成功：用户 {user.email}")
        return user
        
    except Exception as e:
        logger.debug(f"JWT认证失败: {e}")
        return None

# ============================================================================
# 公共认证依赖函数
# ============================================================================

async def get_current_user_by_api_key(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    通过API Key获取当前用户
    支持 Authorization: Bearer sk_xxxx 格式
    """
    return await _authenticate_api_key(request, db)

async def get_current_user_by_jwt(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """
    通过JWT获取当前用户
    使用FastAPI Users标准实现
    只接受标准JWT token，不接受API Key
    """
    return await _authenticate_jwt(request, db)

async def get_current_user_dual_auth(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    双重认证：API Key + JWT
    优先使用API Key，如果API Key失败则尝试JWT
    """
    # 1. 优先尝试API Key认证
    user = await _authenticate_api_key(request, db)
    if user:
        return user
    
    # 2. 尝试JWT认证
    user = await _authenticate_jwt(request, db)
    if user:
        return user
    
    # 3. 认证失败
    client_ip = request.client.host if request.client else 'unknown'
    logger.warning(f"双重认证失败：请求来源 {client_ip}")
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
    user = await _authenticate_api_key(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key authentication required"
        )
    return user

async def get_current_user_with_auth_type(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Tuple[User, str]:
    """
    获取当前用户和认证类型
    返回: (user, auth_type) 其中 auth_type 为 "jwt" 或 "api_key"
    """
    # 1. 尝试API Key认证
    user = await _authenticate_api_key(request, db)
    if user:
        return user, "api_key"
    
    # 2. 尝试JWT认证
    user = await _authenticate_jwt(request, db)
    if user:
        return user, "jwt"
    
    # 3. 认证失败
    client_ip = request.client.host if request.client else 'unknown'
    logger.warning(f"认证失败：无法确定认证类型，请求来源 {client_ip}")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please provide valid JWT token or API Key."
    )

# ============================================================================
# 专用认证依赖函数
# ============================================================================

async def require_jwt_auth(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    要求JWT认证
    如果JWT认证失败，抛出异常
    """
    user = await _authenticate_jwt(request, db)
    if not user:
        client_ip = request.client.host if request.client else 'unknown'
        logger.warning(f"JWT认证失败：请求来源 {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT authentication required. Please provide valid JWT token."
        )
    return user

# ============================================================================
# 认证工具函数
# ============================================================================

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

async def get_auth_info(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
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