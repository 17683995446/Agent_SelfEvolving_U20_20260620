"""
性能监控模块。

实时采集系统性能指标，支持延迟分布和吞吐量统计。

第一性原理：
- 可观测性是优化的前提
- 指标采集必须低开销
- 窗口统计反映近期趋势
"""

import time
from collections import deque
from typing import Any, Dict, List, Optional

from agent_core.common.logger import get_logger


class PerformanceMonitor:
    """
    性能监控器。

    记录操作延迟、吞吐量、错误率等关键指标。
    """

    def __init__(self, window_size: int = 100) -> None:
        self._window_size = window_size
        self._latencies: deque = deque(maxlen=window_size)
        self._throughput_count = 0
        self._throughput_window_start = time.monotonic()
        self._error_count = 0
        self._total_count = 0
        self._logger = get_logger()

    def record_latency(self, latency_seconds: float) -> None:
        """
        记录一次操作延迟。

        Args:
            latency_seconds: 延迟秒数。
        """
        self._latencies.append(latency_seconds)
        self._total_count += 1

    def record_error(self) -> None:
        """记录一次错误。"""
        self._error_count += 1
        self._total_count += 1

    def record_throughput(self, count: int = 1) -> None:
        """
        记录吞吐量。

        Args:
            count: 操作次数。
        """
        self._throughput_count += count

    def get_metrics(self) -> Dict[str, Any]:
        """
        获取当前性能指标。

        Returns:
            指标字典。
        """
        now = time.monotonic()
        window_duration = now - self._throughput_window_start
        throughput = (
            self._throughput_count / window_duration if window_duration > 0 else 0.0
        )
        latencies = list(self._latencies)
        if latencies:
            latencies.sort()
            p50 = latencies[len(latencies) // 2]
            p99 = latencies[int(len(latencies) * 0.99)] if len(latencies) >= 100 else latencies[-1]
            avg = sum(latencies) / len(latencies)
        else:
            p50 = p99 = avg = 0.0
        error_rate = (
            self._error_count / self._total_count if self._total_count > 0 else 0.0
        )
        return {
            "throughput": round(throughput, 2),
            "latency_p50_ms": round(p50 * 1000, 2),
            "latency_p99_ms": round(p99 * 1000, 2),
            "latency_avg_ms": round(avg * 1000, 2),
            "error_rate": round(error_rate, 4),
            "total_operations": self._total_count,
        }

    def reset_throughput_window(self) -> None:
        """重置吞吐量统计窗口。"""
        self._throughput_count = 0
        self._throughput_window_start = time.monotonic()

    def snapshot(self) -> Dict[str, Any]:
        """
        获取指标快照并重置吞吐量窗口。

        Returns:
            指标字典。
        """
        metrics = self.get_metrics()
        self.reset_throughput_window()
        return metrics
