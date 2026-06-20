"""
令牌桶速率限制器。

防止暴力破解与拒绝服务攻击。

第一性原理：
- 生物神经系统的不应期（refractory period）：神经元放电后需要恢复时间，
  防止过度刺激导致系统崩溃
- 令牌桶算法：以恒定速率补充令牌，请求消耗令牌，桶满则丢弃多余令牌
- 允许突发（burst）但限制长期平均速率

设计要点：
- 按键（key）独立限流：每个调用方独立计数
- 线程安全：多线程并发请求
- 自动过期：长时间无请求的键自动清理，避免内存泄漏
"""

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

from agent_core.common.logger import get_logger

# 默认令牌补充速率（令牌/秒）
_DEFAULT_RATE = 10.0
# 默认桶容量（允许的突发请求数）
_DEFAULT_CAPACITY = 20.0
# 键过期时间（秒）：超过此时间无请求则清理
_DEFAULT_KEY_TTL = 300.0
# 清理周期（秒）
_CLEANUP_INTERVAL = 60.0


@dataclass
class RateLimitResult:
    """速率限制检查结果。"""

    allowed: bool
    remaining: float
    retry_after: float


class _TokenBucket:
    """单键令牌桶。"""

    __slots__ = ("rate", "capacity", "tokens", "last_refill", "last_access")

    def __init__(self, rate: float, capacity: float) -> None:
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self.last_access = self.last_refill

    def refill(self, now: float) -> None:
        """补充令牌。"""
        elapsed = now - self.last_refill
        if elapsed <= 0:
            return
        self.tokens = min(
            self.capacity, self.tokens + elapsed * self.rate
        )
        self.last_refill = now

    def consume(self, now: float, cost: float = 1.0) -> RateLimitResult:
        """消耗令牌。"""
        self.last_access = now
        self.refill(now)
        if self.tokens >= cost:
            self.tokens -= cost
            return RateLimitResult(
                allowed=True, remaining=self.tokens, retry_after=0.0
            )
        deficit = cost - self.tokens
        retry_after = deficit / self.rate if self.rate > 0 else float("inf")
        return RateLimitResult(
            allowed=False, remaining=self.tokens, retry_after=retry_after
        )


class RateLimiter:
    """
    令牌桶速率限制器。

    按键独立限流，支持突发与长期平均速率控制。
    """

    def __init__(
        self,
        rate: float = _DEFAULT_RATE,
        capacity: float = _DEFAULT_CAPACITY,
        key_ttl: float = _DEFAULT_KEY_TTL,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._rate = rate
        self._capacity = capacity
        self._key_ttl = key_ttl
        self._buckets: Dict[str, _TokenBucket] = {}
        self._lock = threading.Lock()
        self._logger = get_logger()
        self._last_cleanup = time.monotonic()

    def check(
        self, key: str, cost: float = 1.0
    ) -> RateLimitResult:
        """
        检查是否允许请求。

        Args:
            key: 限流键（如模块名、用户ID）。
            cost: 本次请求消耗的令牌数。

        Returns:
            速率限制结果。
        """
        now = time.monotonic()
        with self._lock:
            self._maybe_cleanup(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _TokenBucket(self._rate, self._capacity)
                self._buckets[key] = bucket
            result = bucket.consume(now, cost)
            if not result.allowed:
                self._logger.warning(
                    f"[RateLimiter] Key '{key}' rate-limited, "
                    f"retry_after={result.retry_after:.2f}s"
                )
            return result

    def allow(self, key: str, cost: float = 1.0) -> bool:
        """便捷方法：仅返回是否允许。"""
        return self.check(key, cost).allowed

    def reset(self, key: Optional[str] = None) -> None:
        """重置指定键或全部键的令牌桶。"""
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)

    def get_stats(self, key: str) -> Optional[Dict[str, float]]:
        """获取指定键的统计信息。"""
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                return None
            now = time.monotonic()
            bucket.refill(now)
            return {
                "tokens": bucket.tokens,
                "capacity": bucket.capacity,
                "rate": bucket.rate,
            }

    def _maybe_cleanup(self, now: float) -> None:
        """定期清理过期键。"""
        if now - self._last_cleanup < _CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        expired = [
            k
            for k, b in self._buckets.items()
            if now - b.last_access > self._key_ttl
        ]
        for k in expired:
            del self._buckets[k]
        if expired:
            self._logger.info(
                f"[RateLimiter] Cleaned up {len(expired)} expired keys"
            )
