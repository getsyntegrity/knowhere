"""
Redis监控服务
"""
import asyncio
import time
from typing import Any, Dict, List

from loguru import logger

from shared.services.redis.redis_service import RedisService
from shared.utils.redis_key_builder import redis_key_builder


class RedisMonitor:
    """Redis监控服务"""
    
    def __init__(self, redis_service: RedisService):
        self.redis = redis_service
        self._metrics = {}
        self._alerts = []
    
    async def get_redis_info(self) -> Dict[str, Any]:
        """获取Redis信息"""
        try:
            client = await self.redis._get_client()
            info = await client.info()
            return info
        except Exception as e:
            logger.error(f"获取Redis信息失败: {e}")
            return {}
    
    async def get_memory_usage(self) -> Dict[str, Any]:
        """获取内存使用情况"""
        try:
            info = await self.get_redis_info()
            memory_info = {
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "used_memory_rss": info.get("used_memory_rss", 0),
                "used_memory_peak": info.get("used_memory_peak", 0),
                "used_memory_peak_human": info.get("used_memory_peak_human", "0B"),
                "mem_fragmentation_ratio": info.get("mem_fragmentation_ratio", 0),
                "maxmemory": info.get("maxmemory", 0),
                "maxmemory_human": info.get("maxmemory_human", "0B")
            }
            return memory_info
        except Exception as e:
            logger.error(f"获取内存使用情况失败: {e}")
            return {}
    
    async def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        try:
            info = await self.get_redis_info()
            connection_info = {
                "connected_clients": info.get("connected_clients", 0),
                "client_recent_max_input_buffer": info.get("client_recent_max_input_buffer", 0),
                "client_recent_max_output_buffer": info.get("client_recent_max_output_buffer", 0),
                "blocked_clients": info.get("blocked_clients", 0),
                "tracking_clients": info.get("tracking_clients", 0),
                "clients_in_timeout_table": info.get("clients_in_timeout_table", 0)
            }
            return connection_info
        except Exception as e:
            logger.error(f"获取连接信息失败: {e}")
            return {}
    
    async def get_stats_info(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            info = await self.get_redis_info()
            stats_info = {
                "total_commands_processed": info.get("total_commands_processed", 0),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                "total_net_input_bytes": info.get("total_net_input_bytes", 0),
                "total_net_output_bytes": info.get("total_net_output_bytes", 0),
                "instantaneous_input_kbps": info.get("instantaneous_input_kbps", 0),
                "instantaneous_output_kbps": info.get("instantaneous_output_kbps", 0),
                "rejected_connections": info.get("rejected_connections", 0),
                "sync_full": info.get("sync_full", 0),
                "sync_partial_ok": info.get("sync_partial_ok", 0),
                "sync_partial_err": info.get("sync_partial_err", 0)
            }
            return stats_info
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}
    
    async def get_keyspace_info(self) -> Dict[str, Any]:
        """获取键空间信息"""
        try:
            info = await self.get_redis_info()
            keyspace_info = {}
            
            for key, value in info.items():
                if key.startswith("db"):
                    db_name = key
                    db_info = {}
                    for item in value.split(","):
                        if "=" in item:
                            k, v = item.split("=", 1)
                            db_info[k] = v
                    keyspace_info[db_name] = db_info
            
            return keyspace_info
        except Exception as e:
            logger.error(f"获取键空间信息失败: {e}")
            return {}
    
    async def get_slow_log(self, count: int = 10) -> List[Dict[str, Any]]:
        """获取慢查询日志"""
        try:
            client = await self.redis._get_client()
            slow_log = await client.slowlog_get(count)
            
            formatted_log = []
            for entry in slow_log:
                formatted_entry = {
                    "id": entry[0],
                    "timestamp": entry[1],
                    "duration": entry[2],
                    "command": " ".join(entry[3]),
                    "client": entry[4],
                    "client_name": entry[5]
                }
                formatted_log.append(formatted_entry)
            
            return formatted_log
        except Exception as e:
            logger.error(f"获取慢查询日志失败: {e}")
            return []
    
    async def get_key_count_by_type(self) -> Dict[str, int]:
        """按类型统计键数量"""
        try:
            client = await self.redis._get_client()
            keyspace_info = await self.get_keyspace_info()
            
            key_counts = {}
            for db_name, db_info in keyspace_info.items():
                key_count = int(db_info.get("keys", 0))
                if key_count > 0:
                    key_counts[db_name] = key_count
            
            return key_counts
        except Exception as e:
            logger.error(f"统计键数量失败: {e}")
            return {}
    
    async def get_business_metrics(self) -> Dict[str, Any]:
        """获取业务指标"""
        try:
            metrics = {}
            
            # 在线用户数
            online_users = await self.redis.smembers(redis_key_builder.set_online_users())
            metrics["online_users_count"] = len(online_users)
            
            # 活跃用户数
            active_users = await self.redis.smembers(redis_key_builder.set_active_users())
            metrics["active_users_count"] = len(active_users)
            
            # 处理中任务数
            processing_tasks = await self.redis.smembers(redis_key_builder.set_processing_tasks())
            metrics["processing_tasks_count"] = len(processing_tasks)
            
            # 错误日志数
            error_logs = await self.redis.llen(redis_key_builder.list_error_logs())
            metrics["error_logs_count"] = error_logs
            
            return metrics
        except Exception as e:
            logger.error(f"获取业务指标失败: {e}")
            return {}
    
    async def check_health(self) -> Dict[str, Any]:
        """检查Redis健康状态"""
        try:
            health_status = {
                "is_healthy": False,
                "ping_latency": 0,
                "memory_usage": 0,
                "connection_count": 0,
                "issues": []
            }
            
            # 检查PING延迟
            start_time = time.time()
            ping_result = await self.redis.ping()
            ping_latency = (time.time() - start_time) * 1000  # 转换为毫秒
            
            if ping_result:
                health_status["ping_latency"] = ping_latency
            else:
                health_status["issues"].append("PING失败")
            
            # 检查内存使用
            memory_info = await self.get_memory_usage()
            if memory_info:
                used_memory = memory_info.get("used_memory", 0)
                max_memory = memory_info.get("maxmemory", 0)
                
                if max_memory > 0:
                    memory_usage_percent = (used_memory / max_memory) * 100
                    health_status["memory_usage"] = memory_usage_percent
                    
                    if memory_usage_percent > 90:
                        health_status["issues"].append(f"内存使用率过高: {memory_usage_percent:.2f}%")
                else:
                    health_status["memory_usage"] = 0
            
            # 检查连接数
            connection_info = await self.get_connection_info()
            connection_count = connection_info.get("connected_clients", 0)
            health_status["connection_count"] = connection_count
            
            if connection_count > 1000:  # 假设1000个连接为警告阈值
                health_status["issues"].append(f"连接数过多: {connection_count}")
            
            # 检查慢查询
            slow_log = await self.get_slow_log(5)
            if slow_log:
                slow_queries = [log for log in slow_log if log["duration"] > 1000]  # 超过1秒的查询
                if slow_queries:
                    health_status["issues"].append(f"发现 {len(slow_queries)} 个慢查询")
            
            # 判断整体健康状态
            health_status["is_healthy"] = len(health_status["issues"]) == 0
            
            return health_status
        except Exception as e:
            logger.error(f"检查Redis健康状态失败: {e}")
            return {
                "is_healthy": False,
                "ping_latency": 0,
                "memory_usage": 0,
                "connection_count": 0,
                "issues": [f"健康检查失败: {e}"]
            }
    
    async def get_comprehensive_report(self) -> Dict[str, Any]:
        """获取综合监控报告"""
        try:
            report = {
                "timestamp": time.time(),
                "health": await self.check_health(),
                "memory": await self.get_memory_usage(),
                "connections": await self.get_connection_info(),
                "stats": await self.get_stats_info(),
                "keyspace": await self.get_keyspace_info(),
                "business_metrics": await self.get_business_metrics(),
                "slow_log": await self.get_slow_log(5)
            }
            return report
        except Exception as e:
            logger.error(f"生成监控报告失败: {e}")
            return {"error": str(e)}
    
    async def start_monitoring(self, interval: int = 60):
        """开始监控"""
        logger.info("Redis监控已启动")
        
        while True:
            try:
                report = await self.get_comprehensive_report()
                
                # 检查健康状态
                if not report.get("health", {}).get("is_healthy", False):
                    issues = report.get("health", {}).get("issues", [])
                    for issue in issues:
                        logger.warning(f"Redis健康检查警告: {issue}")
                
                # 记录指标
                self._metrics[time.time()] = report
                
                # 清理旧指标（保留最近1小时的数据）
                current_time = time.time()
                self._metrics = {
                    k: v for k, v in self._metrics.items() 
                    if current_time - k < 3600
                }
                
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"监控过程中出错: {e}")
                await asyncio.sleep(interval)
    
    def get_metrics_history(self, duration: int = 3600) -> Dict[str, Any]:
        """获取历史指标"""
        current_time = time.time()
        filtered_metrics = {
            k: v for k, v in self._metrics.items() 
            if current_time - k < duration
        }
        return filtered_metrics
