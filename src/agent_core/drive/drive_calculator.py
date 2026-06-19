"""
驱力计算器模块。

三大驱力独立计算，互不影响。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

import numpy as np

from agent_core.common.data_contracts import EnvironmentState


class IDriveCalculator(ABC):
    """
    驱力计算器接口。
    """

    @abstractmethod
    def compute(self, env_state: EnvironmentState) -> float:
        """
        计算驱力奖励值。

        Args:
            env_state: 环境状态对象。

        Returns:
            奖励值，范围为[0, 1]。
        """
        raise NotImplementedError


class SafetyDriveCalculator(IDriveCalculator):
    """
    安全驱力计算器。
    """

    def compute(self, env_state: EnvironmentState) -> float:
        sensors = env_state.raw_sensors
        cpu_score = self._compute_cpu_score(sensors)
        mem_score = self._compute_memory_score(sensors)
        log_score = self._compute_log_score(sensors)
        proc_score = self._compute_process_score(sensors)
        safety = (cpu_score + mem_score + log_score + proc_score) / 4.0
        return float(np.clip(safety, 0.0, 1.0))

    def _compute_cpu_score(self, sensors: Dict[str, Any]) -> float:
        data = sensors.get("cpu", {})
        percent = data.get("percent", 0.0)
        load = data.get("load_avg_1m", 0.0)
        score_a = max(0.0, 1.0 - percent / 100.0)
        score_b = max(0.0, 1.0 - load / 10.0)
        return score_a * 0.6 + score_b * 0.4

    def _compute_memory_score(self, sensors: Dict[str, Any]) -> float:
        data = sensors.get("memory", {})
        percent = data.get("percent", 0.0)
        swap = data.get("swap_percent", 0.0)
        score_a = max(0.0, 1.0 - percent / 100.0)
        score_b = max(0.0, 1.0 - swap / 100.0)
        return score_a * 0.7 + score_b * 0.3

    def _compute_log_score(self, sensors: Dict[str, Any]) -> float:
        data = sensors.get("log", {})
        errors = data.get("error_count", 0)
        warnings = data.get("warning_count", 0)
        return max(0.0, 1.0 - (errors + warnings * 0.5) / 20.0)

    def _compute_process_score(self, sensors: Dict[str, Any]) -> float:
        data = sensors.get("process", {})
        zombies = data.get("zombie_count", 0)
        return max(0.0, 1.0 - zombies / 10.0)


class GainDriveCalculator(IDriveCalculator):
    """
    收益驱力计算器。
    """

    def __init__(self) -> None:
        self._state_coverage: set = set()
        self._novelty_history: list = []

    def compute(self, env_state: EnvironmentState) -> float:
        vector = env_state.feature_vector
        # Bug22修复：NaN/空向量清洗，避免NaN透传到DriveSignals校验
        if vector is None or len(vector) == 0:
            return 0.5
        vector = np.nan_to_num(vector, nan=0.0, posinf=1.0, neginf=0.0)
        state_hash = self._discretize_state(vector)
        is_new = state_hash not in self._state_coverage
        if is_new:
            self._state_coverage.add(state_hash)
        coverage = min(len(self._state_coverage) / 1000.0, 1.0)
        change = self._compute_change_rate(vector)
        gain = coverage * 0.6 + min(change, 1.0) * 0.4
        return float(np.clip(gain, 0.0, 1.0))

    def _discretize_state(self, vector: np.ndarray, bins: int = 5) -> str:
        discretized = np.digitize(vector, np.linspace(0, 1, bins))
        return "_".join(map(str, discretized))

    def _compute_change_rate(self, vector: np.ndarray) -> float:
        if not self._novelty_history:
            self._novelty_history.append(vector.copy())
            return 0.5
        last = self._novelty_history[-1]
        rate = float(np.mean(np.abs(vector - last)))
        self._novelty_history.append(vector.copy())
        if len(self._novelty_history) > 100:
            self._novelty_history.pop(0)
        return rate


class EfficiencyDriveCalculator(IDriveCalculator):
    """
    能效驱力计算器。
    """

    def compute(self, env_state: EnvironmentState) -> float:
        sensors = env_state.raw_sensors
        cpu_eff = self._compute_cpu_efficiency(sensors)
        mem_eff = self._compute_memory_efficiency(sensors)
        disk_eff = self._compute_disk_efficiency(sensors)
        efficiency = (cpu_eff + mem_eff + disk_eff) / 3.0
        return float(np.clip(efficiency, 0.0, 1.0))

    def _compute_cpu_efficiency(self, sensors: Dict[str, Any]) -> float:
        data = sensors.get("cpu", {})
        percent = data.get("percent", 0.0)
        return max(0.0, 1.0 - abs(percent - 40.0) / 60.0)

    def _compute_memory_efficiency(self, sensors: Dict[str, Any]) -> float:
        data = sensors.get("memory", {})
        percent = data.get("percent", 0.0)
        return max(0.0, 1.0 - abs(percent - 40.0) / 60.0)

    def _compute_disk_efficiency(self, sensors: Dict[str, Any]) -> float:
        data = sensors.get("disk", {})
        partitions = data.get("partitions", [])
        if not partitions:
            return 0.5
        percent = partitions[0].get("percent", 0.0)
        return max(0.0, 1.0 - abs(percent - 50.0) / 50.0)
