"""
Redis服务抽象层
"""
import asyncio
import json
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from loguru import logger

from shared.core.config.redis import RedisConfigManager
from shared.core.exceptions.redis_exceptions import (
    RedisConnectionError,
    RedisOperationError,
)
from shared.utils.redis_retry import RedisHealthChecker, RedisRetry


class RedisService:
    """Redis服务抽象层"""
    _KEY_PREFIX: str = "knowhere-api"
    
    def __init__(self, config_manager: Optional[RedisConfigManager] = None):
        if config_manager is None:
            from shared.core.config import settings
            config_manager = RedisConfigManager(settings)
        self.config_manager = config_manager
        self._client: Optional[redis.Redis] = None
        self._health_checker: Optional[RedisHealthChecker] = None
        self._lock = asyncio.Lock()
    
    async def _get_client(self) -> redis.Redis:
        """获取Redis客户端（懒加载）"""
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    try:
                        self._client = redis.from_url(
                            self.config_manager.get_connection_url(),
                            **self.config_manager.get_connection_params()
                        )
                        self._health_checker = RedisHealthChecker(self._client)
                        logger.debug("Redis客户端初始化成功")
                    except Exception as e:
                        raise RedisConnectionError(
                            internal_message=f"Redis client initialization failed: {str(e)}",
                            original_exception=e
                        )
        return self._client
    
    async def _execute_with_retry(self, operation: callable) -> Any:
        """执行Redis操作并支持重试"""
        return await RedisRetry.with_retry(
            operation,
            max_retries=self.config_manager.config.REDIS_MAX_RETRIES,
            base_delay=self.config_manager.config.REDIS_RETRY_DELAY
        )
    
    def _build_key(self, key: str) -> str:
        """构建完整的键名"""
        prefix = self._KEY_PREFIX
        return f"{prefix}:{key}" if not key.startswith(prefix) else key
    
    # ==================== 基础操作 ====================
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None, ex: Optional[int] = None) -> bool:
        """设置键值"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            if isinstance(value, (dict, list)):
                # 使用make_json_safe确保所有复杂类型都能正确序列化
                from shared.utils.json_utils import make_json_safe
                safe_value = make_json_safe(value)
                value = json.dumps(safe_value, ensure_ascii=False)
                logger.debug(f"Redis序列化完成: key={full_key}, 类型={type(value)}")
            
            # 优先使用ex参数，其次使用ttl参数
            expire_time = ex or ttl or self.config_manager.config.REDIS_DEFAULT_TTL
            
            async def _operation():
                return await client.set(full_key, value, ex=expire_time)
            
            result = await self._execute_with_retry(_operation)
            return result
        except Exception as e:
            logger.error(f"Redis SET operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"SET operation failed: {str(e)}",
                operation="SET",
                original_exception=e
            )
    
    async def get(self, key: str, default: Any = None) -> Any:
        """获取键值"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            async def _operation():
                return await client.get(full_key)
            
            result = await self._execute_with_retry(_operation)
            
            if result is None:
                return default
            
            # 尝试解析JSON
            try:
                return json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return result
        except Exception as e:
            logger.error(f"Redis GET operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"GET operation failed: {str(e)}",
                operation="GET",
                original_exception=e
            )
    
    async def delete(self, *keys: str) -> int:
        """删除键"""
        try:
            client = await self._get_client()
            full_keys = [self._build_key(key) for key in keys]
            
            async def _operation():
                return await client.delete(*full_keys)
            
            return await self._execute_with_retry(_operation)
        except Exception as e:
            logger.error(f"Redis DELETE operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"DELETE operation failed: {str(e)}",
                operation="DELETE",
                original_exception=e
            )
    
    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            async def _operation():
                return await client.exists(full_key)
            
            result = await self._execute_with_retry(_operation)
            return bool(result)
        except Exception as e:
            logger.error(f"Redis EXISTS operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"EXISTS operation failed: {str(e)}",
                operation="EXISTS",
                original_exception=e
            )
    
    async def expire(self, key: str, ttl: int) -> bool:
        """设置键过期时间"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            async def _operation():
                return await client.expire(full_key, ttl)
            
            return await self._execute_with_retry(_operation)
        except Exception as e:
            logger.error(f"Redis EXPIRE operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"EXPIRE operation failed: {str(e)}",
                operation="EXPIRE",
                original_exception=e
            )

    async def ttl(self, key: str) -> int:
        """获取键的剩余TTL（秒）"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)

            async def _operation():
                return await client.ttl(full_key)

            result = await self._execute_with_retry(_operation)
            return int(result)
        except Exception as e:
            logger.error(f"Redis TTL operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"TTL operation failed: {str(e)}",
                operation="TTL",
                original_exception=e
            )
    
    # ==================== 列表操作 ====================
    
    async def lpush(self, key: str, *values: Any) -> int:
        """从列表左侧推入元素"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            # 序列化值
            serialized_values = []
            for value in values:
                if isinstance(value, (dict, list)):
                    serialized_values.append(json.dumps(value, ensure_ascii=False))
                else:
                    serialized_values.append(str(value))
            
            async def _operation():
                return await client.lpush(full_key, *serialized_values)
            
            return await self._execute_with_retry(_operation)
        except Exception as e:
            logger.error(f"Redis LPUSH operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"LPUSH operation failed: {str(e)}",
                operation="LPUSH",
                original_exception=e
            )
    
    async def rpush(self, key: str, *values: Any) -> int:
        """从列表右侧推入元素"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            # 序列化值
            serialized_values = []
            for value in values:
                if isinstance(value, (dict, list)):
                    serialized_values.append(json.dumps(value, ensure_ascii=False))
                else:
                    serialized_values.append(str(value))
            
            async def _operation():
                return await client.rpush(full_key, *serialized_values)
            
            return await self._execute_with_retry(_operation)
        except Exception as e:
            logger.error(f"Redis RPUSH operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"RPUSH operation failed: {str(e)}",
                operation="RPUSH",
                original_exception=e
            )
    
    async def lpop(self, key: str) -> Any:
        """从列表左侧弹出元素"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            async def _operation():
                return await client.lpop(full_key)
            
            result = await self._execute_with_retry(_operation)
            
            if result is None:
                return None
            
            # 尝试解析JSON
            try:
                return json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return result
        except Exception as e:
            logger.error(f"Redis LPOP operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"LPOP operation failed: {str(e)}",
                operation="LPOP",
                original_exception=e
            )
    
    async def rpop(self, key: str) -> Any:
        """从列表右侧弹出元素"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            async def _operation():
                return await client.rpop(full_key)
            
            result = await self._execute_with_retry(_operation)
            
            if result is None:
                return None
            
            # 尝试解析JSON
            try:
                return json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return result
        except Exception as e:
            logger.error(f"Redis RPOP operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"RPOP operation failed: {str(e)}",
                operation="RPOP",
                original_exception=e
            )
    
    async def lrange(self, key: str, start: int = 0, end: int = -1) -> List[Any]:
        """获取列表范围内的元素"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            async def _operation():
                return await client.lrange(full_key, start, end)
            
            result = await self._execute_with_retry(_operation)
            
            # 尝试解析每个元素的JSON
            parsed_result = []
            for item in result:
                try:
                    parsed_result.append(json.loads(item))
                except (json.JSONDecodeError, TypeError):
                    parsed_result.append(item)
            
            return parsed_result
        except Exception as e:
            logger.error(f"Redis LRANGE operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"LRANGE operation failed: {str(e)}",
                operation="LRANGE",
                original_exception=e
            )
    
    # ==================== 哈希操作 ====================
    
    async def hset(self, key: str, field: str = None, value: Any = None, mapping: Dict[str, Any] = None) -> int:
        """设置哈希字段"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            async def _operation():
                if mapping is not None:
                    # 序列化mapping中的值
                    serialized_mapping = {}
                    for k, v in mapping.items():
                        if isinstance(v, (dict, list)):
                            serialized_mapping[k] = json.dumps(v, ensure_ascii=False)
                        else:
                            serialized_mapping[k] = str(v)
                    return await client.hset(full_key, mapping=serialized_mapping)
                else:
                    # 处理单个字段值
                    serialized_value = value
                    if isinstance(value, (dict, list)):
                        serialized_value = json.dumps(value, ensure_ascii=False)
                    return await client.hset(full_key, field, serialized_value)
            
            return await self._execute_with_retry(_operation)
        except Exception as e:
            logger.error(f"Redis HSET operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"HSET operation failed: {str(e)}",
                operation="HSET",
                original_exception=e
            )
    
    async def hget(self, key: str, field: str, default: Any = None) -> Any:
        """获取哈希字段值"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            async def _operation():
                return await client.hget(full_key, field)
            
            result = await self._execute_with_retry(_operation)
            
            if result is None:
                return default
            
            # 尝试解析JSON
            try:
                return json.loads(result)
            except (json.JSONDecodeError, TypeError):
                return result
        except Exception as e:
            logger.error(f"Redis HGET operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"HGET operation failed: {str(e)}",
                operation="HGET",
                original_exception=e
            )
    
    async def hgetall(self, key: str) -> Dict[str, Any]:
        """获取所有哈希字段"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            async def _operation():
                return await client.hgetall(full_key)
            
            result = await self._execute_with_retry(_operation)
            
            # 尝试解析每个值的JSON
            parsed_result = {}
            for field, value in result.items():
                try:
                    parsed_result[field] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    parsed_result[field] = value
            
            return parsed_result
        except Exception as e:
            logger.error(f"Redis HGETALL operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"HGETALL operation failed: {str(e)}",
                operation="HGETALL",
                original_exception=e
            )
    
    # ==================== 集合操作 ====================
    
    async def sadd(self, key: str, *values: Any) -> int:
        """向集合添加元素"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            # 序列化值
            serialized_values = []
            for value in values:
                if isinstance(value, (dict, list)):
                    serialized_values.append(json.dumps(value, ensure_ascii=False))
                else:
                    serialized_values.append(str(value))
            
            async def _operation():
                return await client.sadd(full_key, *serialized_values)
            
            return await self._execute_with_retry(_operation)
        except Exception as e:
            logger.error(f"Redis SADD operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"SADD operation failed: {str(e)}",
                operation="SADD",
                original_exception=e
            )
    
    async def srem(self, key: str, *values: Any) -> int:
        """从集合移除元素"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            # 序列化值
            serialized_values = []
            for value in values:
                if isinstance(value, (dict, list)):
                    serialized_values.append(json.dumps(value, ensure_ascii=False))
                else:
                    serialized_values.append(str(value))
            
            async def _operation():
                return await client.srem(full_key, *serialized_values)
            
            return await self._execute_with_retry(_operation)
        except Exception as e:
            logger.error(f"Redis SREM operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"SREM operation failed: {str(e)}",
                operation="SREM",
                original_exception=e
            )
    
    async def smembers(self, key: str) -> set:
        """获取集合所有成员"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            async def _operation():
                return await client.smembers(full_key)
            
            result = await self._execute_with_retry(_operation)
            return result
        except Exception as e:
            logger.error(f"Redis SMEMBERS operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"SMEMBERS operation failed: {str(e)}",
                operation="SMEMBERS",
                original_exception=e
            )
    
    async def incr(self, key: str) -> int:
        """递增计数器"""
        try:
            client = await self._get_client()
            full_key = self._build_key(key)
            
            async def _operation():
                return await client.incr(full_key)
            
            return await self._execute_with_retry(_operation)
        except Exception as e:
            logger.error(f"Redis INCR operation failed: {e}")
            raise RedisOperationError(
                internal_message=f"INCR operation failed: {str(e)}",
                operation="INCR",
                original_exception=e
            )
    
    # ==================== 健康检查 ====================
    
    async def ping(self) -> bool:
        """检查Redis连接"""
        try:
            client = await self._get_client()
            
            async def _operation():
                return await client.ping()
            
            result = await self._execute_with_retry(_operation)
            return result
        except Exception as e:
            logger.error(f"Redis PING操作失败: {e}")
            return False
    
    async def is_healthy(self) -> bool:
        """检查Redis是否健康"""
        if self._health_checker:
            return await self._health_checker.is_healthy()
        return await self.ping()
    
    # ==================== 连接管理 ====================
    
    async def close(self):
        """关闭Redis连接"""
        if self._client:
            await self._client.close()
            self._client = None
            self._health_checker = None
            logger.info("Redis连接已关闭")
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
