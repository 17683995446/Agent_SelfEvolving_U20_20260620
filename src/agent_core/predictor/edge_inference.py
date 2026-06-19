"""
边缘推理优化模块。

实现轻量级推理优化，适用于资源受限环境。

第一性原理：
- 边缘设备计算和内存受限
- 批量处理摊销固定开销
- 缓存预热减少冷启动延迟
"""

import time
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from agent_core.common.compute_cache import ComputeCache
from agent_core.common.logger import get_logger


class EdgeInference:
    """
    边缘推理引擎。

    提供批量合并、缓存预热和异步预取功能。
    """

    def __init__(
        self,
        inference_fn: Callable[[np.ndarray], np.ndarray],
        batch_size: int = 8,
    ) -> None:
        self._inference = inference_fn
        self._batch_size = batch_size
        self._cache = ComputeCache(max_size=64, ttl_seconds=300.0)
        self._logger = get_logger()

    def predict(self, input_data: np.ndarray) -> np.ndarray:
        """
        单条推理，优先查缓存。

        Args:
            input_data: 输入数组。

        Returns:
            输出数组。
        """
        key = self._make_key(input_data)
        return self._cache.get_or_compute(
            key, lambda: self._inference(input_data)
        )

    def predict_batch(self, inputs: List[np.ndarray]) -> List[np.ndarray]:
        """
        批量推理，自动合并批次。

        Args:
            inputs: 输入数组列表。

        Returns:
            输出数组列表。
        """
        results: List[np.ndarray] = []
        for i in range(0, len(inputs), self._batch_size):
            batch = inputs[i : i + self._batch_size]
            stacked = np.stack(batch)
            batch_out = self._inference(stacked)
            results.extend([batch_out[j] for j in range(len(batch))])
        return results

    def warm_cache(self, sample_inputs: List[np.ndarray]) -> None:
        """
        预热缓存。

        Args:
            sample_inputs: 样本输入列表。
        """
        for inp in sample_inputs:
            _ = self.predict(inp)
        self._logger.info(
            f"[EdgeInference] Cache warmed with {len(sample_inputs)} samples"
        )

    def _make_key(self, arr: np.ndarray) -> str:
        """为数组生成缓存键。"""
        return hash(arr.tobytes()) % (2 ** 32)

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计。"""
        return {"cache_size": self._cache.size}
