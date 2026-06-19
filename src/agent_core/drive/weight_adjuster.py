"""
动态权重调整器模块。

根据场景自适应调整三大驱力权重。
"""

from typing import Dict

from agent_core.common.constants import (
    BASE_EFFICIENCY_WEIGHT_DEFAULT,
    BASE_GAIN_WEIGHT_DEFAULT,
    BASE_SAFETY_WEIGHT_DEFAULT,
)


class DynamicWeightAdjuster:
    """
    动态权重调整器。
    """

    def __init__(self) -> None:
        self._base_weights = {
            "safety": BASE_SAFETY_WEIGHT_DEFAULT,
            "gain": BASE_GAIN_WEIGHT_DEFAULT,
            "efficiency": BASE_EFFICIENCY_WEIGHT_DEFAULT,
        }

    def adjust(
        self, gaps: Dict[str, float], base_weights: Dict[str, float]
    ) -> Dict[str, float]:
        """
        根据缺口动态调整权重。

        Args:
            gaps: 缺口字典。
            base_weights: 基础权重字典。

        Returns:
            调整后的权重字典。
        """
        if base_weights:
            self._base_weights = base_weights.copy()
        safety_gap = gaps.get("safety", 0.0)
        gain_gap = gaps.get("gain", 0.0)
        efficiency_gap = gaps.get("efficiency", 0.0)
        weights = self._select_weights_by_scene(
            safety_gap, gain_gap, efficiency_gap
        )
        return self._normalize_weights(weights)

    def _select_weights_by_scene(
        self, safety_gap: float, gain_gap: float, efficiency_gap: float
    ) -> Dict[str, float]:
        if safety_gap > 0.7:
            return {"safety": 0.7, "gain": 0.2, "efficiency": 0.1}
        if efficiency_gap > 0.7:
            return {"safety": 0.2, "gain": 0.1, "efficiency": 0.7}
        if safety_gap < 0.3 and efficiency_gap < 0.3:
            return {"safety": 0.2, "gain": 0.6, "efficiency": 0.2}
        return self._base_weights.copy()

    def _normalize_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        total = sum(weights.values())
        if total <= 0.0:
            return {"safety": 0.33, "gain": 0.33, "efficiency": 0.34}
        return {key: value / total for key, value in weights.items()}
