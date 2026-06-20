"""
高层抽象预测器模块。

均值回归预测器，负责小时级稳态回归。

C-9增强：
- 误差 EMA 衰减（替代全历史平均）
- 概念漂移检测：漂移时重置历史窗口与均值缓存
"""

from collections import deque
from typing import Optional

import numpy as np

from agent_core.common.interfaces import IPredictionModel
from agent_core.predictor.concept_drift import ConceptDriftDetector

# C-9: 误差 EMA 衰减系数
_ERROR_EMA_ALPHA = 0.3


class MeanReversionPredictor(IPredictionModel):
    """
    均值回归预测器。

    C-9增强：误差 EMA、漂移检测。
    """

    def __init__(
        self,
        feature_dimensions: int,
        window_size: int,
        reversion_strength: float,
    ) -> None:
        self._feature_dimensions = feature_dimensions
        self._window_size = window_size
        self._reversion_strength = reversion_strength
        self._history: deque = deque(maxlen=window_size)
        self._error_ema: float = 1.0  # C-9: EMA 误差
        self._error_count = 0
        self._initialized = False
        self._sum_cache: Optional[np.ndarray] = None
        # C-9: 概念漂移检测器
        self._drift_detector = ConceptDriftDetector()
        self._drift_resets = 0

    def predict(self, state: np.ndarray) -> np.ndarray:
        if len(self._history) < 10:
            return np.asarray(state, dtype=np.float32).copy()
        mean_values = self._compute_mean()
        current = np.asarray(state, dtype=np.float32)
        deviation = mean_values - current
        prediction = current + self._reversion_strength * deviation
        return np.clip(prediction, 0.0, 1.0)

    def _compute_mean(self) -> np.ndarray:
        if self._sum_cache is None:
            data = np.array(self._history)
            self._sum_cache = np.sum(data, axis=0)
        return self._sum_cache / len(self._history)

    def update(self, state: np.ndarray, actual: np.ndarray) -> None:
        actual_arr = np.asarray(actual, dtype=np.float32)
        self._add_history(actual_arr)
        self._initialized = True
        if len(self._history) >= 10:
            pred = self.predict(actual_arr)
            error = float(np.mean(np.abs(actual_arr - pred)))
            # C-9: 误差 EMA 更新
            self._error_ema = (
                (1.0 - _ERROR_EMA_ALPHA) * self._error_ema
                + _ERROR_EMA_ALPHA * error
            )
            self._error_count += 1
            # C-9: 概念漂移检测
            if self._drift_detector.update(error):
                self._reset_on_drift()

    def _add_history(self, actual: np.ndarray) -> None:
        if self._sum_cache is not None:
            self._sum_cache += actual
        if len(self._history) == self._window_size:
            oldest = self._history[0]
            if self._sum_cache is not None:
                self._sum_cache -= oldest
        self._history.append(actual.copy())
        if self._sum_cache is None:
            data = np.array(self._history)
            self._sum_cache = np.sum(data, axis=0)

    def _reset_on_drift(self) -> None:
        """C-9: 漂移时重置历史窗口与均值缓存。"""
        self._history.clear()
        self._sum_cache = None
        self._error_ema = 1.0
        self._drift_resets += 1
        self._drift_detector.reset()

    def get_error(self) -> float:
        """C-9: 返回 EMA 误差。"""
        if self._error_count == 0:
            return 1.0
        return self._error_ema

    def get_drift_stats(self) -> dict:
        """C-9: 获取漂移检测统计。"""
        return {
            **self._drift_detector.get_stats(),
            "drift_resets": self._drift_resets,
        }
