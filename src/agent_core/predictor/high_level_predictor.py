"""
高层抽象预测器模块。

均值回归预测器，负责小时级稳态回归。
"""

from collections import deque

import numpy as np

from agent_core.common.interfaces import IPredictionModel


class MeanReversionPredictor(IPredictionModel):
    """
    均值回归预测器。
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
        self._error_sum = 0.0
        self._error_count = 0
        self._initialized = False
        self._sum_cache: Optional[np.ndarray] = None

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
            self._error_sum += error
            self._error_count += 1

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

    def get_error(self) -> float:
        if self._error_count == 0:
            return 1.0
        return self._error_sum / self._error_count
