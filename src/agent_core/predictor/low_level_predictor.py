"""
底层高频预测器模块。

自适应指数平滑预测器，负责秒级快速适应。
"""

from typing import Optional

import numpy as np

from agent_core.common.interfaces import IPredictionModel
from agent_core.common.constants import (
    LOW_ADAPTATION_RATE_DEFAULT,
    LOW_ALPHA_INIT_DEFAULT,
    LOW_ALPHA_MAX_DEFAULT,
    LOW_ALPHA_MIN_DEFAULT,
)


class AdaptiveExponentialSmoother(IPredictionModel):
    """
    自适应指数平滑预测器。
    """

    def __init__(
        self,
        feature_dimensions: int,
        alpha_init: float,
        alpha_min: float,
        alpha_max: float,
        adaptation_rate: float,
    ) -> None:
        self._feature_dimensions = feature_dimensions
        self._alpha_min = alpha_min
        self._alpha_max = alpha_max
        self._adaptation_rate = adaptation_rate
        self._smoothed: Optional[np.ndarray] = None
        self._alpha = np.full(feature_dimensions, alpha_init, dtype=np.float32)
        self._error_sum = 0.0
        self._error_count = 0
        self._initialized = False

    def predict(self, state: np.ndarray) -> np.ndarray:
        if not self._initialized or self._smoothed is None:
            return state.copy()
        return self._smoothed.copy()

    def update(self, state: np.ndarray, actual: np.ndarray) -> None:
        actual_arr = np.asarray(actual, dtype=np.float32)
        if not self._initialized:
            self._smoothed = actual_arr.copy()
            self._initialized = True
            return
        self._update_smoothed(actual_arr)

    def _update_smoothed(self, actual: np.ndarray) -> None:
        error = actual - self._smoothed
        abs_error = np.abs(error)
        self._adapt_alpha(abs_error)
        self._blend(actual)
        self._error_sum += float(np.mean(abs_error))
        self._error_count += 1

    def _adapt_alpha(self, abs_error: np.ndarray) -> None:
        delta = self._adaptation_rate * (abs_error - self._alpha)
        self._alpha = np.clip(
            self._alpha + delta,
            self._alpha_min,
            self._alpha_max,
        )

    def _blend(self, actual: np.ndarray) -> None:
        self._smoothed = (
            self._alpha * actual + (1.0 - self._alpha) * self._smoothed
        )

    def get_error(self) -> float:
        if self._error_count == 0:
            return 1.0
        return self._error_sum / self._error_count
