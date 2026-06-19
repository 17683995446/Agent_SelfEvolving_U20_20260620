"""
状态标准化模块。

将原始传感器数据转换为统一的标准化特征向量。
"""

from typing import Any, Dict

import numpy as np

from agent_core.common.constants import (
    FEATURE_DIMENSIONS_DEFAULT,
    HEALTH_CPU_WEIGHT,
    HEALTH_DISK_WEIGHT,
    HEALTH_ERROR_WEIGHT,
    HEALTH_MEMORY_WEIGHT,
)


class StateNormalizer:
    """
    状态标准化器。

    将原始传感器数据标准化为特征向量，所有特征归一化到[0, 1]范围。
    """

    def __init__(self, feature_dimensions: int) -> None:
        self._feature_dimensions = feature_dimensions

    def normalize(self, sensor_data: Dict[str, Any]) -> np.ndarray:
        """
        将原始传感器数据转换为标准化特征向量。

        Args:
            sensor_data: 原始传感器数据字典。

        Returns:
            标准化后的特征向量。
        """
        features = np.zeros(self._feature_dimensions, dtype=np.float32)
        features[0] = self._extract_cpu_percent(sensor_data)
        features[1] = self._extract_cpu_load(sensor_data)
        features[2] = self._extract_memory_percent(sensor_data)
        features[3] = self._extract_swap_percent(sensor_data)
        features[4] = self._extract_disk_percent(sensor_data)
        features[5] = self._extract_network_error_rate(sensor_data)
        features[6] = self._extract_log_error_rate(sensor_data)
        features[7] = self._extract_log_warning_rate(sensor_data)
        features[8] = self._extract_process_ratio(sensor_data)
        features[9] = self._compute_health_score(features)
        return features

    def _extract_cpu_percent(self, sensor_data: Dict[str, Any]) -> float:
        cpu_data = sensor_data.get("cpu", {})
        percent = cpu_data.get("percent", 0.0)
        return min(percent / 100.0, 1.0)

    def _extract_cpu_load(self, sensor_data: Dict[str, Any]) -> float:
        cpu_data = sensor_data.get("cpu", {})
        load = cpu_data.get("load_avg_1m", 0.0)
        return min(load / 10.0, 1.0)

    def _extract_memory_percent(self, sensor_data: Dict[str, Any]) -> float:
        memory_data = sensor_data.get("memory", {})
        percent = memory_data.get("percent", 0.0)
        return min(percent / 100.0, 1.0)

    def _extract_swap_percent(self, sensor_data: Dict[str, Any]) -> float:
        memory_data = sensor_data.get("memory", {})
        percent = memory_data.get("swap_percent", 0.0)
        return min(percent / 100.0, 1.0)

    def _extract_disk_percent(self, sensor_data: Dict[str, Any]) -> float:
        disk_data = sensor_data.get("disk", {})
        partitions = disk_data.get("partitions", [])
        if not partitions:
            return 0.0
        return min(partitions[0].get("percent", 0.0) / 100.0, 1.0)

    def _extract_network_error_rate(self, sensor_data: Dict[str, Any]) -> float:
        network_data = sensor_data.get("network", {})
        packets_recv = network_data.get("packets_recv", 0)
        if packets_recv <= 0:
            return 0.0
        errors = network_data.get("errin", 0) + network_data.get("errout", 0)
        return min(errors / packets_recv, 1.0)

    def _extract_log_error_rate(self, sensor_data: Dict[str, Any]) -> float:
        log_data = sensor_data.get("log", {})
        count = log_data.get("error_count", 0)
        return min(count / 10.0, 1.0)

    def _extract_log_warning_rate(self, sensor_data: Dict[str, Any]) -> float:
        log_data = sensor_data.get("log", {})
        count = log_data.get("warning_count", 0)
        return min(count / 10.0, 1.0)

    def _extract_process_ratio(self, sensor_data: Dict[str, Any]) -> float:
        process_data = sensor_data.get("process", {})
        count = process_data.get("total_processes", 0)
        return min(count / 500.0, 1.0)

    def _compute_health_score(self, features: np.ndarray) -> float:
        cpu_score = 1.0 - features[0]
        memory_score = 1.0 - features[2]
        disk_score = 1.0 - features[4]
        error_score = 1.0 - features[6]
        return (
            HEALTH_CPU_WEIGHT * cpu_score
            + HEALTH_MEMORY_WEIGHT * memory_score
            + HEALTH_DISK_WEIGHT * disk_score
            + HEALTH_ERROR_WEIGHT * error_score
        )
