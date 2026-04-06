"""
API Key 管理服务
"""
import asyncio
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from shared.models.database.api_key import APIKey
from app.repositories.api_key_repository import APIKeyRepository
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from shared.core.exceptions.domain_exceptions import ValidationException, NotFoundException, KnowhereException, APIKeyOperationException
from shared.core.database import get_db_context
from shared.core.config import redis_pool_manager
from app.services.rate_limit.identity_cache import identity_cache


@dataclass(frozen=True)
class APIKeyIdentity:
    """Resolved identity for a validated API key."""

    user_id: str
    enabled_modules: tuple[str, ...]


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
            raise ValidationException(
                user_message="Maximum API Key limit reached (10)",
                violations=[{"field": "api_keys", "description": "User has reached the maximum API Key limit"}]
            )
        
        existing_key = await self.repository.get_by_user_and_name(session, user_id, name)
        if existing_key:
            raise ValidationException(
                user_message="API Key name already exists",
                violations=[{"field": "name", "description": f"An API Key with name '{name}' already exists"}]
            )
        
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

        return api_key
    
    async def validate_api_key(self, session: AsyncSession, api_key: str) -> Optional[str]:
        """Validate API key against DB, return user_id or None."""
        identity = await self.validate_api_key_identity(session, api_key)
        return identity.user_id if identity is not None else None

    async def validate_api_key_identity(
        self,
        session: AsyncSession,
        api_key: str,
    ) -> Optional[APIKeyIdentity]:
        """Validate API key and return the authenticated identity."""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        api_key_record = await self.repository.get_by_key_hash(session, key_hash)

        if not api_key_record or not api_key_record.is_valid():
            return None

        self._schedule_last_used_update(str(api_key_record.id))

        enabled_modules = tuple(api_key_record.enabled_modules or ["all"])
        return APIKeyIdentity(
            user_id=str(api_key_record.user_id),
            enabled_modules=enabled_modules,
        )
    
    async def revoke_api_key(self, session: AsyncSession, api_key_id: str, user_id: str) -> bool:
        """撤销API Key（直接删除）"""
        logger.info(f"撤销API密钥: api_key_id={api_key_id}, user_id={user_id}")
        
        # 1. 验证API Key属于该用户
        api_key = await self.repository.get_by_id(session, api_key_id)
        
        if not api_key:
            logger.warning("API密钥不存在")
            raise NotFoundException(
                resource="APIKey",
                resource_id=api_key_id,
                internal_message="API Key not found",
            )
            
        if str(api_key.user_id) != user_id:
            logger.warning(f"用户ID不匹配: api_key.user_id={api_key.user_id}, user_id={user_id}")
            raise NotFoundException(
                resource="APIKey",
                resource_id=api_key_id,
                internal_message="API Key not found or does not belong to user",
            )
        
        # 2. 直接删除API Key
        success = await self.repository.delete_by_id(session, api_key_id)
        logger.info(f"删除结果: {success}")
        
        # 3. 提交事务
        if success:
            await session.commit()
            logger.info("事务已提交")
            await self._invalidate_revoked_api_key_cache_best_effort(
                user_id=user_id,
                key_hash=api_key.key_hash,
            )
        
        return success

    async def _invalidate_revoked_api_key_cache_best_effort(
        self,
        user_id: str,
        key_hash: str,
    ) -> None:
        """Best-effort cache invalidation after a revoke has already been committed."""
        try:
            await identity_cache.invalidate_apikey(
                redis_pool_manager.get_redis_service(),
                user_id,
                key_hash,
            )
        except Exception as err:
            logger.warning(f"Failed to invalidate revoked API key cache (ignored): {err}")
    
    async def list_user_api_keys(self, session: AsyncSession, user_id: str) -> List[dict]:
        """获取用户API Key列表（有效期内的，包含禁用的）"""
        api_keys = await self.repository.get_unexpired_by_user_id(session, user_id)
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
        api_key = await self.repository.get_by_id(session, api_key_id)
        if not api_key or api_key.user_id != user_id:
            raise NotFoundException(
                resource="APIKey",
                resource_id=api_key_id,
                internal_message="API Key not found or does not belong to user"
            )
        
        # 2. 生成新的API Key (sk_ + UUID的32位字符串，不包含连字符)
        new_api_key = f"sk_{str(uuid.uuid4()).replace('-', '')}"
        new_key_hash = hashlib.sha256(new_api_key.encode()).hexdigest()
        new_key_mask = self._mask_api_key(new_api_key)
        
        # 3. 更新数据库
        from sqlalchemy import update
        from shared.models.database.api_key import APIKey
        await session.execute(
            update(APIKey)
            .where(APIKey.id == api_key_id)
            .values(key_hash=new_key_hash, key_mask=new_key_mask, updated_at=datetime.utcnow())
        )
        await session.commit()
        
        # 4. 更新缓存
        await identity_cache.invalidate_apikey(
            redis_pool_manager.get_redis_service(),
            user_id,
            api_key.key_hash,
        )
        
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
    
    def _schedule_last_used_update(self, api_key_id: str) -> None:
        """Schedule a best-effort background update for api_keys.last_used_at."""
        try:
            asyncio.create_task(
                self._update_last_used_best_effort(api_key_id),
                name=f"api_key_last_used:{api_key_id}",
            )
        except Exception as e:
            logger.warning(f"Failed to schedule API key last-used update (ignored): {e}")

    async def _update_last_used_best_effort(self, api_key_id: str) -> None:
        """Best-effort async update; failures are logged but never propagated."""
        try:
            async with get_db_context() as db:
                await self.repository.update_last_used(db, api_key_id)
        except Exception as e:
            logger.warning(f"Failed to update API key last-used time (ignored): {e}")
    
    async def get_api_key(self, session: AsyncSession, user_id: str, api_key_id: str) -> Optional[APIKey]:
        """获取单个API Key"""
        try:
            api_key = await self.repository.get(session, api_key_id)
            if api_key and api_key.user_id == user_id:
                return api_key
            return None
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"获取API Key失败: {e}")
            raise APIKeyOperationException(
                internal_message=f"获取API Key失败: {str(e)}",
                original_exception=e
            )
    
    async def toggle_api_key(self, session: AsyncSession, user_id: str, api_key_id: str) -> bool:
        """启用/禁用API Key"""
        try:
            api_key = await self.repository.get(session, api_key_id)
            if not api_key or str(api_key.user_id) != user_id:
                return False
            
            api_key.is_active = not api_key.is_active
            await session.commit()
            await session.refresh(api_key)

            if not api_key.is_active:
                await identity_cache.invalidate_apikey(
                    redis_pool_manager.get_redis_service(),
                    user_id,
                    api_key.key_hash,
                )
            
            logger.info(f"API Key状态切换成功: {api_key_id}, 新状态: {api_key.is_active}")
            return True
        except KnowhereException:
            raise
        except Exception as e:
            logger.error(f"切换API Key状态失败: {e}")
            await session.rollback()
            raise APIKeyOperationException(
                internal_message=f"切换API Key状态失败: {str(e)}",
                original_exception=e
            )
