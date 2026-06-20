"""
集成预测器模块。

多层预测融合，动态加权。

C-9增强：
- 动态 softmax 权重（带温度参数），替代纯 exp(-beta*error)
- 预测置信区间估计（基于各层预测的离散度）
- 误差 EMA 衰减保留（已有），新增近期误差窗口用于置信区间
"""

from collections import deque
from typing import Deque, Dict, List, Tuple

import numpy as np

# softmax 温度参数（越小权重越尖锐，越大越均匀）
_SOFTMAX_TEMPERATURE = 0.3
# 置信区间近期样本数
_CONFIDENCE_WINDOW = 20


class EnsemblePredictor:
    """
    集成预测器。

    C-9增强：
    - 动态 softmax 权重（温度参数控制尖锐度）
    - 预测置信区间估计（基于层间离散度）
    """

    def __init__(self, feature_dimensions: int, beta: float) -> None:
        self._feature_dimensions = feature_dimensions
        self._beta = beta
        self._layer_errors: Dict[str, float] = {
            "low": 1.0,
            "mid": 1.0,
            "high": 1.0,
        }
        # C-9: 近期集成预测离散度窗口（用于置信区间）
        self._disparity_history: Deque[float] = deque(
            maxlen=_CONFIDENCE_WINDOW
        )
        # C-9: 近期各层预测缓存（用于置信区间计算）
        self._last_predictions: Dict[str, np.ndarray] = {}

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
        # C-9: 缓存预测用于置信区间
        self._last_predictions = {
            "low": low_safe,
            "mid": mid_safe,
            "high": high_safe,
        }
        # C-9: 记录层间离散度
        disparity = self._compute_disparity(low_safe, mid_safe, high_safe)
        self._disparity_history.append(disparity)
        confidence = self._compute_confidence(w_low, w_mid, w_high)
        confidence = float(np.nan_to_num(confidence, nan=0.0))
        return np.clip(ensemble, 0.0, 1.0), confidence

    def _compute_weights(self) -> Dict[str, float]:
        """C-9: 动态 softmax 权重（带温度参数）。"""
        # 原始分数：误差越低分数越高
        raw_scores = np.array([
            -self._beta * max(self._layer_errors["low"], 0.01),
            -self._beta * max(self._layer_errors["mid"], 0.01),
            -self._beta * max(self._layer_errors["high"], 0.01),
        ])
        # softmax with temperature
        scaled = raw_scores / max(_SOFTMAX_TEMPERATURE, 1e-6)
        scaled = scaled - np.max(scaled)  # 数值稳定
        exp_scores = np.exp(scaled)
        softmax_weights = exp_scores / (np.sum(exp_scores) + 1e-10)
        return {
            "low": float(softmax_weights[0]),
            "mid": float(softmax_weights[1]),
            "high": float(softmax_weights[2]),
        }

    def _compute_disparity(
        self,
        low: np.ndarray,
        mid: np.ndarray,
        high: np.ndarray,
    ) -> float:
        """C-9: 计算层间预测离散度（标准差均值）。"""
        stacked = np.stack([low, mid, high])
        disparity = float(np.mean(np.std(stacked, axis=0)))
        return float(np.nan_to_num(disparity, nan=0.0))

    def _compute_confidence(
        self, w_low: float, w_mid: float, w_high: float
    ) -> float:
        """C-9: 置信度 = 权重熵置信度 × (1 - 离散度)。"""
        probs = np.array([w_low, w_mid, w_high])
        entropy = -np.sum(probs * np.log(probs + 1e-10))
        max_entropy = np.log(3)
        entropy_confidence = float(1.0 - entropy / max_entropy)
        # 离散度惩罚：层间预测越分散，置信度越低
        avg_disparity = (
            float(np.mean(list(self._disparity_history)))
            if self._disparity_history
            else 0.0
        )
        disparity_penalty = min(avg_disparity, 1.0)
        return float(entropy_confidence * (1.0 - disparity_penalty))

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

    # C-9: 置信区间估计
    def get_confidence_interval(self) -> Tuple[float, float]:
        """
        估计预测置信区间（基于近期离散度）。

        Returns:
            (lower_bound, upper_bound) 离散度范围。
        """
        if not self._disparity_history:
            return 0.0, 0.0
        disparities = list(self._disparity_history)
        mean_disp = float(np.mean(disparities))
        std_disp = float(np.std(disparities))
        return max(0.0, mean_disp - std_disp), mean_disp + std_disp

    def get_layer_weights(self) -> Dict[str, float]:
        """C-9: 获取当前各层归一化权重。"""
        weights = self._compute_weights()
        total = sum(weights.values())
        if not np.isfinite(total) or total < 1e-10:
            return {"low": 1 / 3, "mid": 1 / 3, "high": 1 / 3}
        return {k: v / total for k, v in weights.items()}
