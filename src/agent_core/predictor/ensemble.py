"""
集成预测器模块。

多层预测融合，动态加权。
"""

from typing import Dict, Tuple

import numpy as np


class EnsemblePredictor:
    """
    集成预测器。
    """

    def __init__(self, feature_dimensions: int, beta: float) -> None:
        self._feature_dimensions = feature_dimensions
        self._beta = beta
        self._layer_errors: Dict[str, float] = {
            "low": 1.0,
            "mid": 1.0,
            "high": 1.0,
        }

    def combine(
        self,
        low_prediction: np.ndarray,
        mid_prediction: np.ndarray,
        high_prediction: np.ndarray,
    ) -> Tuple[np.ndarray, float]:
        """
        融合三层预测。

        Args:
            low_prediction: 底层预测向量。
            mid_prediction: 中层预测向量。
            high_prediction: 高层预测向量。

        Returns:
            (集成预测向量, 置信度)。
        """
        weights = self._compute_weights()
        total = sum(weights.values())
        # Bug21修复：NaN不可通过 < 1e-10 检查，需显式用isfinite
        if not np.isfinite(total) or total < 1e-10:
            w_low = w_mid = w_high = 1.0 / 3.0
        else:
            w_low = weights["low"] / total
            w_mid = weights["mid"] / total
            w_high = weights["high"] / total
        # Bug21修复：对NaN预测值做清洗，避免NaN透传
        low_safe = np.nan_to_num(low_prediction, nan=0.0, posinf=1.0, neginf=0.0)
        mid_safe = np.nan_to_num(mid_prediction, nan=0.0, posinf=1.0, neginf=0.0)
        high_safe = np.nan_to_num(high_prediction, nan=0.0, posinf=1.0, neginf=0.0)
        ensemble = (
            w_low * low_safe
            + w_mid * mid_safe
            + w_high * high_safe
        )
        confidence = self._compute_confidence(w_low, w_mid, w_high)
        confidence = float(np.nan_to_num(confidence, nan=0.0))
        return np.clip(ensemble, 0.0, 1.0), confidence

    def _compute_weights(self) -> Dict[str, float]:
        weights: Dict[str, float] = {}
        for layer, error in self._layer_errors.items():
            weights[layer] = np.exp(-self._beta * max(error, 0.01))
        return weights

    def _compute_confidence(
        self, w_low: float, w_mid: float, w_high: float
    ) -> float:
        probs = np.array([w_low, w_mid, w_high])
        entropy = -np.sum(probs * np.log(probs + 1e-10))
        max_entropy = np.log(3)
        return float(1.0 - entropy / max_entropy)

    def update_errors(self, errors: Dict[str, float]) -> None:
        """
        更新各层误差。

        Args:
            errors: 误差字典。
        """
        for layer, error in errors.items():
            if layer in self._layer_errors:
                self._layer_errors[layer] = (
                    0.7 * self._layer_errors[layer] + 0.3 * error
                )
