"""
FastAPI Users 用户管理器配置
"""
from typing import Optional

from shared.core.config import settings
from shared.core.database import get_db
from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from sqlalchemy.ext.asyncio import AsyncSession


class UserManager(UUIDIDMixin, BaseUserManager):
    """用户管理器"""
    
    reset_password_token_secret = settings.SECRET_KEY
    verification_token_secret = settings.SECRET_KEY
    
    async def authenticate(
        self, 
        credentials, 
        request: Optional[Request] = None
    ):
        """重写认证方法以支持email登录"""
        from shared.models.database.user import User
        from loguru import logger
        from sqlalchemy import or_, select
        
        try:
            # 获取用户名和密码 - credentials是OAuth2PasswordRequestForm对象
            username = credentials.username
            password = credentials.password
            
            logger.info(f"尝试认证用户: {username}")
            
            if not username or not password:
                logger.warning("用户名或密码为空")
                return None
            
            # 通过username或email查找用户
            query = select(User).where(
                or_(
                    User.username == username,
                    User.email == username
                )
            )
            
            result = await self.user_db.session.execute(query)
            user = result.scalar_one_or_none()
            
            if not user:
                logger.warning(f"用户不存在: {username}")
                return None
            
            logger.info(f"找到用户: {user.email}, 开始验证密码")
            
            # 验证密码
            verified, updated_password_hash = self.password_helper.verify_and_update(password, user.hashed_password)
            if not verified:
                logger.warning(f"密码验证失败: {username}")
                return None
            
            # 检查用户是否激活
            if not user.is_active:
                logger.warning(f"用户未激活: {username}")
                return None
            
            logger.info(f"用户认证成功: {username}")
            return user
            
        except Exception as e:
            logger.error(f"认证过程中发生错误: {e}", exc_info=True)
            return None
    
    async def on_after_login(
        self, 
        user, 
        request: Optional[Request] = None,
        response: Optional[Request] = None,
    ):
        """登录后处理"""
        print(f"用户 {user.email} 已登录")
    
    async def on_after_register(
        self, 
        user, 
        request: Optional[Request] = None
    ):
        """注册后处理"""
        print(f"用户 {user.email} 已注册")
        
        # 创建Free订阅和赠送初始Credits
        await self._setup_new_user_subscription(user)
    
    async def _setup_new_user_subscription(self, user):
        """为新用户设置Free订阅和初始Credits"""
        try:
            from shared.core.config import settings
            from shared.core.database import get_db_context
            from app.services.billing.credits_service import CreditsService
            from app.repositories.subscription_repository import \
                SubscriptionRepository
            from loguru import logger

            # 获取初始Credits数量
            initial_credits = getattr(settings, 'FREE_PLAN_INITIAL_CREDITS', 100)
            
            async with get_db_context() as db:
                # 创建Free订阅
                subscription_repo = SubscriptionRepository()
                from datetime import datetime
                subscription_data = {
                    "user_id": str(user.id),
                    "plan_type": "free",
                    "status": "active",
                    "start_date": datetime.utcnow()
                }
                subscription = await subscription_repo.create(db, subscription_data)
                
                if subscription:
                    logger.info(f"为用户 {user.id} 创建Free订阅成功")
                    
                    # 赠送初始Credits (use service for proper transaction logging)
                    credits_service = CreditsService()
                    await credits_service.add_credits(
                        session=db,
                        user_id=str(user.id),
                        amount=initial_credits,
                        reason=f"新用户注册赠送 {initial_credits} Credits",
                        transaction_type="initial_grant"
                    )
                    
                    # Explicit commit since repository no longer auto-commits
                    await db.commit()
                    
                    logger.info(f"为用户 {user.id} 赠送 {initial_credits} Credits成功")
                    
                    # 发送欢迎邮件
                    await self._send_welcome_email(user, db=db)
                else:
                    logger.error(f"为用户 {user.id} 创建Free订阅失败")
                    
        except Exception as e:
            from loguru import logger
            logger.error(f"设置新用户订阅失败: {e}")
            # 不抛出异常，避免影响用户注册流程
    
    async def _send_welcome_email(self, user, db=None):
        """发送欢迎邮件"""
        try:
            from app.services.email import EmailService
            email_service = EmailService()
            
            await email_service.send_welcome_email(
                user_email=user.email,
                user_name=getattr(user, 'full_name', None) or user.email,
                db=db,
                user_id=str(user.id) if user.id else None
            )
            
            logger.info(f"欢迎邮件已发送给用户 {user.email}")
            
        except Exception as e:
            logger.error(f"发送欢迎邮件失败: {e}")
            # 不抛出异常，避免影响用户注册流程
    
    async def on_after_update(
        self, 
        user, 
        update_dict: dict,
        request: Optional[Request] = None
    ):
        """更新后处理"""
        print(f"用户 {user.email} 已更新")

async def get_user_db(session: AsyncSession = Depends(get_db)):
    """获取用户数据库会话"""
    from shared.models.database.user import User
    yield SQLAlchemyUserDatabase(session, User)

async def get_user_manager(user_db=Depends(get_user_db)):
    """获取用户管理器"""
    yield UserManager(user_db)
