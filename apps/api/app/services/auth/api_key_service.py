"""
API Key 管理服务
"""
import secrets
import hashlib
import uuid
from typing import Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database.api_key import APIKey
from app.models.database.user import User
from app.repositories.api_key_repository import APIKeyRepository
from app.core.database import get_db


class APIKeyService:
    """API Key管理服务"""
    
    def __init__(self):
        self.repository = APIKeyRepository()
    
    def _mask_api_key(self, api_key: str) -> str:
        """掩码API密钥，只显示前8位和后4位"""
        if not api_key or len(api_key) < 12:
            return api_key
        return api_key[:8] + "•" * (len(api_key) - 12) + api_key[-4:]
    
    async def create_api_key(
        self, 
        session: AsyncSession,
        user_id: str, 
        name: str, 
        enabled_modules: Optional[List[str]] = None,
        expires_at: Optional[datetime] = None
    ) -> str:
        """创建API Key"""
        # 1. 检查用户API Key数量限制
        key_count = await self.repository.count_by_user(session, user_id)
        if key_count >= 10:  # 限制每个用户最多10个API Key
            raise ValueError("API Key数量已达上限")
        
        # 2. 检查名称是否重复
        existing_key = await self.repository.get_by_user_and_name(session, user_id, name)
        if existing_key:
            raise ValueError("API Key名称已存在")
        
        # 3. 生成安全的API Key (sk_ + UUID的32位字符串，不包含连字符)
        api_key = f"sk_{str(uuid.uuid4()).replace('-', '')}"
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        key_mask = self._mask_api_key(api_key)
        
        # 4. 存储到数据库
        api_key_record = APIKey(
            user_id=user_id,
            key_hash=key_hash,
            key_mask=key_mask,
            name=name,
            enabled_modules=enabled_modules or ["all"],  # 默认启用所有模块
            expires_at=expires_at
        )
        
        await self.repository.create(session, api_key_record)
        
        # 5. 缓存到Redis（可选）
        await self._cache_api_key(api_key, user_id)
        
        return api_key
    
    async def validate_api_key(self, session: AsyncSession, api_key: str) -> Optional[User]:
        """验证API Key"""
        # 1. 从缓存获取（如果实现了缓存）
        user_id = await self._get_cached_user_id(api_key)
        if user_id:
            return await self._get_user_by_id(session, user_id)
        
        # 2. 从数据库获取
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        api_key_record = await self.repository.get_by_key_hash(session, key_hash)
        
        if not api_key_record or not api_key_record.is_valid():
            return None
        
        # 3. 更新最后使用时间
        await self.repository.update_last_used(session, api_key_record.id)
        
        # 4. 缓存结果
        await self._cache_api_key(api_key, str(api_key_record.user_id))
        
        return await self._get_user_by_id(session, str(api_key_record.user_id))
    
    async def revoke_api_key(self, session: AsyncSession, api_key_id: str, user_id: str) -> bool:
        """撤销API Key"""
        print(f"撤销API密钥: api_key_id={api_key_id}, user_id={user_id}")
        
        # 1. 验证API Key属于该用户
        api_key = await self.repository.get_by_id(session, api_key_id)
        print(f"找到API密钥: {api_key}")
        
        if not api_key:
            print("API密钥不存在")
            return False
            
        if str(api_key.user_id) != user_id:
            print(f"用户ID不匹配: api_key.user_id={api_key.user_id}, user_id={user_id}")
            return False
        
        # 2. 标记为已撤销
        success = await self.repository.deactivate(session, api_key_id)
        print(f"停用结果: {success}")
        
        # 3. 提交事务
        if success:
            await session.commit()
            print("事务已提交")
            # 4. 清理缓存
            await self._remove_cached_api_key(api_key_id)
        
        return success
    
    async def list_user_api_keys(self, session: AsyncSession, user_id: str) -> List[dict]:
        """获取用户API Key列表"""
        api_keys = await self.repository.get_active_by_user_id(session, user_id)
        return [
            {
                "id": str(api_key.id),
                "name": api_key.name,
                "api_key": api_key.key_mask or f"sk_{api_key.id[:8]}••••••••••••••••••••••••••••••••••••••••",  # 返回掩码后的API密钥
                "enabled_modules": api_key.enabled_modules,
                "is_active": api_key.is_active,
                "created_at": api_key.created_at,
                "last_used_at": api_key.last_used_at,
                "expires_at": api_key.expires_at
            }
            for api_key in api_keys
        ]
    
    async def regenerate_api_key(self, session: AsyncSession, api_key_id: str, user_id: str) -> str:
        """重新生成API Key"""
        # 1. 验证API Key属于该用户
        api_key = await self.repository.get_by_id(session, api_key_id)
        if not api_key or api_key.user_id != user_id:
            raise ValueError("API Key不存在或不属于该用户")
        
        # 2. 生成新的API Key (sk_ + UUID的32位字符串，不包含连字符)
        new_api_key = f"sk_{str(uuid.uuid4()).replace('-', '')}"
        new_key_hash = hashlib.sha256(new_api_key.encode()).hexdigest()
        new_key_mask = self._mask_api_key(new_api_key)
        
        # 3. 更新数据库
        from sqlalchemy import update
        await session.execute(
            update(APIKey)
            .where(APIKey.id == api_key_id)
            .values(key_hash=new_key_hash, key_mask=new_key_mask, updated_at=datetime.utcnow())
        )
        await session.commit()
        
        # 4. 更新缓存
        await self._cache_api_key(new_api_key, user_id)
        await self._remove_cached_api_key(api_key_id)
        
        return new_api_key
    
    async def check_module_permission(self, session: AsyncSession, api_key: str, module: str) -> bool:
        """检查API Key是否有访问指定模块的权限"""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        api_key_record = await self.repository.get_by_key_hash(session, key_hash)
        
        if not api_key_record or not api_key_record.is_valid():
            return False
        
        # 如果启用了所有模块或包含指定模块
        enabled_modules = api_key_record.enabled_modules or []
        return "all" in enabled_modules or module in enabled_modules
    
    async def _get_user_by_id(self, session: AsyncSession, user_id: str) -> Optional[User]:
        """根据ID获取用户"""
        from sqlalchemy import select
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def _cache_api_key(self, api_key: str, user_id: str):
        """缓存API Key到Redis"""
        # TODO: 实现Redis缓存
        pass
    
    async def _get_cached_user_id(self, api_key: str) -> Optional[str]:
        """从缓存获取用户ID"""
        # TODO: 实现Redis缓存
        return None
    
    async def _remove_cached_api_key(self, api_key_id: str):
        """从缓存中移除API Key"""
        # TODO: 实现Redis缓存
        pass
    
    async def get_api_key(self, session: AsyncSession, user_id: str, api_key_id: str) -> Optional[APIKey]:
        """获取单个API Key"""
        try:
            api_key = await self.repository.get(session, api_key_id)
            if api_key and api_key.user_id == user_id:
                return api_key
            return None
        except Exception as e:
            logger.error(f"获取API Key失败: {e}")
            raise
    
    async def toggle_api_key(self, session: AsyncSession, user_id: str, api_key_id: str) -> bool:
        """启用/禁用API Key"""
        try:
            api_key = await self.repository.get(session, api_key_id)
            if not api_key or api_key.user_id != user_id:
                return False
            
            api_key.is_active = not api_key.is_active
            await session.commit()
            await session.refresh(api_key)
            
            logger.info(f"API Key状态切换成功: {api_key_id}, 新状态: {api_key.is_active}")
            return True
        except Exception as e:
            logger.error(f"切换API Key状态失败: {e}")
            await session.rollback()
            raise
