"""
性能基准测试。

验证计算缓存、对象池、批量处理等优化模块的实际效果。
"""

import asyncio
import time

import numpy as np
import pytest

from agent_core.common.compute_cache import ComputeCache
from agent_core.common.object_pool import NumpyArrayPool
from agent_core.common.async_batcher import AsyncBatcher
from agent_core.monitoring.performance_monitor import PerformanceMonitor


class TestComputeCacheBenchmark:
    """计算缓存基准测试。"""

    def test_cache_hit_speedup(self):
        """测试缓存命中加速效果。"""
        cache = ComputeCache(max_size=100, ttl_seconds=10.0)
        def slow_compute():
            time.sleep(0.001)
            return 42
        key = "test"
        cache.get_or_compute(key, slow_compute)
        start = time.monotonic()
        for _ in range(100):
            cache.get_or_compute(key, slow_compute)
        elapsed = time.monotonic() - start
        assert elapsed < 0.01

    def test_cache_make_key_performance(self):
        """测试键生成性能。"""
        start = time.monotonic()
        for i in range(10000):
            ComputeCache.make_key("a", i, x=i * 2)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0


class TestObjectPoolBenchmark:
    """对象池基准测试。"""

    def test_pool_vs_malloc(self):
        """测试对象池对比直接分配。"""
        pool = NumpyArrayPool(shape=(1000,), dtype="float32", initial_size=10)
        start = time.monotonic()
        for _ in range(1000):
            arr = pool.acquire()
            pool.release(arr)
        pool_elapsed = time.monotonic() - start
        start = time.monotonic()
        for _ in range(1000):
            arr = np.zeros((1000,), dtype="float32")
            _ = arr
        malloc_elapsed = time.monotonic() - start
        assert pool_elapsed < malloc_elapsed * 2


class TestAsyncBatcherBenchmark:
    """异步批量处理基准测试。"""

    @pytest.mark.asyncio
    async def test_batch_throughput(self):
        """测试批量处理吞吐量。"""
        async def processor(items):
            return [x * 2 for x in items]
        batcher = AsyncBatcher(processor, batch_size=50, max_wait_seconds=0.01)
        start = time.monotonic()
        results = await asyncio.gather(*[batcher.submit(i) for i in range(100)])
        elapsed = time.monotonic() - start
        assert len(results) == 100
        assert all(r == i * 2 for i, r in enumerate(results))
        assert elapsed < 0.5
        await batcher.shutdown()


class TestPerformanceMonitorBenchmark:
    """性能监控器基准测试。"""

    def test_monitor_overhead(self):
        """测试监控开销。"""
        monitor = PerformanceMonitor(window_size=1000)
        start = time.monotonic()
        for i in range(10000):
            monitor.record_latency(0.0001 * (i % 10))
        elapsed = time.monotonic() - start
        assert elapsed < 1.0
        metrics = monitor.get_metrics()
        assert metrics["total_operations"] == 10000
