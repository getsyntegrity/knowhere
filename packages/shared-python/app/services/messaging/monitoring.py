"""
消息服务监控
提供消息发布和消费的监控指标
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict

from loguru import logger

from app.services.redis import RedisServiceFactory


class MessageMonitoring:
    """消息监控服务"""
    
    def __init__(self):
        """初始化监控服务"""
        self.redis_service = None
        self._stats = defaultdict(int)
        self._error_stats = defaultdict(list)
        self._duration_stats = defaultdict(list)  # 内存中的耗时统计
    
    def _get_redis_service(self):
        """获取Redis服务（延迟初始化）"""
        if self.redis_service is None:
            self.redis_service = RedisServiceFactory.get_service()
        return self.redis_service
    
    def record_message_published(self, message_type: str, job_id: str, success: bool):
        """
        记录消息发布
        
        Args:
            message_type: 消息类型
            job_id: 任务ID
            success: 是否成功
        """
        key = f"message_published:{message_type}"
        self._stats[key] += 1
        
        if not success:
            error_key = f"message_publish_error:{message_type}"
            self._error_stats[error_key].append({
                "job_id": job_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            logger.warning(f"消息发布失败: {message_type}, job_id={job_id}")
    
    def record_message_processed(self, message_type: str, job_id: str, success: bool, duration_ms: float = None):
        """
        记录消息处理
        
        Args:
            message_type: 消息类型
            job_id: 任务ID
            success: 是否成功
            duration_ms: 处理耗时（毫秒）
        """
        key = f"message_processed:{message_type}"
        self._stats[key] += 1
        
        if not success:
            error_key = f"message_process_error:{message_type}"
            self._error_stats[error_key].append({
                "job_id": job_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            logger.warning(f"消息处理失败: {message_type}, job_id={job_id}")
        
        if duration_ms:
            duration_key = f"message_duration:{message_type}"
            # 可以存储到Redis进行统计（异步操作，不阻塞）
            try:
                redis = self._get_redis_service()
                # 使用Redis的sorted set存储耗时数据
                # 注意：这里使用同步Redis客户端，如果是异步需要调整
                if hasattr(redis, 'zadd'):
                    redis.zadd(
                        f"message_durations:{message_type}",
                        {str(datetime.utcnow().timestamp()): duration_ms}
                    )
                    # 只保留最近1小时的数据
                    cutoff = (datetime.utcnow() - timedelta(hours=1)).timestamp()
                    redis.zremrangebyscore(f"message_durations:{message_type}", 0, cutoff)
                else:
                    # 如果Redis服务是异步的，记录到内存统计中
                    if not hasattr(self, '_duration_stats'):
                        self._duration_stats = defaultdict(list)
                    self._duration_stats[duration_key].append(duration_ms)
                    # 只保留最近100条记录
                    if len(self._duration_stats[duration_key]) > 100:
                        self._duration_stats[duration_key] = self._duration_stats[duration_key][-100:]
            except Exception as e:
                logger.error(f"记录消息处理耗时失败: {e}")
                # 降级到内存统计
                if not hasattr(self, '_duration_stats'):
                    self._duration_stats = defaultdict(list)
                self._duration_stats[duration_key].append(duration_ms)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息字典
        """
        stats = {
            "published": {},
            "processed": {},
            "errors": {},
            "durations": {}
        }
        
        # 统计发布数量
        for key, count in self._stats.items():
            if key.startswith("message_published:"):
                msg_type = key.replace("message_published:", "")
                stats["published"][msg_type] = count
        
        # 统计处理数量
        for key, count in self._stats.items():
            if key.startswith("message_processed:"):
                msg_type = key.replace("message_processed:", "")
                stats["processed"][msg_type] = count
        
        # 统计错误
        for key, errors in self._error_stats.items():
            msg_type = key.replace("message_publish_error:", "").replace("message_process_error:", "")
            if msg_type not in stats["errors"]:
                stats["errors"][msg_type] = []
            stats["errors"][msg_type].extend(errors[-10:])  # 只保留最近10个错误
        
        # 统计平均耗时
        try:
            redis = self._get_redis_service()
            for msg_type in ["job_status_update", "job_progress_update", "job_result", "job_failure"]:
                key = f"message_durations:{msg_type}"
                if hasattr(redis, 'zrange'):
                    durations = redis.zrange(key, 0, -1, withscores=True)
                    if durations:
                        values = [float(score) for _, score in durations]
                        stats["durations"][msg_type] = {
                            "count": len(values),
                            "avg_ms": sum(values) / len(values),
                            "min_ms": min(values),
                            "max_ms": max(values)
                        }
                # 如果Redis不可用，使用内存统计
                elif hasattr(self, '_duration_stats'):
                    duration_key = f"message_duration:{msg_type}"
                    if duration_key in self._duration_stats:
                        values = self._duration_stats[duration_key]
                        if values:
                            stats["durations"][msg_type] = {
                                "count": len(values),
                                "avg_ms": sum(values) / len(values),
                                "min_ms": min(values),
                                "max_ms": max(values)
                            }
        except Exception as e:
            logger.error(f"获取消息处理耗时统计失败: {e}")
            # 降级到内存统计
            if hasattr(self, '_duration_stats'):
                for duration_key, values in self._duration_stats.items():
                    msg_type = duration_key.replace("message_duration:", "")
                    if values:
                        stats["durations"][msg_type] = {
                            "count": len(values),
                            "avg_ms": sum(values) / len(values),
                            "min_ms": min(values),
                            "max_ms": max(values)
                        }
        
        return stats
    
    def reset_stats(self):
        """重置统计信息"""
        self._stats.clear()
        self._error_stats.clear()
        logger.info("消息监控统计已重置")


# 创建全局监控实例
message_monitoring = MessageMonitoring()

