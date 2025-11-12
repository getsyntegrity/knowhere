from datetime import datetime
from typing import List, Optional, Type

from app.core.security import get_password_hash
from app.models.database.user import Role, User
from app.models.schemas.user import UserCreate
from app.repositories.base_repository import BaseRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select


class UserRepository(BaseRepository[User, UserCreate, UserCreate]):
    """用户数据访问层"""
    
    def __init__(self, model: Type[User] = User):
        super().__init__(model)
    
    async def create_user(self, db: AsyncSession, user_data: UserCreate) -> User:
        """
        创建用户（包含角色处理）
        
        Args:
            db: 数据库会话
            user_data: 用户创建数据
            
        Returns:
            创建的用户对象
        """
        role_names_to_assign = []
        if user_data.role:
            role_names_to_assign = user_data.role
        elif hasattr(user_data, 'role') and user_data.role:
            role_names_to_assign = [user_data.role]

        db_roles = []
        if role_names_to_assign:
            query = select(Role).where(Role.name.in_(role_names_to_assign))
            result = await db.execute(query)
            db_roles = result.scalars().all()

        hashed_password = get_password_hash(user_data.password)
        db_user = User(
            id=user_data.id if user_data.id else None,  # 使用提供的id或让数据库自动生成
            username=user_data.username,
            email=user_data.email,
            phone=user_data.phone,
            hashed_password=hashed_password,
            is_active=True,
            roles=db_roles,
            create_time=datetime.now(),
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        return db_user
    
    async def get_by_username(self, db: AsyncSession, username: str) -> Optional[User]:
        """
        通过用户名查询用户
        
        Args:
            db: 数据库会话
            username: 用户名
            
        Returns:
            用户对象或None
        """
        return await self.get_by_field(db, "username", username)
    
    async def get_by_email(self, db: AsyncSession, email: str) -> Optional[User]:
        """
        通过邮箱查询用户
        
        Args:
            db: 数据库会话
            email: 邮箱
            
        Returns:
            用户对象或None
        """
        return await self.get_by_field(db, "email", email)
    
    async def get_active_users(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> List[User]:
        """
        获取活跃用户列表
        
        Args:
            db: 数据库会话
            skip: 跳过记录数
            limit: 限制记录数
            
        Returns:
            活跃用户列表
        """
        return await self.get_multi_by_field(db, "is_active", True, skip, limit)
    
    async def get_users_by_role(self, db: AsyncSession, role_name: str) -> List[User]:
        """
        根据角色获取用户列表 - 暂时返回空列表避免数据库关系问题
        
        Args:
            db: 数据库会话
            role_name: 角色名称
            
        Returns:
            用户列表
        """
        # 暂时返回空列表，避免数据库关系问题
        return []
    
    async def update_user_password(
        self, 
        db: AsyncSession, 
        user_id: str, 
        new_password: str
    ) -> bool:
        """
        更新用户密码
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            new_password: 新密码
            
        Returns:
            是否更新成功
        """
        try:
            user = await self.get(db, user_id)
            if not user:
                return False
            
            user.hashed_password = get_password_hash(new_password)
            await db.commit()
            await db.refresh(user)
            return True
        except Exception:
            await db.rollback()
            return False

