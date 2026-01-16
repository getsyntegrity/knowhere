"""
用户管理服务
"""
from typing import Optional

from shared.core.logging import get_logger
from shared.models.database.user import User
from shared.models.schemas.user import UserUpdateRequest
from app.repositories.user_repository import UserRepository
from shared.core.exceptions.DomainExceptions import KnowhereException, WorkerHandlingException
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


class UserService:
    """用户管理服务"""
    
    def __init__(self):
        self.user_repository = UserRepository()
    
    async def get_user_profile(self, session: AsyncSession, user_id: str) -> Optional[User]:
        """获取用户资料"""
        try:
            user = await self.user_repository.get(session, user_id)
            if not user:
                logger.warning(f"用户不存在: {user_id}")
                return None
            return user
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"获取用户资料失败: {e}")
            raise WorkerHandlingException(
                internal_message=f"获取用户资料失败: {str(e)}",
                original_exception=e
            )
    
    async def update_user_profile(
        self, 
        session: AsyncSession, 
        user_id: str, 
        user_update: UserUpdateRequest
    ) -> Optional[User]:
        """更新用户资料"""
        try:
            # 获取现有用户
            user = await self.user_repository.get(session, user_id)
            if not user:
                logger.warning(f"用户不存在: {user_id}")
                return None
            
            # 更新用户信息
            update_data = user_update.model_dump(exclude_unset=True)
            
            # 只更新允许的字段
            allowed_fields = ['username', 'avatar_url', 'phone']
            for field, value in update_data.items():
                if field in allowed_fields and hasattr(user, field):
                    setattr(user, field, value)
            
            # 保存更改
            await session.commit()
            await session.refresh(user)
            
            logger.info(f"用户资料更新成功: {user_id}")
            return user
            
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"更新用户资料失败: {e}")
            await session.rollback()
            raise WorkerHandlingException(
                internal_message=f"更新用户资料失败: {str(e)}",
                original_exception=e
            )
    
    async def delete_user(self, session: AsyncSession, user_id: str) -> bool:
        """删除用户账户"""
        try:
            # 检查用户是否存在
            user = await self.user_repository.get(session, user_id)
            if not user:
                logger.warning(f"用户不存在: {user_id}")
                return False
            
            # 删除用户（级联删除相关数据）
            success = await self.user_repository.delete(session, user_id)
            
            if success:
                logger.info(f"用户删除成功: {user_id}")
            else:
                logger.error(f"用户删除失败: {user_id}")
            
            return success
            
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"删除用户失败: {e}")
            await session.rollback()
            raise WorkerHandlingException(
                internal_message=f"删除用户失败: {str(e)}",
                original_exception=e
            )
    
    async def get_user_by_email(self, session: AsyncSession, email: str) -> Optional[User]:
        """根据邮箱获取用户"""
        try:
            user = await self.user_repository.get_by_field(session, "email", email)
            return user
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"根据邮箱获取用户失败: {e}")
            raise WorkerHandlingException(
                internal_message=f"根据邮箱获取用户失败: {str(e)}",
                original_exception=e
            )
    
    async def get_user_by_username(self, session: AsyncSession, username: str) -> Optional[User]:
        """根据用户名获取用户"""
        try:
            user = await self.user_repository.get_by_field(session, "username", username)
            return user
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"根据用户名获取用户失败: {e}")
            raise WorkerHandlingException(
                internal_message=f"根据用户名获取用户失败: {str(e)}",
                original_exception=e
            )
    
    async def update_user_credits_balance(
        self, 
        session: AsyncSession, 
        user_id: str, 
        credits_amount: int
    ) -> bool:
        """更新用户Credits余额"""
        try:
            user = await self.user_repository.get(session, user_id)
            if not user:
                logger.warning(f"用户不存在: {user_id}")
                return False
            
            # 更新Credits余额
            user.credits_balance = max(0, user.credits_balance + credits_amount)
            await session.commit()
            await session.refresh(user)
            
            logger.info(f"用户Credits余额更新成功: {user_id}, 新余额: {user.credits_balance}")
            return True
            
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"更新用户Credits余额失败: {e}")
            await session.rollback()
            raise WorkerHandlingException(
                internal_message=f"更新用户Credits余额失败: {str(e)}",
                original_exception=e
            )
    
    async def get_user_stats(self, session: AsyncSession, user_id: str) -> dict:
        """获取用户统计信息"""
        try:
            user = await self.user_repository.get(session, user_id)
            if not user:
                return {}
            
            # 统计API Key数量
            api_keys_count = len(user.api_keys) if hasattr(user, 'api_keys') else 0
            
            # 统计订阅数量
            subscriptions_count = len(user.subscriptions) if hasattr(user, 'subscriptions') else 0
            
            # 统计使用日志数量
            usage_logs_count = len(user.usage_logs) if hasattr(user, 'usage_logs') else 0
            
            return {
                "user_id": user_id,
                "credits_balance": user.credits_balance,
                "api_keys_count": api_keys_count,
                "subscriptions_count": subscriptions_count,
                "usage_logs_count": usage_logs_count,
                "user_type": user.user_type,
                "created_at": user.created_at,
                "updated_at": user.updated_at
            }
            
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"获取用户统计信息失败: {e}")
            raise WorkerHandlingException(
                internal_message=f"获取用户统计信息失败: {str(e)}",
                original_exception=e
            )