"""
C-11超复杂场景测试：可观测性与运维自动化。

验证C-11新增能力在极端复杂场景下的正确性：
- 统一指标采集器：Counter/Gauge/Histogram 三种类型
- Prometheus 格式导出：文本格式兼容
- 异常检测告警：Z-score 统计异常 + 变化率告警
- 指标历史与趋势分析
- 采集回调集成
- 线程安全并发采集
"""

import threading
import time
import unittest
from typing import Dict, List

from agent_core.monitoring.alert_engine import AlertEngine
from agent_core.monitoring.anomaly_detection import (
    AnomalyDetectionRule,
    RateOfChangeRule,
)
from agent_core.monitoring.metrics_collector import (
    Counter,
    Gauge,
    Histogram,
    MetricsCollector,
    get_metrics_collector,
    reset_metrics_collector,
)


class TestCounter(unittest.TestCase):
    """计数器验证。"""

    def test_inc_and_get(self) -> None:
        """增加并获取值。"""
        c = Counter("requests", "Total requests")
        c.inc()
        c.inc(2.5)
        self.assertEqual(c.get(), 3.5)

    def test_thread_safety(self) -> None:
        """并发增加线程安全。"""
        c = Counter("concurrent")
        threads = [threading.Thread(target=lambda: [c.inc() for _ in range(100)]) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(c.get(), 1000)


class TestGauge(unittest.TestCase):
    """瞬时值验证。"""

    def test_set_inc_dec(self) -> None:
        """设置/增加/减少。"""
        g = Gauge("queue_size", "Current queue size")
        g.set(10)
        self.assertEqual(g.get(), 10)
        g.inc(5)
        self.assertEqual(g.get(), 15)
        g.dec(3)
        self.assertEqual(g.get(), 12)

    def test_negative_allowed(self) -> None:
        """允许负值。"""
        g = Gauge("delta")
        g.set(5)
        g.dec(10)
        self.assertEqual(g.get(), -5)


class TestHistogram(unittest.TestCase):
    """柱状图验证。"""

    def test_observe_and_stats(self) -> None:
        """观测并获取统计。"""
        h = Histogram("latency", "Request latency")
        for v in [0.01, 0.02, 0.03, 0.1, 0.5]:
            h.observe(v)
        stats = h.get_stats()
        self.assertEqual(stats["count"], 5)
        self.assertGreater(stats["sum"], 0)
        self.assertGreater(stats["avg"], 0)

    def test_percentile(self) -> None:
        """百分位计算。"""
        h = Histogram("latency")
        for i in range(100):
            h.observe(float(i) / 1000.0)  # 0.000 to 0.099
        p50 = h.get_percentile(50)
        p99 = h.get_percentile(99)
        self.assertGreater(p50, 0.04)
        self.assertLess(p50, 0.06)
        self.assertGreater(p99, 0.09)

    def test_empty_histogram(self) -> None:
        """空柱状图统计为零。"""
        h = Histogram("empty")
        stats = h.get_stats()
        self.assertEqual(stats["count"], 0)
        self.assertEqual(stats["p50"], 0.0)


class TestMetricsCollector(unittest.TestCase):
    """统一指标采集器验证。"""

    def setUp(self) -> None:
        reset_metrics_collector()

    def test_register_counter(self) -> None:
        """注册计数器。"""
        collector = MetricsCollector()
        c = collector.register_counter("http_requests", "HTTP requests")
        c.inc(5)
        metrics = collector.collect_all()
        self.assertEqual(metrics["http_requests"], 5)

    def test_register_gauge(self) -> None:
        """注册瞬时值。"""
        collector = MetricsCollector()
        g = collector.register_gauge("active_connections")
        g.set(42)
        metrics = collector.collect_all()
        self.assertEqual(metrics["active_connections"], 42)

    def test_register_histogram(self) -> None:
        """注册柱状图。"""
        collector = MetricsCollector()
        h = collector.register_histogram("request_latency")
        h.observe(0.1)
        h.observe(0.2)
        metrics = collector.collect_all()
        self.assertEqual(metrics["request_latency_count"], 2)
        self.assertIn("request_latency_p50", metrics)
        self.assertIn("request_latency_p99", metrics)

    def test_duplicate_register_returns_same(self) -> None:
        """重复注册返回同一实例。"""
        collector = MetricsCollector()
        c1 = collector.register_counter("dup")
        c2 = collector.register_counter("dup")
        self.assertIs(c1, c2)

    def test_add_collector_callback(self) -> None:
        """外部采集回调。"""
        collector = MetricsCollector()
        collector.add_collector(lambda: {"custom_metric": 99.0})
        metrics = collector.collect_all()
        self.assertEqual(metrics["custom_metric"], 99.0)

    def test_collector_callback_exception_handled(self) -> None:
        """采集回调异常不崩溃。"""
        collector = MetricsCollector()

        def bad_collector() -> Dict[str, float]:
            raise RuntimeError("collector broken")

        collector.add_collector(bad_collector)
        collector.register_counter("good")
        metrics = collector.collect_all()
        self.assertIn("good", metrics)

    def test_history_recorded(self) -> None:
        """指标历史被记录。"""
        collector = MetricsCollector()
        c = collector.register_counter("hist_test")
        c.inc()
        collector.collect_all()
        c.inc()
        collector.collect_all()
        history = collector.get_history("hist_test")
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].value, 1.0)
        self.assertEqual(history[1].value, 2.0)

    def test_get_all_metrics_snapshot(self) -> None:
        """获取所有指标快照。"""
        collector = MetricsCollector()
        collector.register_counter("c1").inc(10)
        collector.register_gauge("g1").set(20)
        collector.register_histogram("h1").observe(0.5)
        snapshot = collector.get_all_metrics()
        self.assertIn("counters", snapshot)
        self.assertIn("gauges", snapshot)
        self.assertIn("histograms", snapshot)
        self.assertEqual(snapshot["counters"]["c1"], 10)
        self.assertEqual(snapshot["gauges"]["g1"], 20)
        self.assertIn("timestamp", snapshot)


class TestPrometheusExport(unittest.TestCase):
    """Prometheus 格式导出验证。"""

    def test_export_contains_all_types(self) -> None:
        """导出包含所有指标类型。"""
        collector = MetricsCollector()
        collector.register_counter("requests_total", "Total requests").inc(100)
        collector.register_gauge("queue_depth", "Queue depth").set(5)
        collector.register_histogram("latency_seconds", "Latency").observe(0.1)
        output = collector.export_prometheus()
        # 验证格式
        self.assertIn("# TYPE requests_total counter", output)
        self.assertIn("requests_total 100", output)
        self.assertIn("# TYPE queue_depth gauge", output)
        self.assertIn("queue_depth 5", output)
        self.assertIn("# TYPE latency_seconds histogram", output)
        self.assertIn("latency_seconds_count", output)
        self.assertIn("latency_seconds_sum", output)

    def test_export_help_comments(self) -> None:
        """导出包含 HELP 注释。"""
        collector = MetricsCollector()
        collector.register_counter("test_metric", "Test description")
        output = collector.export_prometheus()
        self.assertIn("# HELP test_metric Test description", output)

    def test_export_empty_collector(self) -> None:
        """空采集器导出不崩溃。"""
        collector = MetricsCollector()
        output = collector.export_prometheus()
        self.assertEqual(output.strip(), "")


class TestAnomalyDetection(unittest.TestCase):
    """异常检测告警验证。"""

    def test_no_anomaly_on_stable_series(self) -> None:
        """平稳序列不触发异常。"""
        rule = AnomalyDetectionRule(
            name="stable",
            metric_key="latency",
            zscore_threshold=3.0,
            min_samples=10,
        )
        for i in range(20):
            triggered = rule.check({"latency": 0.05})
            self.assertFalse(triggered)

    def test_anomaly_on_spike(self) -> None:
        """突变尖峰触发异常。"""
        rule = AnomalyDetectionRule(
            name="spike",
            metric_key="latency",
            zscore_threshold=3.0,
            min_samples=10,
        )
        # 平稳阶段
        for _ in range(20):
            rule.check({"latency": 0.05})
        # 突变尖峰
        triggered = rule.check({"latency": 5.0})
        self.assertTrue(triggered)

    def test_min_samples_protection(self) -> None:
        """样本不足时不检测。"""
        rule = AnomalyDetectionRule(
            name="early",
            metric_key="latency",
            min_samples=10,
        )
        for _ in range(9):
            self.assertFalse(rule.check({"latency": 100.0}))

    def test_cooldown_prevents_repeat(self) -> None:
        """冷却期防止重复告警。"""
        rule = AnomalyDetectionRule(
            name="cooldown",
            metric_key="latency",
            zscore_threshold=2.0,
            min_samples=10,
            cooldown_seconds=100.0,
        )
        for _ in range(15):
            rule.check({"latency": 0.05})
        # 第一次触发
        triggered1 = rule.check({"latency": 10.0})
        self.assertTrue(triggered1)
        # 冷却期内不重复
        triggered2 = rule.check({"latency": 10.0})
        self.assertFalse(triggered2)

    def test_get_baseline(self) -> None:
        """获取基线统计。"""
        rule = AnomalyDetectionRule(
            name="baseline",
            metric_key="latency",
            min_samples=5,
        )
        for v in [0.1, 0.2, 0.15, 0.12, 0.18]:
            rule.check({"latency": v})
        baseline = rule.get_baseline()
        self.assertIn("mean", baseline)
        self.assertIn("std", baseline)
        self.assertEqual(baseline["samples"], 5)
        self.assertGreater(baseline["mean"], 0.1)

    def test_non_numeric_metric_ignored(self) -> None:
        """非数值指标被忽略。"""
        rule = AnomalyDetectionRule(
            name="nonnumeric",
            metric_key="status",
        )
        self.assertFalse(rule.check({"status": "healthy"}))
        self.assertFalse(rule.check({"status": None}))


class TestRateOfChangeRule(unittest.TestCase):
    """变化率告警验证。"""

    def test_no_alert_on_slow_change(self) -> None:
        """缓慢变化不触发。"""
        rule = RateOfChangeRule(
            name="slow",
            metric_key="cpu",
            max_rate=100.0,  # 每秒最多变化100
            cooldown_seconds=0.0,
        )
        rule.check({"cpu": 50.0})
        time.sleep(0.1)
        self.assertFalse(rule.check({"cpu": 55.0}))

    def test_alert_on_rapid_spike(self) -> None:
        """快速突变触发。"""
        rule = RateOfChangeRule(
            name="spike",
            metric_key="cpu",
            max_rate=10.0,  # 每秒最多变化10
            cooldown_seconds=0.0,
        )
        rule.check({"cpu": 50.0})
        time.sleep(0.05)
        # 短时间内变化 50，变化率约 1000/s > 10
        triggered = rule.check({"cpu": 100.0})
        self.assertTrue(triggered)

    def test_first_sample_no_alert(self) -> None:
        """首个样本不触发（无基线）。"""
        rule = RateOfChangeRule(
            name="first",
            metric_key="cpu",
            max_rate=1.0,
        )
        self.assertFalse(rule.check({"cpu": 100.0}))


class TestAlertEngineIntegration(unittest.TestCase):
    """告警引擎集成验证。"""

    def test_threshold_rule_triggers(self) -> None:
        """阈值规则触发。"""
        from agent_core.monitoring.alert_engine import AlertRule

        engine = AlertEngine()
        rule = AlertRule(
            name="high_latency",
            metric_key="latency_p99_ms",
            threshold=100.0,
            comparator=">",
            cooldown_seconds=0.0,
        )
        engine.add_rule(rule)
        alerts = engine.evaluate({"latency_p99_ms": 150.0})
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["rule"], "high_latency")
        self.assertEqual(alerts[0]["severity"], "critical")

    def test_handler_invoked(self) -> None:
        """告警处理器被调用。"""
        from agent_core.monitoring.alert_engine import AlertRule

        engine = AlertEngine()
        engine.add_rule(
            AlertRule(
                name="test",
                metric_key="value",
                threshold=10,
                comparator=">",
                cooldown_seconds=0,
            )
        )
        received: List[Dict] = []
        engine.add_handler(lambda alert: received.append(alert))
        engine.evaluate({"value": 20})
        self.assertEqual(len(received), 1)

    def test_mixed_rules_evaluation(self) -> None:
        """混合规则评估。"""
        from agent_core.monitoring.alert_engine import AlertRule

        engine = AlertEngine()
        engine.add_rule(
            AlertRule("threshold", "cpu", 80, ">", 0)
        )
        engine.add_rule(
            AnomalyDetectionRule("anomaly", "memory", min_samples=5)
        )
        # 先积累样本
        for _ in range(10):
            engine.evaluate({"cpu": 50, "memory": 0.5})
        # 触发阈值告警 + 异常告警
        alerts = engine.evaluate({"cpu": 90, "memory": 5.0})
        self.assertGreaterEqual(len(alerts), 1)


class TestConcurrentCollection(unittest.TestCase):
    """并发采集验证。"""

    def test_concurrent_collect_no_crash(self) -> None:
        """并发采集不崩溃。"""
        collector = MetricsCollector()
        c = collector.register_counter("concurrent_test")
        g = collector.register_gauge("concurrent_gauge")

        def worker() -> None:
            for _ in range(50):
                c.inc()
                g.set(time.time())
                collector.collect_all()

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 验证最终值
        self.assertEqual(c.get(), 250)

    def test_global_singleton(self) -> None:
        """全局单例一致性。"""
        reset_metrics_collector()
        c1 = get_metrics_collector()
        c2 = get_metrics_collector()
        self.assertIs(c1, c2)


class TestEndToEndObservability(unittest.TestCase):
    """端到端可观测性验证。"""

    def test_full_pipeline(self) -> None:
        """完整指标采集→告警→导出流水线。"""
        collector = MetricsCollector()
        # 注册系统指标
        cycle_counter = collector.register_counter(
            "agent_cycles_total", "Total agent cycles"
        )
        error_gauge = collector.register_gauge(
            "prediction_error", "Current prediction error"
        )
        latency_hist = collector.register_histogram(
            "cycle_latency_seconds", "Cycle latency"
        )
        # 模拟系统运行
        for i in range(20):
            cycle_counter.inc()
            error_gauge.set(0.05 + i * 0.001)
            latency_hist.observe(0.01 + i * 0.0005)
            collector.collect_all()
        # 导出 Prometheus 格式
        output = collector.export_prometheus()
        self.assertIn("agent_cycles_total", output)
        self.assertIn("prediction_error", output)
        self.assertIn("cycle_latency_seconds", output)
        # 验证指标值
        metrics = collector.collect_all()
        self.assertEqual(metrics["agent_cycles_total"], 20)
        self.assertGreater(metrics["prediction_error"], 0.05)
        self.assertEqual(metrics["cycle_latency_seconds_count"], 20)

    def test_alert_on_high_error_rate(self) -> None:
        """高错误率触发告警。"""
        from agent_core.monitoring.alert_engine import AlertRule

        collector = MetricsCollector()
        engine = AlertEngine()
        engine.add_rule(
            AlertRule(
                name="high_error_rate",
                metric_key="error_rate",
                threshold=0.1,
                comparator=">",
                cooldown_seconds=0,
            )
        )
        alerts_received: List[Dict] = []
        engine.add_handler(lambda a: alerts_received.append(a))
        # 正常错误率
        engine.evaluate({"error_rate": 0.02})
        self.assertEqual(len(alerts_received), 0)
        # 高错误率
        engine.evaluate({"error_rate": 0.15})
        self.assertEqual(len(alerts_received), 1)
        self.assertEqual(alerts_received[0]["rule"], "high_error_rate")


if __name__ == "__main__":
    unittest.main()
