"""
对象池模块测试。

覆盖：预分配、获取归还、上限控制、重置逻辑、NumPy数组池。
"""

import numpy as np
import pytest

from agent_core.common.object_pool import ObjectPool, NumpyArrayPool


class TestObjectPool:
    """ObjectPool测试类。"""

    @pytest.fixture
    def pool(self):
        """创建对象池实例。"""
        return ObjectPool(
            factory=lambda: {"data": 0},
            reset=lambda obj: obj.update({"data": 0}),
            initial_size=3,
            max_size=5,
        )

    def test_preallocate(self, pool):
        """测试预分配。"""
        assert pool.available_count == 3
        assert pool.in_use_count == 0

    def test_acquire_from_pool(self, pool):
        """测试从池中获取对象。"""
        obj = pool.acquire()
        assert obj == {"data": 0}
        assert pool.available_count == 2
        assert pool.in_use_count == 1

    def test_release_back_to_pool(self, pool):
        """测试归还对象到池。"""
        obj = pool.acquire()
        obj["data"] = 42
        pool.release(obj)
        assert pool.available_count == 3
        assert pool.in_use_count == 0
        obj2 = pool.acquire()
        assert obj2["data"] == 0

    def test_acquire_beyond_initial(self, pool):
        """测试超出预分配数量时动态创建。"""
        objs = [pool.acquire() for _ in range(5)]
        assert pool.available_count == 0
        assert pool.in_use_count == 5
        obj6 = pool.acquire()
        assert obj6 is not None
        assert pool.in_use_count == 6

    def test_max_size_limit(self, pool):
        """测试最大容量限制。"""
        objs = [pool.acquire() for _ in range(10)]
        for obj in objs:
            pool.release(obj)
        assert pool.available_count <= 5

    def test_clear(self, pool):
        """测试清空池。"""
        pool.acquire()
        pool.clear()
        assert pool.available_count == 0
        assert pool.in_use_count == 0


class TestNumpyArrayPool:
    """NumpyArrayPool测试类。"""

    @pytest.fixture
    def arr_pool(self):
        """创建数组池实例。"""
        return NumpyArrayPool(shape=(10,), dtype="float32", initial_size=2)

    def test_acquire_zeroed(self, arr_pool):
        """测试获取的数组已清零。"""
        arr = arr_pool.acquire()
        assert arr.shape == (10,)
        assert np.all(arr == 0)

    def test_release_reset(self, arr_pool):
        """测试归还后数组被重置。"""
        arr = arr_pool.acquire()
        arr[:] = 1.0
        arr_pool.release(arr)
        arr2 = arr_pool.acquire()
        assert np.all(arr2 == 0)

    def test_pool_counts(self, arr_pool):
        """测试池计数。"""
        assert arr_pool.available_count == 2
        arr = arr_pool.acquire()
        assert arr_pool.available_count == 1
        assert arr_pool.in_use_count == 1
