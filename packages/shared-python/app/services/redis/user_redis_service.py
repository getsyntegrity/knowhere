"""
用户相关Redis服务
"""
from typing import Dict, Any, Optional, List
from loguru import logger
from app.services.redis.redis_service import RedisService
from app.utils.redis_key_builder import redis_key_builder, RedisKeyType


class UserRedisService:
    """用户相关Redis服务"""
    
    def __init__(self, redis_service: RedisService):
        self.redis = redis_service
    
    async def save_user_config(self, user_id: str, config: Dict[str, Any]) -> bool:
        """保存用户配置"""
        try:
            config_key = redis_key_builder.user_config(user_id)
            await self.redis.set(config_key, config, ttl=redis_key_builder.get_key_ttl(RedisKeyType.USER))
            
            # 更新用户活动时间
            await self.update_user_activity(user_id)
            
            logger.info(f"用户 {user_id} 配置保存成功")
            return True
        except Exception as e:
            logger.error(f"保存用户 {user_id} 配置失败: {e}")
            return False
    
    async def get_user_config(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户配置"""
        try:
            config_key = redis_key_builder.user_config(user_id)
            config = await self.redis.get(config_key)
            return config
        except Exception as e:
            logger.error(f"获取用户 {user_id} 配置失败: {e}")
            return None
    
    async def update_user_session(self, user_id: str, session_data: Dict[str, Any]) -> bool:
        """更新用户会话"""
        try:
            session_key = redis_key_builder.user_session(user_id)
            await self.redis.set(session_key, session_data, ttl=redis_key_builder.get_key_ttl(RedisKeyType.SESSION))
            
            # 添加到在线用户集合
            online_users_key = redis_key_builder.set_online_users()
            await self.redis.sadd(online_users_key, user_id)
            await self.redis.expire(online_users_key, redis_key_builder.get_key_ttl(RedisKeyType.SET))
            
            logger.debug(f"用户 {user_id} 会话更新成功")
            return True
        except Exception as e:
            logger.error(f"更新用户 {user_id} 会话失败: {e}")
            return False
    
    async def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """获取用户会话"""
        try:
            session_key = redis_key_builder.user_session(user_id)
            session = await self.redis.get(session_key)
            return session
        except Exception as e:
            logger.error(f"获取用户 {user_id} 会话失败: {e}")
            return None
    
    async def update_user_activity(self, user_id: str, activity: str = "active") -> bool:
        """更新用户活动"""
        try:
            activity_key = redis_key_builder.user_activity(user_id)
            activity_data = {
                "activity": activity,
                "timestamp": self._get_current_timestamp(),
                "user_id": user_id
            }
            await self.redis.hset(activity_key, mapping=activity_data)
            await self.redis.expire(activity_key, redis_key_builder.get_key_ttl(RedisKeyType.USER))
            
            # 添加到活跃用户集合
            active_users_key = redis_key_builder.set_active_users()
            await self.redis.sadd(active_users_key, user_id)
            await self.redis.expire(active_users_key, redis_key_builder.get_key_ttl(RedisKeyType.SET))
            
            logger.debug(f"用户 {user_id} 活动更新: {activity}")
            return True
        except Exception as e:
            logger.error(f"更新用户 {user_id} 活动失败: {e}")
            return False
    
    async def get_user_activity(self, user_id: str) -> Dict[str, Any]:
        """获取用户活动"""
        try:
            activity_key = redis_key_builder.user_activity(user_id)
            activity = await self.redis.hgetall(activity_key)
            return activity
        except Exception as e:
            logger.error(f"获取用户 {user_id} 活动失败: {e}")
            return {}
    
    async def set_user_permissions(self, user_id: str, permissions: List[str]) -> bool:
        """设置用户权限"""
        try:
            permissions_key = redis_key_builder.user_permissions(user_id)
            permissions_data = {
                "permissions": permissions,
                "timestamp": self._get_current_timestamp()
            }
            await self.redis.set(permissions_key, permissions_data, ttl=redis_key_builder.get_key_ttl(RedisKeyType.USER))
            
            logger.info(f"用户 {user_id} 权限设置成功")
            return True
        except Exception as e:
            logger.error(f"设置用户 {user_id} 权限失败: {e}")
            return False
    
    async def get_user_permissions(self, user_id: str) -> List[str]:
        """获取用户权限"""
        try:
            permissions_key = redis_key_builder.user_permissions(user_id)
            permissions_data = await self.redis.get(permissions_key)
            
            if permissions_data and isinstance(permissions_data, dict):
                return permissions_data.get("permissions", [])
            return []
        except Exception as e:
            logger.error(f"获取用户 {user_id} 权限失败: {e}")
            return []
    
    async def increment_user_requests(self, user_id: str) -> int:
        """增加用户请求计数"""
        try:
            counter_key = redis_key_builder.counter_user_requests(user_id)
            count = await self.redis.incr(counter_key)
            await self.redis.expire(counter_key, redis_key_builder.get_key_ttl(RedisKeyType.COUNTER))
            return count
        except Exception as e:
            logger.error(f"增加用户 {user_id} 请求计数失败: {e}")
            return 0
    
    async def get_user_requests_count(self, user_id: str) -> int:
        """获取用户请求计数"""
        try:
            counter_key = redis_key_builder.counter_user_requests(user_id)
            count = await self.redis.get(counter_key, 0)
            return int(count)
        except Exception as e:
            logger.error(f"获取用户 {user_id} 请求计数失败: {e}")
            return 0
    
    async def get_online_users(self) -> List[str]:
        """获取在线用户列表"""
        try:
            online_users_key = redis_key_builder.set_online_users()
            users = await self.redis.smembers(online_users_key)
            return list(users)
        except Exception as e:
            logger.error(f"获取在线用户列表失败: {e}")
            return []
    
    async def get_active_users(self) -> List[str]:
        """获取活跃用户列表"""
        try:
            active_users_key = redis_key_builder.set_active_users()
            users = await self.redis.smembers(active_users_key)
            return list(users)
        except Exception as e:
            logger.error(f"获取活跃用户列表失败: {e}")
            return []
    
    async def user_logout(self, user_id: str) -> bool:
        """用户登出"""
        try:
            # 从在线用户集合移除
            online_users_key = redis_key_builder.set_online_users()
            await self.redis.srem(online_users_key, user_id)
            
            # 删除会话数据
            session_key = redis_key_builder.user_session(user_id)
            await self.redis.delete(session_key)
            
            # 更新活动状态
            await self.update_user_activity(user_id, "logout")
            
            logger.info(f"用户 {user_id} 登出成功")
            return True
        except Exception as e:
            logger.error(f"用户 {user_id} 登出失败: {e}")
            return False
    
    async def cleanup_user_data(self, user_id: str) -> bool:
        """清理用户数据"""
        try:
            # 删除所有相关键
            keys_to_delete = [
                redis_key_builder.user_config(user_id),
                redis_key_builder.user_session(user_id),
                redis_key_builder.user_activity(user_id),
                redis_key_builder.user_permissions(user_id),
                redis_key_builder.counter_user_requests(user_id)
            ]
            
            await self.redis.delete(*keys_to_delete)
            
            # 从集合中移除
            online_users_key = redis_key_builder.set_online_users()
            active_users_key = redis_key_builder.set_active_users()
            await self.redis.srem(online_users_key, user_id)
            await self.redis.srem(active_users_key, user_id)
            
            logger.info(f"用户 {user_id} 数据清理完成")
            return True
        except Exception as e:
            logger.error(f"清理用户 {user_id} 数据失败: {e}")
            return False
    
    def _get_current_timestamp(self) -> str:
        """获取当前时间戳"""
        import time
        return str(int(time.time()))
