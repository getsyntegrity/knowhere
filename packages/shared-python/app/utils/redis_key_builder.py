"""
Redis键值命名规范工具
"""
from typing import Optional, Dict, Any
from enum import Enum


class RedisKeyType(Enum):
    """Redis键类型枚举"""
    USER = "user"
    TASK = "task"
    CONVERSATION = "conversation"
    KNOWLEDGE_BASE = "kb"
    SESSION = "session"
    CACHE = "cache"
    QUEUE = "queue"
    COUNTER = "counter"
    SET = "set"
    HASH = "hash"
    LIST = "list"


class RedisKeyBuilder:
    """Redis键值构建器"""
    
    def __init__(self, prefix: str = "aismart_bid:v1"):
        self.prefix = prefix
    
    def build_key(self, key_type: RedisKeyType, *parts: str, **kwargs) -> str:
        """
        构建Redis键
        
        Args:
            key_type: 键类型
            *parts: 键的各个部分
            **kwargs: 额外的键值对参数
        
        Returns:
            完整的Redis键
        """
        key_parts = [self.prefix, key_type.value]
        key_parts.extend(parts)
        
        # 添加额外的键值对参数
        if kwargs:
            for key, value in sorted(kwargs.items()):
                key_parts.append(f"{key}:{value}")
        
        return ":".join(key_parts)
    
    # ==================== 用户相关键 ====================
    
    def user_config(self, username: str) -> str:
        """用户配置键"""
        return self.build_key(RedisKeyType.USER, username, "config")
    
    def user_session(self, username: str) -> str:
        """用户会话键"""
        return self.build_key(RedisKeyType.USER, username, "session")
    
    def user_permissions(self, username: str) -> str:
        """用户权限键"""
        return self.build_key(RedisKeyType.USER, username, "permissions")
    
    def user_activity(self, username: str) -> str:
        """用户活动键"""
        return self.build_key(RedisKeyType.USER, username, "activity")
    
    # ==================== 任务相关键 ====================
    
    def task_status(self, task_id: str) -> str:
        """任务状态键"""
        return self.build_key(RedisKeyType.TASK, task_id, "status")
    
    def task_result(self, task_id: str) -> str:
        """任务结果键"""
        return self.build_key(RedisKeyType.TASK, task_id, "result")
    
    def task_metadata(self, task_id: str) -> str:
        """任务元数据键"""
        return self.build_key(RedisKeyType.TASK, task_id, "metadata")
    
    def task_progress(self, task_id: str) -> str:
        """任务进度键"""
        return self.build_key(RedisKeyType.TASK, task_id, "progress")
    
    def task_info(self, task_id: str) -> str:
        """任务基本信息键"""
        return self.build_key(RedisKeyType.TASK, task_id, "info")
    
    def task_queue(self, queue_name: str) -> str:
        """任务队列键"""
        return self.build_key(RedisKeyType.QUEUE, queue_name)
    
    # ==================== 对话相关键 ====================
    
    def conversation_state(self, conversation_id: str) -> str:
        """对话状态键"""
        return self.build_key(RedisKeyType.CONVERSATION, conversation_id, "state")
    
    def conversation_history(self, conversation_id: str) -> str:
        """对话历史键"""
        return self.build_key(RedisKeyType.CONVERSATION, conversation_id, "history")
    
    def conversation_context(self, conversation_id: str) -> str:
        """对话上下文键"""
        return self.build_key(RedisKeyType.CONVERSATION, conversation_id, "context")
    
    # ==================== 知识库相关键 ====================
    
    def kb_status(self, user_id: str) -> str:
        """知识库状态键"""
        return self.build_key(RedisKeyType.KNOWLEDGE_BASE, user_id, "status")
    
    def kb_vectors(self, user_id: str) -> str:
        """知识库向量键"""
        return self.build_key(RedisKeyType.KNOWLEDGE_BASE, user_id, "vectors")
    
    def kb_metadata(self, user_id: str) -> str:
        """知识库元数据键"""
        return self.build_key(RedisKeyType.KNOWLEDGE_BASE, user_id, "metadata")
    
    def kb_index(self, user_id: str) -> str:
        """知识库索引键"""
        return self.build_key(RedisKeyType.KNOWLEDGE_BASE, user_id, "index")
    
    # ==================== 会话相关键 ====================
    
    def session_data(self, session_id: str) -> str:
        """会话数据键"""
        return self.build_key(RedisKeyType.SESSION, session_id, "data")
    
    def session_expiry(self, session_id: str) -> str:
        """会话过期时间键"""
        return self.build_key(RedisKeyType.SESSION, session_id, "expiry")
    
    # ==================== 缓存相关键 ====================
    
    def cache_data(self, cache_key: str) -> str:
        """缓存数据键"""
        return self.build_key(RedisKeyType.CACHE, cache_key)
    
    def cache_metadata(self, cache_key: str) -> str:
        """缓存元数据键"""
        return self.build_key(RedisKeyType.CACHE, cache_key, "metadata")
    
    
    # ==================== 计数器相关键 ====================
    
    def counter_user_requests(self, username: str) -> str:
        """用户请求计数器键"""
        return self.build_key(RedisKeyType.COUNTER, "user_requests", username)
    
    def counter_api_calls(self, api_name: str) -> str:
        """API调用计数器键"""
        return self.build_key(RedisKeyType.COUNTER, "api_calls", api_name)
    
    def counter_task_completed(self, task_type: str) -> str:
        """任务完成计数器键"""
        return self.build_key(RedisKeyType.COUNTER, "task_completed", task_type)
    
    def rate_limit_api(self, user_id: str, api_name: str) -> str:
        """API速率限制键"""
        return self.build_key(RedisKeyType.COUNTER, "rate_limit", api_name, user_id)
    
    # ==================== 集合相关键 ====================
    
    def set_active_users(self) -> str:
        """活跃用户集合键"""
        return self.build_key(RedisKeyType.SET, "active_users")
    
    def set_online_users(self) -> str:
        """在线用户集合键"""
        return self.build_key(RedisKeyType.SET, "online_users")
    
    def set_processing_tasks(self) -> str:
        """处理中任务集合键"""
        return self.build_key(RedisKeyType.SET, "processing_tasks")
    
    # ==================== 哈希相关键 ====================
    
    def hash_user_stats(self, username: str) -> str:
        """用户统计哈希键"""
        return self.build_key(RedisKeyType.HASH, "user_stats", username)
    
    def hash_system_stats(self) -> str:
        """系统统计哈希键"""
        return self.build_key(RedisKeyType.HASH, "system_stats")
    
    def hash_task_stats(self, task_id: str) -> str:
        """任务统计哈希键"""
        return self.build_key(RedisKeyType.HASH, "task_stats", task_id)
    
    # ==================== 列表相关键 ====================
    
    def list_recent_activities(self, username: str) -> str:
        """最近活动列表键"""
        return self.build_key(RedisKeyType.LIST, "recent_activities", username)
    
    def list_error_logs(self) -> str:
        """错误日志列表键"""
        return self.build_key(RedisKeyType.LIST, "error_logs")
    
    def list_audit_logs(self) -> str:
        """审计日志列表键"""
        return self.build_key(RedisKeyType.LIST, "audit_logs")
    
    # ==================== 工具方法 ====================
    
    def parse_key(self, key: str) -> Dict[str, Any]:
        """
        解析Redis键，提取各个部分
        
        Args:
            key: Redis键
        
        Returns:
            解析后的键信息
        """
        if not key.startswith(self.prefix):
            raise ValueError(f"键 '{key}' 不是有效的Redis键格式")
        
        parts = key[len(self.prefix):].lstrip(':').split(':')
        
        if len(parts) < 2:
            raise ValueError(f"键 '{key}' 格式不正确")
        
        result = {
            'prefix': self.prefix,
            'type': parts[0],
            'parts': parts[1:],
            'original_key': key
        }
        
        return result
    
    def is_key_type(self, key: str, key_type: RedisKeyType) -> bool:
        """
        检查键是否属于指定类型
        
        Args:
            key: Redis键
            key_type: 键类型
        
        Returns:
            是否属于指定类型
        """
        try:
            parsed = self.parse_key(key)
            return parsed['type'] == key_type.value
        except ValueError:
            return False
    
    def get_key_ttl(self, key_type: RedisKeyType) -> int:
        """
        获取键类型的默认TTL
        
        Args:
            key_type: 键类型
        
        Returns:
            TTL（秒）
        """
        ttl_mapping = {
            RedisKeyType.USER: 86400,      # 1天（user_config缓存）
            RedisKeyType.TASK: 86400,      # 1天
            RedisKeyType.CONVERSATION: 3600 * 2,  # 2小时
            RedisKeyType.KNOWLEDGE_BASE: 86400 * 30,  # 30天
            RedisKeyType.SESSION: 3600,    # 1小时
            RedisKeyType.CACHE: 3600,      # 1小时
            RedisKeyType.QUEUE: 86400,     # 1天
            RedisKeyType.COUNTER: 86400,   # 1天
            RedisKeyType.SET: 86400,       # 1天
            RedisKeyType.HASH: 86400,      # 1天
            RedisKeyType.LIST: 86400,      # 1天
        }
        
        return ttl_mapping.get(key_type, 3600)  # 默认1小时


# 全局键构建器实例
redis_key_builder = RedisKeyBuilder()
