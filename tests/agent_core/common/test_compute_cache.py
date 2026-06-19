"""
计算缓存模块测试。

覆盖：缓存命中、计算执行、TTL过期、LRU淘汰、清空、键生成。
"""

import time

import pytest

from agent_core.common.compute_cache import ComputeCache


class TestComputeCache:
    """ComputeCache测试类。"""

    @pytest.fixture
    def cache(self):
        """创建缓存实例。"""
        return ComputeCache(max_size=3, ttl_seconds=1.0)

    def test_cache_miss_computes(self, cache):
        """测试缓存未命中时执行计算。"""
        calls = []
        def compute():
            calls.append(1)
            return 42
        result = cache.get_or_compute("key1", compute)
        assert result == 42
        assert len(calls) == 1

    def test_cache_hit_skips_compute(self, cache):
        """测试缓存命中时跳过计算。"""
        calls = []
        def compute():
            calls.append(1)
            return 42
        cache.get_or_compute("key1", compute)
        result = cache.get_or_compute("key1", compute)
        assert result == 42
        assert len(calls) == 1

    def test_ttl_expiration(self, cache):
        """测试TTL过期后重新计算。"""
        calls = []
        def compute():
            calls.append(1)
            return 42
        cache.get_or_compute("key1", compute)
        time.sleep(1.1)
        cache.get_or_compute("key1", compute)
        assert len(calls) == 2

    def test_lru_eviction(self, cache):
        """测试LRU淘汰。"""
        cache.get_or_compute("a", lambda: 1)
        cache.get_or_compute("b", lambda: 2)
        cache.get_or_compute("c", lambda: 3)
        cache.get_or_compute("a", lambda: 1)
        cache.get_or_compute("d", lambda: 4)
        assert cache.size == 3
        assert "b" not in cache._cache

    def test_invalidate(self, cache):
        """测试手动失效。"""
        cache.get_or_compute("k", lambda: 1)
        cache.invalidate("k")
        assert cache.size == 0

    def test_clear(self, cache):
        """测试清空缓存。"""
        cache.get_or_compute("a", lambda: 1)
        cache.get_or_compute("b", lambda: 2)
        cache.clear()
        assert cache.size == 0

    def test_make_key_consistency(self):
        """测试键生成一致性。"""
        k1 = ComputeCache.make_key("a", 1, x=2)
        k2 = ComputeCache.make_key("a", 1, x=2)
        assert k1 == k2

    def test_make_key_uniqueness(self):
        """测试键生成唯一性。"""
        k1 = ComputeCache.make_key("a", 1)
        k2 = ComputeCache.make_key("a", 2)
        assert k1 != k2
