"""
模型压缩模块。

实现参数剪枝和量化，减少模型存储和计算开销。

第一性原理：
- 神经网络存在大量冗余参数
- 低精度表示对推理影响有限
- 剪枝后模型需要微调恢复精度
"""

from typing import Any, Dict, List, Optional

import numpy as np

from agent_core.common.logger import get_logger


class ModelCompressor:
    """
    模型压缩器。

    提供剪枝和量化功能。
    """

    def __init__(self) -> None:
        self._logger = get_logger()

    def prune(
        self, params: List[np.ndarray], sparsity: float = 0.5
    ) -> List[np.ndarray]:
        """
        按幅度剪枝参数。

        Args:
            params: 模型参数列表。
            sparsity: 剪枝比例（0-1）。

        Returns:
            剪枝后的参数（稀疏表示）。
        """
        pruned: List[np.ndarray] = []
        for p in params:
            threshold = np.percentile(np.abs(p), sparsity * 100)
            mask = np.abs(p) >= threshold
            pruned.append(p * mask)
        self._logger.info(f"[ModelCompressor] Pruned {sparsity * 100:.0f}% params")
        return pruned

    def quantize(
        self, params: List[np.ndarray], bits: int = 8
    ) -> List[Dict[str, Any]]:
        """
        线性量化参数。

        Args:
            params: 模型参数列表。
            bits: 量化位数。

        Returns:
            量化后的参数字典列表（含scale和zero_point）。
        """
        quantized: List[Dict[str, Any]] = []
        for p in params:
            min_val = float(np.min(p))
            max_val = float(np.max(p))
            scale = (max_val - min_val) / (2 ** bits - 1) if max_val != min_val else 1.0
            zero_point = int(-min_val / scale) if scale != 0 else 0
            q = np.round((p - min_val) / scale).astype(np.int32)
            quantized.append({
                "values": q,
                "scale": scale,
                "zero_point": zero_point,
                "shape": p.shape,
            })
        self._logger.info(f"[ModelCompressor] Quantized to {bits} bits")
        return quantized

    def dequantize(self, quantized: List[Dict[str, Any]]) -> List[np.ndarray]:
        """
        反量化参数。

        Args:
            quantized: 量化后的参数字典列表。

        Returns:
            浮点参数列表。
        """
        params: List[np.ndarray] = []
        for q in quantized:
            p = (q["values"].astype(np.float64) - q["zero_point"]) * q["scale"]
            params.append(p.reshape(q["shape"]))
        return params

    def compute_compression_ratio(
        self, original: List[np.ndarray], compressed: List[Any]
    ) -> float:
        """
        计算压缩比。

        Args:
            original: 原始参数。
            compressed: 压缩后参数。

        Returns:
            压缩比（原始大小/压缩后大小）。
        """
        orig_size = sum(p.nbytes for p in original)
        comp_size = sum(
            c["values"].nbytes + 16 for c in compressed
            if isinstance(c, dict)
        )
        if comp_size == 0:
            return 1.0
        return orig_size / comp_size
