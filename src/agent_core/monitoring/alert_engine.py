"""
自动化告警引擎。

基于阈值规则监控指标并触发告警。

第一性原理：
- 告警是系统的"痛觉神经"，必须及时准确
- 规则简单明确，避免告警风暴
- 与JSON日志集成，输出结构化告警
"""

import json
import time
from typing import Any, Callable, Dict, List, Optional

from agent_core.common.logger import get_logger


class AlertRule:
    """告警规则。"""

    def __init__(
        self,
        name: str,
        metric_key: str,
        threshold: float,
        comparator: str,
        cooldown_seconds: float,
    ) -> None:
        self.name = name
        self.metric_key = metric_key
        self.threshold = threshold
        self.comparator = comparator
        self.cooldown_seconds = cooldown_seconds
        self._last_triggered: float = 0.0

    def check(self, metrics: Dict[str, Any]) -> bool:
        value = metrics.get(self.metric_key)
        if not isinstance(value, (int, float)):
            return False
        triggered = self._compare(value)
        if triggered and self._is_cooled_down():
            self._last_triggered = time.time()
            return True
        return False

    def _compare(self, value: float) -> bool:
        if self.comparator == ">":
            return value > self.threshold
        if self.comparator == ">=":
            return value >= self.threshold
        if self.comparator == "<":
            return value < self.threshold
        if self.comparator == "<=":
            return value <= self.threshold
        return False

    def _is_cooled_down(self) -> bool:
        return time.time() - self._last_triggered >= self.cooldown_seconds


class AlertEngine:
    """告警引擎。"""

    def __init__(self) -> None:
        self._rules: List[AlertRule] = []
        self._logger = get_logger()
        self._handlers: List[Callable[[Dict[str, Any]], None]] = []

    def add_rule(self, rule: AlertRule) -> None:
        self._rules.append(rule)

    def add_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        self._handlers.append(handler)

    def evaluate(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        for rule in self._rules:
            if rule.check(metrics):
                alert = self._build_alert(rule, metrics)
                alerts.append(alert)
                self._dispatch(alert)
        return alerts

    def _build_alert(
        self, rule: AlertRule, metrics: Dict[str, Any]
    ) -> Dict[str, Any]:
        return {
            "timestamp": time.time(),
            "rule": rule.name,
            "metric": rule.metric_key,
            "value": metrics.get(rule.metric_key),
            "threshold": rule.threshold,
            "comparator": rule.comparator,
            "severity": self._severity(rule, metrics),
        }

    def _severity(
        self, rule: AlertRule, metrics: Dict[str, Any]
    ) -> str:
        value = metrics.get(rule.metric_key, 0)
        if not isinstance(value, (int, float)):
            return "warning"
        ratio = abs(value - rule.threshold) / max(abs(rule.threshold), 1e-6)
        if ratio > 0.5:
            return "critical"
        if ratio > 0.2:
            return "warning"
        return "info"

    def _dispatch(self, alert: Dict[str, Any]) -> None:
        self._logger.warning(json.dumps({"alert": alert}, ensure_ascii=False))
        for handler in self._handlers:
            try:
                handler(alert)
            except Exception as exc:
                self._logger.error(f"[AlertEngine] Handler failed: {exc}")
