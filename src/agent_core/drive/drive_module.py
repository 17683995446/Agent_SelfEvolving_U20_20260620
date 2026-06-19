"""
驱力引擎模块主类。

整合三大驱力计算与动态权重调整功能。
"""

from typing import Any, Dict

import numpy as np

from agent_core.common.data_contracts import DriveSignals, EnvironmentState
from agent_core.common.interfaces import IDriveEngine
from agent_core.common.exceptions import ModuleNotInitializedException
from agent_core.common.constants import (
    BASE_EFFICIENCY_WEIGHT_DEFAULT,
    BASE_GAIN_WEIGHT_DEFAULT,
    BASE_SAFETY_WEIGHT_DEFAULT,
)
from agent_core.common.logger import get_logger

from .drive_calculator import (
    EfficiencyDriveCalculator,
    GainDriveCalculator,
    SafetyDriveCalculator,
)
from .weight_adjuster import DynamicWeightAdjuster


class DriveEngine(IDriveEngine):
    """
    驱力引擎实现。
    """

    def __init__(self) -> None:
        self._safety_calc = SafetyDriveCalculator()
        self._gain_calc = GainDriveCalculator()
        self._efficiency_calc = EfficiencyDriveCalculator()
        self._weight_adjuster = DynamicWeightAdjuster()
        self._base_weights = {
            "safety": BASE_SAFETY_WEIGHT_DEFAULT,
            "gain": BASE_GAIN_WEIGHT_DEFAULT,
            "efficiency": BASE_EFFICIENCY_WEIGHT_DEFAULT,
        }
        self._initialized = False
        self._config: Dict[str, Any] = {}
        self._logger = get_logger()

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "DriveEngine"

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """
        初始化驱力引擎。

        Args:
            config: 配置字典。

        Returns:
            初始化成功返回True。
        """
        self._config = config
        if "base_weights" in config:
            self._base_weights = config["base_weights"]
            self._weight_adjuster._base_weights = self._base_weights.copy()
        self._initialized = True
        return True

    async def compute(self, env_state: EnvironmentState) -> DriveSignals:
        """
        计算驱力信号。

        Args:
            env_state: 环境状态对象。

        Returns:
            驱力信号对象。

        Raises:
            ModuleNotInitializedException: 模块未初始化时抛出。
        """
        if not self._initialized:
            raise ModuleNotInitializedException("DriveEngine not initialized")
        safety_reward = self._safety_calc.compute(env_state)
        gain_reward = self._gain_calc.compute(env_state)
        efficiency_reward = self._efficiency_calc.compute(env_state)
        # Bug22修复：NaN兜底，避免DriveSignals.__post_init__校验失败导致周期死循环
        safety_reward = float(np.nan_to_num(safety_reward, nan=0.5))
        gain_reward = float(np.nan_to_num(gain_reward, nan=0.5))
        efficiency_reward = float(np.nan_to_num(efficiency_reward, nan=0.5))
        gaps = {
            "safety": 1.0 - safety_reward,
            "gain": 1.0 - gain_reward,
            "efficiency": 1.0 - efficiency_reward,
        }
        weights = self._weight_adjuster.adjust(gaps, self._base_weights)
        total = (
            weights["safety"] * safety_reward
            + weights["gain"] * gain_reward
            + weights["efficiency"] * efficiency_reward
        )
        total = float(np.nan_to_num(total, nan=0.5))
        self._logger.debug(
            f"[DriveEngine] Computed: safety={safety_reward:.3f}, "
            f"gain={gain_reward:.3f}, efficiency={efficiency_reward:.3f}, "
            f"total={total:.3f}"
        )
        return DriveSignals(
            safety_reward=safety_reward,
            gain_reward=gain_reward,
            efficiency_reward=efficiency_reward,
            safety_gap=gaps["safety"],
            gain_gap=gaps["gain"],
            efficiency_gap=gaps["efficiency"],
            weights=weights,
            total_reward=total,
        )

    def set_base_weights(self, weights: Dict[str, float]) -> None:
        """
        设置基础权重。

        Args:
            weights: 权重字典。
        """
        self._base_weights = weights.copy()
        self._weight_adjuster._base_weights = weights.copy()

    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查。

        Returns:
            健康状态字典。
        """
        status = "healthy" if self._initialized else "unhealthy"
        return {
            "status": status,
            "metrics": {"base_weights": self._base_weights},
        }

    async def shutdown(self) -> None:
        """
        优雅关闭。
        """
        self._initialized = False
