"""
误差评估器模块。

多维度评估预测与实际的对齐程度。
"""

import numpy as np

from agent_core.common.data_contracts import ErrorMetrics
from agent_core.common.interfaces import IErrorEvaluator


class PredictionErrorEvaluator(IErrorEvaluator):
    """
    预测误差评估器。
    """

    def __init__(self, feature_dimensions: int) -> None:
        self._feature_dimensions = feature_dimensions

    def evaluate(
        self, prediction: np.ndarray, actual: np.ndarray
    ) -> ErrorMetrics:
        """
        评估预测误差。

        Args:
            prediction: 预测向量。
            actual: 实际向量。

        Returns:
            误差指标对象。
        """
        pred_arr = np.asarray(prediction, dtype=np.float32)
        actual_arr = np.asarray(actual, dtype=np.float32)
        # Bug22修复：NaN/inf清洗，避免NaN透传到task_generator和memory
        pred_arr = np.nan_to_num(pred_arr, nan=0.0, posinf=1.0, neginf=0.0)
        actual_arr = np.nan_to_num(actual_arr, nan=0.0, posinf=1.0, neginf=0.0)
        error_vector = actual_arr - pred_arr
        mse = float(np.mean(error_vector ** 2))
        mae = float(np.mean(np.abs(error_vector)))
        mape = self._compute_mape(error_vector, actual_arr)
        # 兜底：若结果仍为NaN（如空数组），使用安全默认值
        if not np.isfinite(mse):
            mse = 0.0
        if not np.isfinite(mae):
            mae = 0.0
        if not np.isfinite(mape):
            mape = 0.0
        return ErrorMetrics(
            mse=mse,
            mae=mae,
            mape=mape,
            direction_accuracy=0.5,
            error_vector=error_vector,
        )

    def _compute_mape(
        self, error_vector: np.ndarray, actual: np.ndarray
    ) -> float:
        eps = 1e-10
        return float(np.mean(np.abs(error_vector) / (actual + eps)))
