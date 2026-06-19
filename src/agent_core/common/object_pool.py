"""
对象池模块。

预分配并复用高频对象，减少内存分配和GC开销。

第一性原理：
- 内存分配是昂贵操作，应批量预分配
- 对象复用避免频繁创建销毁
- 池大小必须有上限，防止内存泄漏
"""

from typing import Any, Callable, Dict, List, Optional, TypeVar

from agent_core.common.logger import get_logger

T = TypeVar("T")


class ObjectPool:
    """
    通用对象池。

    维护预分配对象队列，支持借出和归还。
    """

    def __init__(
        self,
        factory: Callable[[], T],
        reset: Optional[Callable[[T], None]] = None,
        initial_size: int = 10,
        max_size: int = 100,
    ) -> None:
        self._factory = factory
        self._reset = reset
        self._max_size = max_size
        self._available: List[T] = []
        self._in_use: int = 0
        self._logger = get_logger()
        self._preallocate(initial_size)

    def _preallocate(self, count: int) -> None:
        """预分配对象。"""
        for _ in range(count):
            self._available.append(self._factory())
        self._logger.info(
            f"[ObjectPool] Preallocated {count} objects"
        )

    def acquire(self) -> T:
        """
        从池中获取对象。

        Returns:
            池化对象。
        """
        if self._available:
            obj = self._available.pop()
        else:
            obj = self._factory()
        self._in_use += 1
        return obj

    def release(self, obj: T) -> None:
        """
        归还对象到池。

        Args:
            obj: 要归还的对象。
        """
        if self._reset is not None:
            self._reset(obj)
        if len(self._available) < self._max_size:
            self._available.append(obj)
        self._in_use -= 1

    @property
    def available_count(self) -> int:
        """可用对象数量。"""
        return len(self._available)

    @property
    def in_use_count(self) -> int:
        """正在使用的对象数量。"""
        return self._in_use

    def clear(self) -> None:
        """清空对象池。"""
        self._available.clear()
        self._in_use = 0


class NumpyArrayPool:
    """
    NumPy数组专用对象池。

    预分配固定形状的数组，支持零拷贝复用。
    """

    def __init__(
        self,
        shape: tuple,
        dtype: str = "float32",
        initial_size: int = 10,
        max_size: int = 100,
    ) -> None:
        import numpy as np
        self._shape = shape
        self._dtype = dtype
        self._pool = ObjectPool(
            factory=lambda: np.zeros(shape, dtype=dtype),
            reset=lambda arr: arr.fill(0),
            initial_size=initial_size,
            max_size=max_size,
        )

    def acquire(self) -> Any:
        """获取数组。"""
        return self._pool.acquire()

    def release(self, arr: Any) -> None:
        """归还数组。"""
        self._pool.release(arr)

    @property
    def available_count(self) -> int:
        """可用数组数量。"""
        return self._pool.available_count

    @property
    def in_use_count(self) -> int:
        """正在使用的数组数量。"""
        return self._pool.in_use_count
