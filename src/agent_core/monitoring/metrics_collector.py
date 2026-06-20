"""
统一指标采集器。

集中采集系统全链路指标，支持 Prometheus 格式导出。

第一性原理：
- 生物本体感觉（proprioception）持续感知内部状态以维持稳态
- 可观测性三支柱：指标（metrics）、日志（logs）、追踪（traces）
- 指标采集必须低开销、非阻塞、线程安全

设计要点：
- 统一指标注册表：counter/gauge/histogram 三种类型
- 线程安全：多模块并发采集
- Prometheus 格式导出：文本格式兼容 Grafana
- 滑动窗口：近期指标优先
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from agent_core.common.logger import get_logger

# 指标历史窗口大小
_METRIC_HISTORY_SIZE = 100
# 柱状图默认桶边界（秒，用于延迟分布）
_DEFAULT_LATENCY_BUCKETS = [
    0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0
]


@dataclass
class MetricSample:
    """单次指标采样。"""

    name: str
    value: float
    timestamp: float
    labels: Dict[str, str] = field(default_factory=dict)


class Counter:
    """单调递增计数器。"""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._value = 0.0
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0) -> None:
        """增加计数值。"""
        with self._lock:
            self._value += amount

    def get(self) -> float:
        """获取当前值。"""
        with self._lock:
            return self._value


class Gauge:
    """可增可减的瞬时值。"""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._value = 0.0
        self._lock = threading.Lock()

    def set(self, value: float) -> None:
        """设置值。"""
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0) -> None:
        """增加值。"""
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        """减少值。"""
        with self._lock:
            self._value -= amount

    def get(self) -> float:
        """获取当前值。"""
        with self._lock:
            return self._value


class Histogram:
    """柱状图（延迟分布）。"""

    def __init__(
        self,
        name: str,
        description: str = "",
        buckets: Optional[List[float]] = None,
    ) -> None:
        self.name = name
        self.description = description
        self._buckets = sorted(buckets or _DEFAULT_LATENCY_BUCKETS)
        self._counts: List[int] = [0] * len(self._buckets)
        self._sum = 0.0
        self._count = 0
        self._lock = threading.Lock()
        # 近期样本（用于百分位计算）
        self._samples: Deque[float] = deque(maxlen=_METRIC_HISTORY_SIZE)

    def observe(self, value: float) -> None:
        """观测一个值。"""
        with self._lock:
            self._sum += value
            self._count += 1
            self._samples.append(value)
            for i, bound in enumerate(self._buckets):
                if value <= bound:
                    self._counts[i] += 1

    def _get_percentile_unlocked(self, p: float) -> float:
        """计算百分位值（调用方必须已持有锁）。"""
        if not self._samples:
            return 0.0
        sorted_samples = sorted(self._samples)
        idx = int(len(sorted_samples) * p / 100.0)
        idx = min(idx, len(sorted_samples) - 1)
        return sorted_samples[idx]

    def get_percentile(self, p: float) -> float:
        """计算百分位值。"""
        with self._lock:
            return self._get_percentile_unlocked(p)

    def get_stats(self) -> Dict[str, float]:
        """获取统计信息。"""
        with self._lock:
            return {
                "count": self._count,
                "sum": self._sum,
                "avg": self._sum / self._count if self._count > 0 else 0.0,
                "p50": self._get_percentile_unlocked(50),
                "p95": self._get_percentile_unlocked(95),
                "p99": self._get_percentile_unlocked(99),
            }


class MetricsCollector:
    """
    统一指标采集器。

    管理所有 Counter/Gauge/Histogram 指标，支持 Prometheus 导出。
    """

    def __init__(self) -> None:
        self._logger = get_logger()
        self._lock = threading.RLock()
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        # 指标历史（用于趋势分析）
        self._history: Deque[MetricSample] = deque(
            maxlen=_METRIC_HISTORY_SIZE * 10
        )
        # 采集回调（外部模块注册）
        self._collectors: List[Callable[[], Dict[str, float]]] = []

    def register_counter(
        self, name: str, description: str = ""
    ) -> Counter:
        """注册计数器。"""
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, description)
            return self._counters[name]

    def register_gauge(
        self, name: str, description: str = ""
    ) -> Gauge:
        """注册瞬时值。"""
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, description)
            return self._gauges[name]

    def register_histogram(
        self,
        name: str,
        description: str = "",
        buckets: Optional[List[float]] = None,
    ) -> Histogram:
        """注册柱状图。"""
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, description, buckets)
            return self._histograms[name]

    def add_collector(
        self, callback: Callable[[], Dict[str, float]]
    ) -> None:
        """注册外部采集回调。"""
        with self._lock:
            self._collectors.append(callback)

    def collect_all(self) -> Dict[str, float]:
        """
        采集所有指标当前值。

        Returns:
            指标名到值的映射。
        """
        result: Dict[str, float] = {}
        with self._lock:
            for name, counter in self._counters.items():
                result[name] = counter.get()
            for name, gauge in self._gauges.items():
                result[name] = gauge.get()
            for name, hist in self._histograms.items():
                stats = hist.get_stats()
                for stat_name, value in stats.items():
                    result[f"{name}_{stat_name}"] = value
            # 调用外部采集器
            for collector in self._collectors:
                try:
                    collected = collector()
                    result.update(collected)
                except Exception as exc:
                    self._logger.error(
                        f"[MetricsCollector] Collector failed: {exc}"
                    )
        # 记录历史
        now = time.time()
        for name, value in result.items():
            self._history.append(
                MetricSample(name=name, value=value, timestamp=now)
            )
        return result

    def get_history(
        self, name: str, limit: int = 50
    ) -> List[MetricSample]:
        """获取指定指标的历史采样。"""
        with self._lock:
            return [
                s for s in self._history if s.name == name
            ][-limit:]

    def export_prometheus(self) -> str:
        """
        导出 Prometheus 文本格式。

        Returns:
            Prometheus 格式字符串。
        """
        lines: List[str] = []
        with self._lock:
            # Counters
            for name, counter in sorted(self._counters.items()):
                if counter.description:
                    lines.append(f"# HELP {name} {counter.description}")
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name} {counter.get()}")
            # Gauges
            for name, gauge in sorted(self._gauges.items()):
                if gauge.description:
                    lines.append(f"# HELP {name} {gauge.description}")
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name} {gauge.get()}")
            # Histograms
            for name, hist in sorted(self._histograms.items()):
                if hist.description:
                    lines.append(f"# HELP {name} {hist.description}")
                lines.append(f"# TYPE {name} histogram")
                stats = hist.get_stats()
                lines.append(f'{name}_count {stats["count"]}')
                lines.append(f'{name}_sum {stats["sum"]}')
                lines.append(f'{name}_avg {stats["avg"]}')
                lines.append(f'{name}_p50 {stats["p50"]}')
                lines.append(f'{name}_p95 {stats["p95"]}')
                lines.append(f'{name}_p99 {stats["p99"]}')
        return "\n".join(lines) + "\n"

    def get_all_metrics(self) -> Dict[str, Any]:
        """获取所有指标的详细快照。"""
        with self._lock:
            return {
                "counters": {
                    n: c.get() for n, c in self._counters.items()
                },
                "gauges": {
                    n: g.get() for n, g in self._gauges.items()
                },
                "histograms": {
                    n: h.get_stats() for n, h in self._histograms.items()
                },
                "timestamp": time.time(),
            }

    def reset(self) -> None:
        """重置所有指标（测试辅助）。"""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._history.clear()


# 全局单例
_global_collector: Optional[MetricsCollector] = None
_global_lock = threading.Lock()


def get_metrics_collector() -> MetricsCollector:
    """获取全局指标采集器单例。"""
    global _global_collector
    if _global_collector is None:
        with _global_lock:
            if _global_collector is None:
                _global_collector = MetricsCollector()
    return _global_collector


def reset_metrics_collector() -> None:
    """重置全局指标采集器（测试辅助）。"""
    global _global_collector
    with _global_lock:
        _global_collector = None
