"""
异步批量操作模块。

将高频小操作合并为批量大操作，减少I/O往返次数。

第一性原理：
- 批量操作效率远高于单次操作
- 超时触发保证延迟可控
- 容量触发保证吞吐量
"""

import asyncio
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional

from agent_core.common.logger import get_logger


class AsyncBatcher:
    """
    异步批量处理器。

    收集请求，按容量或超时触发批量处理。
    """

    def __init__(
        self,
        processor: Callable[[List[Any]], Coroutine[Any, Any, List[Any]]],
        batch_size: int = 10,
        max_wait_seconds: float = 0.1,
    ) -> None:
        self._processor = processor
        self._batch_size = batch_size
        self._max_wait = max_wait_seconds
        self._queue: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._timer: Optional[asyncio.Task] = None
        self._logger = get_logger()

    async def submit(self, item: Any) -> Any:
        """
        提交单个请求，等待批量处理结果。

        Args:
            item: 请求数据。

        Returns:
            处理结果。
        """
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        async with self._lock:
            self._queue.append({"item": item, "future": future})
            if len(self._queue) >= self._batch_size:
                await self._flush()
            elif self._timer is None:
                self._timer = asyncio.create_task(self._delayed_flush())
        return await future

    async def _delayed_flush(self) -> None:
        """延迟触发刷新。"""
        await asyncio.sleep(self._max_wait)
        async with self._lock:
            if self._queue:
                await self._flush()
            self._timer = None

    async def _flush(self) -> None:
        """执行批量处理。"""
        batch = self._queue[: self._batch_size]
        self._queue = self._queue[self._batch_size :]
        items = [entry["item"] for entry in batch]
        try:
            results = await self._processor(items)
            for entry, result in zip(batch, results):
                entry["future"].set_result(result)
        except Exception as exc:
            for entry in batch:
                entry["future"].set_exception(exc)

    async def shutdown(self) -> None:
        """优雅关闭，处理剩余请求。"""
        if self._timer is not None:
            self._timer.cancel()
            try:
                await self._timer
            except asyncio.CancelledError:
                pass
        async with self._lock:
            while self._queue:
                await self._flush()


class ConnectionPool:
    """
    异步连接池。

    管理可复用的异步连接，支持借出和归还。
    """

    def __init__(
        self,
        factory: Callable[[], Coroutine[Any, Any, Any]],
        max_size: int = 5,
    ) -> None:
        self._factory = factory
        self._max_size = max_size
        self._available: List[Any] = []
        self._in_use: int = 0
        self._lock = asyncio.Lock()
        self._logger = get_logger()

    async def acquire(self) -> Any:
        """获取连接。"""
        async with self._lock:
            if self._available:
                conn = self._available.pop()
            else:
                conn = await self._factory()
            self._in_use += 1
            return conn

    async def release(self, conn: Any) -> None:
        """归还连接。"""
        async with self._lock:
            if len(self._available) < self._max_size:
                self._available.append(conn)
            self._in_use -= 1

    @property
    def available_count(self) -> int:
        """可用连接数。"""
        return len(self._available)

    @property
    def in_use_count(self) -> int:
        """使用中连接数。"""
        return self._in_use
