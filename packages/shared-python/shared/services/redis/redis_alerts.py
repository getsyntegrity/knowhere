"""Alerting helpers built on top of Redis monitoring."""

import time
from typing import Any, Callable, Dict, List

from loguru import logger

from shared.services.redis.redis_monitor import RedisMonitor


class AlertRule:
    """Alert rule definition."""

    def __init__(
        self,
        name: str,
        condition: Callable[[Dict[str, Any]], bool],
        severity: str = "warning",
        message: str = "",
        cooldown: int = 300,  # Cooldown in seconds.
    ):
        self.name = name
        self.condition = condition
        self.severity = severity
        self.message = message
        self.cooldown = cooldown
        self.last_triggered = 0

    def should_trigger(self, data: Dict[str, Any]) -> bool:
        """Check whether the alert should trigger."""
        current_time = time.time()

        # Respect the cooldown window.
        if current_time - self.last_triggered < self.cooldown:
            return False

        # Evaluate the rule condition.
        if self.condition(data):
            self.last_triggered = current_time
            return True

        return False


class RedisAlertManager:
    """Manager for Redis alert rules and alert history."""

    def __init__(self, redis_monitor: RedisMonitor):
        self.redis_monitor = redis_monitor
        self.alert_rules = []
        self.alert_history = []
        self._setup_default_rules()

    def _setup_default_rules(self):
        """Register default alert rules."""

        # Memory-usage alerts.
        self.add_rule(
            AlertRule(
                name="high_memory_usage",
                condition=lambda data: data.get("memory", {}).get("memory_usage", 0)
                > 90,
                severity="critical",
                message="Redis memory usage exceeds 90%",
                cooldown=300,
            )
        )

        self.add_rule(
            AlertRule(
                name="medium_memory_usage",
                condition=lambda data: data.get("memory", {}).get("memory_usage", 0)
                > 80,
                severity="warning",
                message="Redis memory usage exceeds 80%",
                cooldown=600,
            )
        )

        # Connection-count alert.
        self.add_rule(
            AlertRule(
                name="high_connection_count",
                condition=lambda data: data.get("connections", {}).get(
                    "connected_clients", 0
                )
                > 1000,
                severity="warning",
                message="Redis connection count is too high",
                cooldown=300,
            )
        )

        # PING latency alert.
        self.add_rule(
            AlertRule(
                name="high_ping_latency",
                condition=lambda data: data.get("health", {}).get("ping_latency", 0)
                > 100,
                severity="warning",
                message="Redis PING latency is too high",
                cooldown=300,
            )
        )

        # Slow-query alert.
        self.add_rule(
            AlertRule(
                name="slow_queries",
                condition=lambda data: len(data.get("slow_log", [])) > 0,
                severity="info",
                message="Slow queries detected",
                cooldown=600,
            )
        )

        # Error-log alert.
        self.add_rule(
            AlertRule(
                name="error_logs",
                condition=lambda data: data.get("business_metrics", {}).get(
                    "error_logs_count", 0
                )
                > 10,
                severity="warning",
                message="Too many error logs",
                cooldown=300,
            )
        )

        # Too many processing tasks alert.
        self.add_rule(
            AlertRule(
                name="too_many_processing_tasks",
                condition=lambda data: data.get("business_metrics", {}).get(
                    "processing_tasks_count", 0
                )
                > 100,
                severity="warning",
                message="Too many tasks in progress",
                cooldown=300,
            )
        )

    def add_rule(self, rule: AlertRule):
        """Add an alert rule."""
        self.alert_rules.append(rule)
        logger.info(f"Added alert rule: {rule.name}")

    def remove_rule(self, rule_name: str):
        """Remove an alert rule."""
        self.alert_rules = [rule for rule in self.alert_rules if rule.name != rule_name]
        logger.info(f"Removed alert rule: {rule_name}")

    async def check_alerts(self) -> List[Dict[str, Any]]:
        """Evaluate all alert rules."""
        try:
            # Load the latest monitoring report.
            report = await self.redis_monitor.get_comprehensive_report()

            triggered_alerts = []

            # Evaluate every registered rule.
            for rule in self.alert_rules:
                if rule.should_trigger(report):
                    alert = {
                        "rule_name": rule.name,
                        "severity": rule.severity,
                        "message": rule.message or f"Alert rule {rule.name} triggered",
                        "timestamp": time.time(),
                        "data": report,
                    }

                    triggered_alerts.append(alert)
                    self.alert_history.append(alert)

                    # Record the triggered alert.
                    self._log_alert(alert)

            return triggered_alerts

        except Exception as e:
            logger.error(f"Failed to check alerts: {e}")
            return []

    def _log_alert(self, alert: Dict[str, Any]):
        """Write an alert to logs."""
        severity = alert["severity"]
        message = alert["message"]
        rule_name = alert["rule_name"]

        if severity == "critical":
            logger.critical(f"[REDIS ALERT] {rule_name}: {message}")
        elif severity == "warning":
            logger.warning(f"[REDIS ALERT] {rule_name}: {message}")
        else:
            logger.info(f"[REDIS ALERT] {rule_name}: {message}")

    def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get alert history."""
        return self.alert_history[-limit:]

    def get_alert_stats(self) -> Dict[str, Any]:
        """Get alert statistics."""
        if not self.alert_history:
            return {
                "total_alerts": 0,
                "critical_alerts": 0,
                "warning_alerts": 0,
                "info_alerts": 0,
                "recent_alerts": 0,
            }

        current_time = time.time()
        recent_threshold = current_time - 3600  # Last hour.

        stats = {
            "total_alerts": len(self.alert_history),
            "critical_alerts": len(
                [a for a in self.alert_history if a["severity"] == "critical"]
            ),
            "warning_alerts": len(
                [a for a in self.alert_history if a["severity"] == "warning"]
            ),
            "info_alerts": len(
                [a for a in self.alert_history if a["severity"] == "info"]
            ),
            "recent_alerts": len(
                [a for a in self.alert_history if a["timestamp"] > recent_threshold]
            ),
        }

        return stats

    async def start_alert_monitoring(self, interval: int = 60):
        """Start the alert-monitoring loop."""
        logger.info("Redis alert monitoring started")

        import asyncio

        while True:
            try:
                alerts = await self.check_alerts()

                if alerts:
                    logger.info(f"Detected {len(alerts)} alerts")

                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Error during alert monitoring: {e}")
                await asyncio.sleep(interval)

    def create_custom_rule(
        self,
        name: str,
        condition_func: Callable[[Dict[str, Any]], bool],
        severity: str = "warning",
        message: str = "",
        cooldown: int = 300,
    ):
        """Create and register a custom alert rule."""
        rule = AlertRule(
            name=name,
            condition=condition_func,
            severity=severity,
            message=message,
            cooldown=cooldown,
        )
        self.add_rule(rule)
        return rule


class RedisAlertNotifier:
    """Alert notification fan-out helper."""

    def __init__(self):
        self.notifiers = []

    def add_notifier(self, notifier_func: Callable[[Dict[str, Any]], None]):
        """Add a notifier callback."""
        self.notifiers.append(notifier_func)

    async def notify(self, alert: Dict[str, Any]):
        """Send an alert through all notifier callbacks."""
        for notifier in self.notifiers:
            try:
                await notifier(alert)
            except Exception as e:
                logger.error(f"Failed to send alert notification: {e}")

    async def notify_email(self, alert: Dict[str, Any]):
        """Email notifier example."""
        # Email delivery logic can be implemented here.
        logger.info(f"Sending email alert: {alert['message']}")

    async def notify_webhook(self, alert: Dict[str, Any]):
        """Webhook notifier example."""
        # Webhook delivery logic can be implemented here.
        logger.info(f"Sending webhook alert: {alert['message']}")

    async def notify_slack(self, alert: Dict[str, Any]):
        """Slack notifier example."""
        # Slack delivery logic can be implemented here.
        logger.info(f"Sending Slack alert: {alert['message']}")
