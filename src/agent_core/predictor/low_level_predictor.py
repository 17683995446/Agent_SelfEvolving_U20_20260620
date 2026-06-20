"""
底层高频预测器模块。

自适应指数平滑预测器，负责秒级快速适应。

C-9增强：
- 误差衰减：用 EMA 替代全历史平均，反映近期表现
- 概念漂移检测：漂移时重置平滑状态，避免旧数据污染
- 学习率衰减：随样本数增加降低适应速率，避免新样本主导
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
from agent_core.predictor.concept_drift import ConceptDriftDetector

# C-9: 误差 EMA 衰减系数
_ERROR_EMA_ALPHA = 0.3
# C-9: 学习率衰减因子（样本数越多，alpha 调整步长越小）
_LR_DECAY_BASE = 10.0


class AdaptiveExponentialSmoother(IPredictionModel):
    """
    自适应指数平滑预测器。

    C-9增强：误差 EMA、漂移检测、学习率衰减。
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
        self._error_ema: float = 1.0  # C-9: EMA 误差替代全历史平均
        self._error_count = 0
        self._initialized = False
        # C-9: 概念漂移检测器
        self._drift_detector = ConceptDriftDetector()
        self._drift_resets = 0

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
        mean_abs_error = float(np.mean(abs_error))
        # C-9: 误差 EMA 更新（替代全历史平均）
        self._error_ema = (
            (1.0 - _ERROR_EMA_ALPHA) * self._error_ema
            + _ERROR_EMA_ALPHA * mean_abs_error
        )
        self._error_count += 1
        # C-9: 概念漂移检测
        drift_detected = self._drift_detector.update(mean_abs_error)
        if drift_detected:
            self._reset_on_drift(actual)
            return
        # C-9: 学习率衰减（样本越多步长越小）
        lr_scale = _LR_DECAY_BASE / (_LR_DECAY_BASE + self._error_count)
        self._adapt_alpha(abs_error, lr_scale)
        self._blend(actual)

    def _adapt_alpha(self, abs_error: np.ndarray, lr_scale: float) -> None:
        """C-9: 带学习率衰减的 alpha 自适应。"""
        delta = self._adaptation_rate * lr_scale * (abs_error - self._alpha)
        self._alpha = np.clip(
            self._alpha + delta,
            self._alpha_min,
            self._alpha_max,
        )

    def _blend(self, actual: np.ndarray) -> None:
        self._smoothed = (
            self._alpha * actual + (1.0 - self._alpha) * self._smoothed
        )

    def _reset_on_drift(self, actual: np.ndarray) -> None:
        """C-9: 漂移时重置平滑状态，以当前观测为新的起点。"""
        self._smoothed = actual.copy()
        self._error_ema = 1.0  # 重置误差
        self._drift_resets += 1
        # 重置漂移检测器窗口
        self._drift_detector.reset()

    def get_error(self) -> float:
        """C-9: 返回 EMA 误差（反映近期表现）。"""
        if self._error_count == 0:
            return 1.0
        return self._error_ema

    def get_drift_stats(self) -> dict:
        """C-9: 获取漂移检测统计。"""
        return {
            **self._drift_detector.get_stats(),
            "drift_resets": self._drift_resets,
        }
