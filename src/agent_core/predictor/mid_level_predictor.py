"""
中层趋势预测器模块。

滑动窗口线性回归预测器，负责分钟级趋势捕捉。
"""

from collections import deque
from typing import Optional

import numpy as np

from agent_core.common.interfaces import IPredictionModel


class TrendLinearPredictor(IPredictionModel):
    """
    趋势线性预测器。
    """

    def __init__(
        self,
        feature_dimensions: int,
        window_size: int,
        forecast_horizon: int,
    ) -> None:
        self._feature_dimensions = feature_dimensions
        self._window_size = window_size
        self._forecast_horizon = forecast_horizon
        self._history: deque = deque(maxlen=window_size)
        self._error_sum = 0.0
        self._error_count = 0
        self._initialized = False
        self._time_axis_cache: Optional[np.ndarray] = None

    def predict(self, state: np.ndarray) -> np.ndarray:
        if len(self._history) < 3:
            return np.asarray(state, dtype=np.float32).copy()
        time_axis = self._get_time_axis()
        data = np.array(self._history)
        return self._predict_all_dims(time_axis, data)

    def _get_time_axis(self) -> np.ndarray:
        n = len(self._history)
        if self._time_axis_cache is not None and len(self._time_axis_cache) == n:
            return self._time_axis_cache
        self._time_axis_cache = np.arange(n)
        return self._time_axis_cache

    def _predict_all_dims(
        self, time_axis: np.ndarray, data: np.ndarray
    ) -> np.ndarray:
        prediction = np.zeros(self._feature_dimensions, dtype=np.float32)
        for dim in range(self._feature_dimensions):
            prediction[dim] = self._predict_dimension(time_axis, data[:, dim])
        return np.clip(prediction, 0.0, 1.0)

    def _predict_dimension(self, time_axis: np.ndarray, values: np.ndarray) -> float:
        time_mean = np.mean(time_axis)
        value_mean = np.mean(values)
        numerator = np.sum(time_axis * values) - len(time_axis) * time_mean * value_mean
        denominator = np.sum(time_axis * time_axis) - len(time_axis) * time_mean * time_mean
        if abs(denominator) < 1e-10:
            slope = 0.0
        else:
            slope = numerator / denominator
        intercept = value_mean - slope * time_mean
        future_time = len(self._history) - 1 + self._forecast_horizon
        return slope * future_time + intercept

    def update(self, state: np.ndarray, actual: np.ndarray) -> None:
        actual_arr = np.asarray(actual, dtype=np.float32)
        self._history.append(actual_arr.copy())
        self._initialized = True
        if len(self._history) >= 3:
            pred = self.predict(actual_arr)
            error = float(np.mean(np.abs(actual_arr - pred)))
            self._error_sum += error
            self._error_count += 1

    def get_error(self) -> float:
        if self._error_count == 0:
            return 1.0
        return self._error_sum / self._error_count
