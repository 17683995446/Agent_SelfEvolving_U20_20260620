"""
自适应计算控制器。

根据资源压力动态调整计算强度，实现能耗优化。

第一性原理：
- 生物适应性产热（adaptive thermogenesis）：根据环境温度和能量储备
  调整代谢率，寒冷时增加产热，温暖时降低
- 计算资源是有限的，必须按需分配
- 非关键计算可在资源紧张时降级或跳过

设计要点：
- 功率配置文件：performance/balanced/power_save/emergency
- 自动模式切换：基于CPU/内存压力
- 计算降级策略：跳过频率、集成规模、精度等级
- 线程安全
"""

import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, Optional

from agent_core.common.logger import get_logger

# 资源压力检查间隔（秒）
_PRESSURE_CHECK_INTERVAL = 5.0
# 模式切换滞后（避免频繁切换）
_MODE_HYSTERESIS = 2


class PowerProfile(IntEnum):
    """功率配置文件。"""

    PERFORMANCE = 0  # 全功率
    BALANCED = 1  # 平衡
    POWER_SAVE = 2  # 节能
    EMERGENCY = 3  # 紧急（最低功耗）


# 功率配置参数
_PROFILE_CONFIG: Dict[PowerProfile, Dict[str, Any]] = {
    PowerProfile.PERFORMANCE: {
        "prediction_frequency": 1.0,  # 每次都预测
        "ensemble_size_ratio": 1.0,  # 全部集成
        "perception_resolution": 1.0,  # 全分辨率
        "memory_consolidation_interval": 10.0,
        "skip_non_critical": False,
        "cpu_threshold": 0.0,
        "memory_threshold": 0.0,
    },
    PowerProfile.BALANCED: {
        "prediction_frequency": 0.75,  # 75%频率
        "ensemble_size_ratio": 0.7,
        "perception_resolution": 0.8,
        "memory_consolidation_interval": 20.0,
        "skip_non_critical": False,
        "cpu_threshold": 60.0,
        "memory_threshold": 70.0,
    },
    PowerProfile.POWER_SAVE: {
        "prediction_frequency": 0.5,
        "ensemble_size_ratio": 0.5,
        "perception_resolution": 0.5,
        "memory_consolidation_interval": 60.0,
        "skip_non_critical": True,
        "cpu_threshold": 80.0,
        "memory_threshold": 85.0,
    },
    PowerProfile.EMERGENCY: {
        "prediction_frequency": 0.25,
        "ensemble_size_ratio": 0.3,
        "perception_resolution": 0.3,
        "memory_consolidation_interval": 120.0,
        "skip_non_critical": True,
        "cpu_threshold": 90.0,
        "memory_threshold": 92.0,
    },
}


@dataclass
class ComputeDecision:
    """计算决策结果。"""

    should_compute: bool
    profile: PowerProfile
    frequency_ratio: float
    ensemble_ratio: float
    resolution_ratio: float
    skip_non_critical: bool
    reason: str = ""


class AdaptiveComputeController:
    """
    自适应计算控制器。

    根据资源压力动态调整计算强度。
    """

    def __init__(
        self,
        initial_profile: PowerProfile = PowerProfile.BALANCED,
    ) -> None:
        self._profile = initial_profile
        self._manual_override = False
        self._logger = get_logger()
        self._lock = threading.Lock()
        self._last_check = 0.0
        self._cpu_pressure = 0.0
        self._memory_pressure = 0.0
        self._call_counter = 0
        self._profile_history: list = []

    @property
    def profile(self) -> PowerProfile:
        """当前功率配置。"""
        with self._lock:
            return self._profile

    def set_manual_profile(self, profile: PowerProfile) -> None:
        """手动设置功率配置（覆盖自动切换）。"""
        with self._lock:
            self._profile = profile
            self._manual_override = True
            self._logger.info(
                f"[AdaptiveCompute] Manual profile: {profile.name}"
            )

    def clear_manual_override(self) -> None:
        """清除手动覆盖，恢复自动切换。"""
        with self._lock:
            self._manual_override = False

    def update_pressure(
        self, cpu_percent: float, memory_percent: float
    ) -> PowerProfile:
        """
        更新资源压力并自动调整功率配置。

        Args:
            cpu_percent: CPU使用率（0-100）。
            memory_percent: 内存使用率（0-100）。

        Returns:
            当前功率配置。
        """
        with self._lock:
            self._cpu_pressure = cpu_percent
            self._memory_pressure = memory_percent
            if self._manual_override:
                return self._profile
            new_profile = self._select_profile(
                cpu_percent, memory_percent
            )
            if new_profile != self._profile:
                self._profile_history.append(
                    (time.monotonic(), self._profile, new_profile)
                )
                self._profile = new_profile
                self._logger.info(
                    f"[AdaptiveCompute] Profile changed to {new_profile.name} "
                    f"(cpu={cpu_percent:.0f}%, mem={memory_percent:.0f}%)"
                )
            return self._profile

    def decide(self, is_critical: bool = False) -> ComputeDecision:
        """
        获取计算决策。

        Args:
            is_critical: 是否关键计算（关键计算不被跳过）。

        Returns:
            计算决策。
        """
        with self._lock:
            config = _PROFILE_CONFIG[self._profile]
            self._call_counter += 1

            # 关键计算始终执行
            if is_critical:
                return ComputeDecision(
                    should_compute=True,
                    profile=self._profile,
                    frequency_ratio=1.0,
                    ensemble_ratio=max(
                        config["ensemble_size_ratio"], 0.5
                    ),
                    resolution_ratio=max(
                        config["perception_resolution"], 0.5
                    ),
                    skip_non_critical=False,
                    reason="critical_compute",
                )

            # 非关键计算按频率跳过
            freq = config["prediction_frequency"]
            should = (
                self._call_counter % max(1, int(1.0 / freq)) == 0
                if freq < 1.0
                else True
            )

            return ComputeDecision(
                should_compute=should,
                profile=self._profile,
                frequency_ratio=freq,
                ensemble_ratio=config["ensemble_size_ratio"],
                resolution_ratio=config["perception_resolution"],
                skip_non_critical=config["skip_non_critical"],
                reason="frequency_skip" if not should else "ok",
            )

    def should_skip_non_critical(self) -> bool:
        """是否应跳过非关键计算。"""
        with self._lock:
            return _PROFILE_CONFIG[self._profile]["skip_non_critical"]

    def get_consolidation_interval(self) -> float:
        """获取记忆整合间隔（秒）。"""
        with self._lock:
            return _PROFILE_CONFIG[self._profile][
                "memory_consolidation_interval"
            ]

    def get_ensemble_ratio(self) -> float:
        """获取集成规模比例。"""
        with self._lock:
            return _PROFILE_CONFIG[self._profile]["ensemble_size_ratio"]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息。"""
        with self._lock:
            config = _PROFILE_CONFIG[self._profile]
            return {
                "profile": self._profile.name,
                "manual_override": self._manual_override,
                "cpu_pressure": self._cpu_pressure,
                "memory_pressure": self._memory_pressure,
                "call_count": self._call_counter,
                "config": {
                    k: v for k, v in config.items()
                    if isinstance(v, (int, float, bool))
                },
                "profile_switches": len(self._profile_history),
            }

    def reset(self) -> None:
        """重置控制器。"""
        with self._lock:
            self._profile = PowerProfile.BALANCED
            self._manual_override = False
            self._cpu_pressure = 0.0
            self._memory_pressure = 0.0
            self._call_counter = 0
            self._profile_history.clear()

    def _select_profile(
        self, cpu: float, memory: float
    ) -> PowerProfile:
        """根据资源压力选择功率配置。"""
        max_pressure = max(cpu, memory)
        if max_pressure >= _PROFILE_CONFIG[PowerProfile.EMERGENCY]["cpu_threshold"]:
            return PowerProfile.EMERGENCY
        if max_pressure >= _PROFILE_CONFIG[PowerProfile.POWER_SAVE]["cpu_threshold"]:
            return PowerProfile.POWER_SAVE
        if max_pressure >= _PROFILE_CONFIG[PowerProfile.BALANCED]["cpu_threshold"]:
            return PowerProfile.BALANCED
        return PowerProfile.PERFORMANCE
