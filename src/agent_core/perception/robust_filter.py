"""
鲁棒滤波模块。

感知层噪声过滤、异常值检测与对抗样本防御。

第一性原理：
- 感官输入天然带有噪声，神经系统通过抑制性回路过滤
- 异常值检测防止单点故障污染整个状态表示
- 对抗防御通过输入平滑降低梯度攻击效果
"""

from typing import Any, Dict, List, Optional

import numpy as np


class RobustFilter:
    """
    鲁棒滤波器。

    提供中值滤波、异常值检测、输入平滑功能。
    """

    def __init__(self, window_size: int = 5, outlier_threshold: float = 3.0) -> None:
        self._window_size = window_size
        self._outlier_threshold = outlier_threshold
        self._history: List[np.ndarray] = []

    def filter(self, raw_vector: np.ndarray) -> np.ndarray:
        """
        对输入向量进行鲁棒滤波。

        步骤：1) 异常值检测与裁剪；2) 历史窗口中值平滑。

        Args:
            raw_vector: 原始输入向量。

        Returns:
            滤波后的向量。
        """
        clipped = self._clip_outliers(raw_vector)
        smoothed = self._median_smooth(clipped)
        return smoothed

    def _clip_outliers(self, vector: np.ndarray) -> np.ndarray:
        """
        基于历史统计裁剪异常值。

        Args:
            vector: 输入向量。

        Returns:
            裁剪后的向量。
        """
        if len(self._history) < 3:
            return vector
        history_array = np.stack(self._history[-10:])
        mean = np.mean(history_array, axis=0)
        std = np.std(history_array, axis=0) + 1e-10
        z_scores = np.abs((vector - mean) / std)
        mask = z_scores > self._outlier_threshold
        clipped = vector.copy()
        clipped[mask] = mean[mask] + np.sign(vector[mask] - mean[mask]) * (
            self._outlier_threshold * std[mask]
        )
        return clipped

    def _median_smooth(self, vector: np.ndarray) -> np.ndarray:
        """
        中值平滑。

        Args:
            vector: 输入向量。

        Returns:
            平滑后的向量。
        """
        self._history.append(vector.copy())
        if len(self._history) > self._window_size:
            self._history.pop(0)
        if len(self._history) < 3:
            return vector
        window = np.stack(self._history)
        median = np.median(window, axis=0)
        alpha = 0.7
        return alpha * vector + (1.0 - alpha) * median

    def detect_anomaly(self, vector: np.ndarray) -> bool:
        """
        检测输入是否为异常值。

        Args:
            vector: 输入向量。

        Returns:
            异常返回True。
        """
        if len(self._history) < 3:
            return False
        history_array = np.stack(self._history[-10:])
        mean = np.mean(history_array, axis=0)
        std = np.std(history_array, axis=0) + 1e-10
        z_scores = np.abs((vector - mean) / std)
        return bool(np.any(z_scores > self._outlier_threshold * 2))

    def reset(self) -> None:
        """重置历史窗口。"""
        self._history.clear()


class AdversarialDefender:
    """
    对抗防御器。

    通过输入随机化与梯度掩码防御对抗攻击。
    """

    def __init__(self, noise_scale: float = 0.01, clip_range: tuple = (0.0, 1.0)) -> None:
        self._noise_scale = noise_scale
        self._clip_min = clip_range[0]
        self._clip_max = clip_range[1]

    def defend(self, vector: np.ndarray) -> np.ndarray:
        """
        对输入施加防御变换。

        步骤：1) 随机噪声；2) 量化；3) 裁剪。

        Args:
            vector: 输入向量。

        Returns:
            防御后的向量。
        """
        noisy = self._add_random_noise(vector)
        quantized = self._quantize(noisy)
        return np.clip(quantized, self._clip_min, self._clip_max)

    def _add_random_noise(self, vector: np.ndarray) -> np.ndarray:
        """添加随机噪声破坏对抗模式。"""
        noise = np.random.normal(0, self._noise_scale, size=vector.shape)
        return vector + noise.astype(vector.dtype)

    def _quantize(self, vector: np.ndarray) -> np.ndarray:
        """量化降低对抗精度。"""
        levels = 64
        return np.round(vector * levels) / levels
