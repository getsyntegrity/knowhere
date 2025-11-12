"""
Redis告警服务
"""
import time
from typing import Any, Callable, Dict, List

from loguru import logger

from app.services.redis.redis_monitor import RedisMonitor


class AlertRule:
    """告警规则"""
    
    def __init__(
        self,
        name: str,
        condition: Callable[[Dict[str, Any]], bool],
        severity: str = "warning",
        message: str = "",
        cooldown: int = 300  # 冷却时间（秒）
    ):
        self.name = name
        self.condition = condition
        self.severity = severity
        self.message = message
        self.cooldown = cooldown
        self.last_triggered = 0
    
    def should_trigger(self, data: Dict[str, Any]) -> bool:
        """检查是否应该触发告警"""
        current_time = time.time()
        
        # 检查冷却时间
        if current_time - self.last_triggered < self.cooldown:
            return False
        
        # 检查条件
        if self.condition(data):
            self.last_triggered = current_time
            return True
        
        return False


class RedisAlertManager:
    """Redis告警管理器"""
    
    def __init__(self, redis_monitor: RedisMonitor):
        self.redis_monitor = redis_monitor
        self.alert_rules = []
        self.alert_history = []
        self._setup_default_rules()
    
    def _setup_default_rules(self):
        """设置默认告警规则"""
        
        # 内存使用率告警
        self.add_rule(AlertRule(
            name="high_memory_usage",
            condition=lambda data: data.get("memory", {}).get("memory_usage", 0) > 90,
            severity="critical",
            message="Redis内存使用率超过90%",
            cooldown=300
        ))
        
        self.add_rule(AlertRule(
            name="medium_memory_usage",
            condition=lambda data: data.get("memory", {}).get("memory_usage", 0) > 80,
            severity="warning",
            message="Redis内存使用率超过80%",
            cooldown=600
        ))
        
        # 连接数告警
        self.add_rule(AlertRule(
            name="high_connection_count",
            condition=lambda data: data.get("connections", {}).get("connected_clients", 0) > 1000,
            severity="warning",
            message="Redis连接数过多",
            cooldown=300
        ))
        
        # PING延迟告警
        self.add_rule(AlertRule(
            name="high_ping_latency",
            condition=lambda data: data.get("health", {}).get("ping_latency", 0) > 100,
            severity="warning",
            message="Redis PING延迟过高",
            cooldown=300
        ))
        
        # 慢查询告警
        self.add_rule(AlertRule(
            name="slow_queries",
            condition=lambda data: len(data.get("slow_log", [])) > 0,
            severity="info",
            message="发现慢查询",
            cooldown=600
        ))
        
        # 错误日志告警
        self.add_rule(AlertRule(
            name="error_logs",
            condition=lambda data: data.get("business_metrics", {}).get("error_logs_count", 0) > 10,
            severity="warning",
            message="错误日志数量过多",
            cooldown=300
        ))
        
        # 处理中任务过多告警
        self.add_rule(AlertRule(
            name="too_many_processing_tasks",
            condition=lambda data: data.get("business_metrics", {}).get("processing_tasks_count", 0) > 100,
            severity="warning",
            message="处理中任务数量过多",
            cooldown=300
        ))
    
    def add_rule(self, rule: AlertRule):
        """添加告警规则"""
        self.alert_rules.append(rule)
        logger.info(f"添加告警规则: {rule.name}")
    
    def remove_rule(self, rule_name: str):
        """移除告警规则"""
        self.alert_rules = [rule for rule in self.alert_rules if rule.name != rule_name]
        logger.info(f"移除告警规则: {rule_name}")
    
    async def check_alerts(self) -> List[Dict[str, Any]]:
        """检查告警"""
        try:
            # 获取监控数据
            report = await self.redis_monitor.get_comprehensive_report()
            
            triggered_alerts = []
            
            # 检查每个规则
            for rule in self.alert_rules:
                if rule.should_trigger(report):
                    alert = {
                        "rule_name": rule.name,
                        "severity": rule.severity,
                        "message": rule.message or f"告警规则 {rule.name} 被触发",
                        "timestamp": time.time(),
                        "data": report
                    }
                    
                    triggered_alerts.append(alert)
                    self.alert_history.append(alert)
                    
                    # 记录告警
                    self._log_alert(alert)
            
            return triggered_alerts
            
        except Exception as e:
            logger.error(f"检查告警失败: {e}")
            return []
    
    def _log_alert(self, alert: Dict[str, Any]):
        """记录告警"""
        severity = alert["severity"]
        message = alert["message"]
        rule_name = alert["rule_name"]
        
        if severity == "critical":
            logger.critical(f"[REDIS告警] {rule_name}: {message}")
        elif severity == "warning":
            logger.warning(f"[REDIS告警] {rule_name}: {message}")
        else:
            logger.info(f"[REDIS告警] {rule_name}: {message}")
    
    def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取告警历史"""
        return self.alert_history[-limit:]
    
    def get_alert_stats(self) -> Dict[str, Any]:
        """获取告警统计"""
        if not self.alert_history:
            return {
                "total_alerts": 0,
                "critical_alerts": 0,
                "warning_alerts": 0,
                "info_alerts": 0,
                "recent_alerts": 0
            }
        
        current_time = time.time()
        recent_threshold = current_time - 3600  # 最近1小时
        
        stats = {
            "total_alerts": len(self.alert_history),
            "critical_alerts": len([a for a in self.alert_history if a["severity"] == "critical"]),
            "warning_alerts": len([a for a in self.alert_history if a["severity"] == "warning"]),
            "info_alerts": len([a for a in self.alert_history if a["severity"] == "info"]),
            "recent_alerts": len([a for a in self.alert_history if a["timestamp"] > recent_threshold])
        }
        
        return stats
    
    async def start_alert_monitoring(self, interval: int = 60):
        """开始告警监控"""
        logger.info("Redis告警监控已启动")
        
        import asyncio
        
        while True:
            try:
                alerts = await self.check_alerts()
                
                if alerts:
                    logger.info(f"检测到 {len(alerts)} 个告警")
                
                await asyncio.sleep(interval)
                
            except Exception as e:
                logger.error(f"告警监控过程中出错: {e}")
                await asyncio.sleep(interval)
    
    def create_custom_rule(
        self,
        name: str,
        condition_func: Callable[[Dict[str, Any]], bool],
        severity: str = "warning",
        message: str = "",
        cooldown: int = 300
    ):
        """创建自定义告警规则"""
        rule = AlertRule(
            name=name,
            condition=condition_func,
            severity=severity,
            message=message,
            cooldown=cooldown
        )
        self.add_rule(rule)
        return rule


class RedisAlertNotifier:
    """Redis告警通知器"""
    
    def __init__(self):
        self.notifiers = []
    
    def add_notifier(self, notifier_func: Callable[[Dict[str, Any]], None]):
        """添加通知器"""
        self.notifiers.append(notifier_func)
    
    async def notify(self, alert: Dict[str, Any]):
        """发送通知"""
        for notifier in self.notifiers:
            try:
                await notifier(alert)
            except Exception as e:
                logger.error(f"发送告警通知失败: {e}")
    
    async def notify_email(self, alert: Dict[str, Any]):
        """邮件通知（示例）"""
        # 这里可以实现邮件发送逻辑
        logger.info(f"发送邮件告警: {alert['message']}")
    
    async def notify_webhook(self, alert: Dict[str, Any]):
        """Webhook通知（示例）"""
        # 这里可以实现Webhook发送逻辑
        logger.info(f"发送Webhook告警: {alert['message']}")
    
    async def notify_slack(self, alert: Dict[str, Any]):
        """Slack通知（示例）"""
        # 这里可以实现Slack发送逻辑
        logger.info(f"发送Slack告警: {alert['message']}")
