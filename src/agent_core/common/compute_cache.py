"""
计算缓存模块。

为频繁计算提供结果缓存，减少重复运算。

第一性原理：
- 缓存只加速不改变的结果
- LRU淘汰避免内存无限增长
- 缓存键必须包含所有影响结果的输入
"""

import hashlib
import json
import time
from typing import Any, Callable, Dict, Optional, Tuple

from agent_core.common.logger import get_logger


class ComputeCache:
    """
    计算缓存。

    基于LRU策略的函数结果缓存。
    """

    def __init__(self, max_size: int = 128, ttl_seconds: float = 60.0) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._access_order: Dict[str, float] = {}
        self._logger = get_logger()

    def get_or_compute(
        self, key: str, compute: Callable[[], Any]
    ) -> Any:
        """
        获取缓存值，不存在则计算并缓存。

        Args:
            key: 缓存键。
            compute: 计算函数。

        Returns:
            缓存值或计算结果。
        """
        now = time.monotonic()
        if key in self._cache:
            value, expiry = self._cache[key]
            if now < expiry:
                self._access_order[key] = now
                return value
            del self._cache[key]
            del self._access_order[key]
        result = compute()
        self._set(key, result, now)
        return result

    def _set(self, key: str, value: Any, now: float) -> None:
        """设置缓存值。"""
        if len(self._cache) >= self._max_size:
            self._evict_oldest()
        self._cache[key] = (value, now + self._ttl)
        self._access_order[key] = now

    def _evict_oldest(self) -> None:
        """淘汰最久未使用的缓存项。"""
        if not self._access_order:
            return
        oldest = min(self._access_order, key=self._access_order.get)
        del self._cache[oldest]
        del self._access_order[oldest]

    def invalidate(self, key: str) -> None:
        """使指定缓存项失效。"""
        self._cache.pop(key, None)
        self._access_order.pop(key, None)

    def clear(self) -> None:
        """清空缓存。"""
        self._cache.clear()
        self._access_order.clear()

    @property
    def size(self) -> int:
        """当前缓存大小。"""
        return len(self._cache)

    @staticmethod
    def make_key(*args: Any, **kwargs: Any) -> str:
        """
        根据参数生成缓存键。

        Args:
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            哈希键字符串。
        """
        data = json.dumps(
            {"args": args, "kwargs": kwargs},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]
