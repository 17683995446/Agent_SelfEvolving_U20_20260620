"""
性能监控模块测试。

覆盖：延迟记录、错误记录、吞吐量统计、指标计算、窗口重置。
"""

import time

import pytest

from agent_core.monitoring.performance_monitor import PerformanceMonitor


class TestPerformanceMonitor:
    """PerformanceMonitor测试类。"""

    @pytest.fixture
    def monitor(self):
        """创建监控器实例。"""
        return PerformanceMonitor(window_size=10)

    def test_record_latency(self, monitor):
        """测试延迟记录。"""
        monitor.record_latency(0.01)
        monitor.record_latency(0.02)
        metrics = monitor.get_metrics()
        assert metrics["total_operations"] == 2
        assert metrics["latency_avg_ms"] == 15.0

    def test_record_error(self, monitor):
        """测试错误记录。"""
        monitor.record_latency(0.01)
        monitor.record_error()
        metrics = monitor.get_metrics()
        assert metrics["error_rate"] == 0.5

    def test_throughput(self, monitor):
        """测试吞吐量统计。"""
        monitor.record_throughput(5)
        time.sleep(0.1)
        metrics = monitor.get_metrics()
        assert metrics["throughput"] > 0

    def test_window_size_limit(self, monitor):
        """测试窗口大小限制。"""
        for i in range(20):
            monitor.record_latency(0.001 * i)
        metrics = monitor.get_metrics()
        assert metrics["latency_p50_ms"] > 0

    def test_empty_metrics(self, monitor):
        """测试无数据时指标为零。"""
        metrics = monitor.get_metrics()
        assert metrics["latency_avg_ms"] == 0.0
        assert metrics["error_rate"] == 0.0

    def test_snapshot_resets_throughput(self, monitor):
        """测试快照重置吞吐量窗口。"""
        monitor.record_throughput(10)
        time.sleep(0.1)
        snap1 = monitor.snapshot()
        assert snap1["throughput"] > 0
        snap2 = monitor.snapshot()
        assert snap2["throughput"] == 0.0
