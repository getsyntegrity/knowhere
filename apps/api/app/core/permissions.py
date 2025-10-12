"""
FastAPI Users 权限管理模块
"""
from uuid import UUID
from fastapi import Depends, HTTPException, status
from fastapi_users import FastAPIUsers

from app.core.users import get_user_manager
from app.core.jwt import auth_backend

# 延迟导入以避免循环依赖
def get_fastapi_users():
    from app.models.database.user import User
    return FastAPIUsers[User, UUID](get_user_manager, [auth_backend])

# 创建 FastAPI Users 实例
fastapi_users = get_fastapi_users()

# 获取当前用户依赖
current_user = fastapi_users.current_user()

# 权限检查装饰器
def require_user_type(user_type):
    """要求特定用户类型"""
    def permission_checker(user = Depends(current_user)):
        from app.models.database.user import UserType
        if user.user_type != user_type.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要 {user_type.value} 权限"
            )
        return user
    return permission_checker

# 常用权限依赖
def get_require_admin():
    from app.models.database.user import UserType
    return require_user_type(UserType.ADMIN)

def get_require_superuser():
    from app.models.database.user import UserType
    return require_user_type(UserType.SUPERUSER)

require_admin = get_require_admin()
require_superuser = get_require_superuser()
