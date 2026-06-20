"""
异常检测告警规则。

基于统计方法（Z-score/移动平均偏离）检测指标异常，补充阈值告警。

第一性原理：
- 阈值告警依赖人工设定，无法适应动态变化的系统
- 统计异常检测基于历史基线自动识别偏离
- 痛觉神经不仅响应绝对伤害，也响应异常变化

设计要点：
- 移动平均 + 标准差作为基线
- Z-score 超阈值视为异常
- 自适应基线：窗口滑动，适应系统演化
"""

import time
from collections import deque
from typing import Any, Deque, Dict, Optional

from agent_core.monitoring.alert_engine import AlertRule

# 异常检测窗口大小
_ANOMALY_WINDOW = 50
# Z-score 异常阈值
_ZSCORE_THRESHOLD = 3.0
# 最小样本数（不足时不检测）
_MIN_SAMPLES = 10


class AnomalyDetectionRule(AlertRule):
    """
    异常检测告警规则（基于 Z-score）。

    当指标值偏离移动平均超过 N 个标准差时触发告警。
    """

    def __init__(
        self,
        name: str,
        metric_key: str,
        zscore_threshold: float = _ZSCORE_THRESHOLD,
        window_size: int = _ANOMALY_WINDOW,
        cooldown_seconds: float = 60.0,
        min_samples: int = _MIN_SAMPLES,
    ) -> None:
        super().__init__(
            name=name,
            metric_key=metric_key,
            threshold=zscore_threshold,
            comparator=">",
            cooldown_seconds=cooldown_seconds,
        )
        self._zscore_threshold = zscore_threshold
        self._window_size = window_size
        self._min_samples = min_samples
        self._history: Deque[float] = deque(maxlen=window_size)

    def check(self, metrics: Dict[str, Any]) -> bool:
        """检查指标是否异常。"""
        value = metrics.get(self.metric_key)
        if not isinstance(value, (int, float)):
            return False
        self._history.append(float(value))
        if len(self._history) < self._min_samples:
            return False
        zscore = self._compute_zscore(float(value))
        if abs(zscore) > self._zscore_threshold:
            if self._is_cooled_down():
                self._last_triggered = time.time()
                return True
        return False

    def _compute_zscore(self, value: float) -> float:
        """计算 Z-score。"""
        samples = list(self._history)
        mean = sum(samples) / len(samples)
        variance = sum((x - mean) ** 2 for x in samples) / len(samples)
        std = variance ** 0.5
        if std < 1e-10:
            return 0.0
        return (value - mean) / std

    def get_baseline(self) -> Dict[str, float]:
        """获取当前基线统计。"""
        if len(self._history) < 2:
            return {"mean": 0.0, "std": 0.0, "samples": len(self._history)}
        samples = list(self._history)
        mean = sum(samples) / len(samples)
        variance = sum((x - mean) ** 2 for x in samples) / len(samples)
        std = variance ** 0.5
        return {
            "mean": mean,
            "std": std,
            "samples": len(self._history),
        }


class RateOfChangeRule(AlertRule):
    """
    变化率告警规则。

    当指标变化率（单位时间变化量）超过阈值时触发。
    """

    def __init__(
        self,
        name: str,
        metric_key: str,
        max_rate: float,
        cooldown_seconds: float = 60.0,
    ) -> None:
        super().__init__(
            name=name,
            metric_key=metric_key,
            threshold=max_rate,
            comparator=">",
            cooldown_seconds=cooldown_seconds,
        )
        self._max_rate = max_rate
        self._last_value: Optional[float] = None
        self._last_time: float = 0.0

    def check(self, metrics: Dict[str, Any]) -> bool:
        """检查变化率。"""
        value = metrics.get(self.metric_key)
        if not isinstance(value, (int, float)):
            return False
        now = time.time()
        if self._last_value is not None and self._last_time > 0:
            dt = now - self._last_time
            if dt > 0:
                rate = abs(float(value) - self._last_value) / dt
                if rate > self._max_rate:
                    if self._is_cooled_down():
                        self._last_triggered = now
                        self._last_value = float(value)
                        self._last_time = now
                        return True
        self._last_value = float(value)
        self._last_time = now
        return False
