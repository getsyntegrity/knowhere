"""
FastAPI Users JWT 认证配置
"""
from datetime import timedelta

from shared.core.config import settings
from fastapi_users.authentication import (AuthenticationBackend,
                                          BearerTransport, JWTStrategy)

# JWT 配置
SECRET = settings.SECRET_KEY
LIFETIME = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

# JWT 传输
jwt_transport = BearerTransport(tokenUrl="v1/jwt/login")

# JWT 认证策略
jwt_strategy = JWTStrategy(
    secret=SECRET,
    lifetime_seconds=int(LIFETIME.total_seconds()),
)

# 认证后端
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=jwt_transport,
    get_strategy=lambda: jwt_strategy,
)
