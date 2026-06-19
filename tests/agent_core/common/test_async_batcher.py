"""
异步批量操作模块测试。

覆盖：批量触发、超时触发、错误传播、连接池管理。
"""

import asyncio

import pytest

from agent_core.common.async_batcher import AsyncBatcher, ConnectionPool


class TestAsyncBatcher:
    """AsyncBatcher测试类。"""

    @pytest.fixture
    def batcher(self):
        """创建批量处理器实例。"""
        async def processor(items):
            return [x * 2 for x in items]
        return AsyncBatcher(processor, batch_size=3, max_wait_seconds=0.05)

    @pytest.mark.asyncio
    async def test_batch_by_size(self, batcher):
        """测试按容量触发批量处理。"""
        results = await asyncio.gather(
            batcher.submit(1),
            batcher.submit(2),
            batcher.submit(3),
        )
        assert results == [2, 4, 6]

    @pytest.mark.asyncio
    async def test_batch_by_timeout(self, batcher):
        """测试按超时触发批量处理。"""
        result = await batcher.submit(5)
        assert result == 10

    @pytest.mark.asyncio
    async def test_error_propagation(self, batcher):
        """测试错误传播到所有等待者。"""
        async def fail_processor(items):
            raise ValueError("batch error")
        fail_batcher = AsyncBatcher(fail_processor, batch_size=2)
        with pytest.raises(ValueError, match="batch error"):
            await fail_batcher.submit(1)

    @pytest.mark.asyncio
    async def test_shutdown_flushes(self, batcher):
        """测试关闭时刷新剩余请求。"""
        future = asyncio.create_task(batcher.submit(7))
        await batcher.shutdown()
        result = await future
        assert result == 14


class TestConnectionPool:
    """ConnectionPool测试类。"""

    @pytest.fixture
    def pool(self):
        """创建连接池实例。"""
        calls = []
        async def factory():
            calls.append(1)
            return {"conn_id": len(calls)}
        p = ConnectionPool(factory, max_size=2)
        p._calls = calls
        return p

    @pytest.mark.asyncio
    async def test_acquire_creates_new(self, pool):
        """测试首次获取创建新连接。"""
        conn = await pool.acquire()
        assert conn["conn_id"] == 1
        assert pool.in_use_count == 1

    @pytest.mark.asyncio
    async def test_release_reuses(self, pool):
        """测试归还后复用连接。"""
        conn = await pool.acquire()
        await pool.release(conn)
        conn2 = await pool.acquire()
        assert conn2["conn_id"] == 1
        assert pool.available_count == 0

    @pytest.mark.asyncio
    async def test_max_size(self, pool):
        """测试最大容量限制。"""
        c1 = await pool.acquire()
        c2 = await pool.acquire()
        c3 = await pool.acquire()
        await pool.release(c1)
        await pool.release(c2)
        await pool.release(c3)
        assert pool.available_count <= 2
