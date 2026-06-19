"""
环境感知模块主类。

整合多传感器数据采集与状态标准化功能。
"""

import asyncio
import time
from collections import deque
from typing import Any, Dict, List

from agent_core.common.data_contracts import EnvironmentState
from agent_core.common.interfaces import IEnvironmentPerception
from agent_core.common.exceptions import ModuleNotInitializedException
from agent_core.common.constants import (
    CPU_INTERVAL_SECONDS_DEFAULT,
    DISK_PATHS_DEFAULT,
    FEATURE_DIMENSIONS_DEFAULT,
    MAX_LOG_LINES_DEFAULT,
)
from agent_core.common.logger import get_logger

from .sensor import (
    CPUSensor,
    DiskSensor,
    ISensor,
    LogSensor,
    MemorySensor,
    NetworkSensor,
    ProcessSensor,
)
from .state_normalizer import StateNormalizer
from .robust_filter import AdversarialDefender, RobustFilter


class EnvironmentPerception(IEnvironmentPerception):
    """
    环境感知模块实现。

    多通道独立采集，统一标准化编码，支持动态注册新传感器。
    """

    def __init__(self) -> None:
        self._sensors: List[ISensor] = []
        self._normalizer = StateNormalizer(FEATURE_DIMENSIONS_DEFAULT)
        self._state_history: deque = deque(maxlen=1000)
        self._config: Dict[str, Any] = {}
        self._initialized = False
        self._logger = get_logger()
        self._robust_filter = RobustFilter()
        self._adversarial_defender = AdversarialDefender()

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "EnvironmentPerception"

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """
        初始化传感器。

        Args:
            config: 配置字典。

        Returns:
            初始化成功返回True。
        """
        self._config = config
        self._register_default_sensors(config)
        self._initialized = True
        self._logger.info("[EnvironmentPerception] Initialized")
        return True

    def _register_default_sensors(self, config: Dict[str, Any]) -> None:
        cpu_interval = config.get("cpu_interval_seconds", CPU_INTERVAL_SECONDS_DEFAULT)
        disk_paths = config.get("disk_paths", DISK_PATHS_DEFAULT)
        log_paths = config.get("log_paths", [])
        max_lines = config.get("max_log_lines", MAX_LOG_LINES_DEFAULT)
        self._sensors = [
            CPUSensor(interval_seconds=cpu_interval),
            MemorySensor(),
            DiskSensor(paths=disk_paths),
            NetworkSensor(),
            LogSensor(log_paths=log_paths, max_lines=max_lines),
            ProcessSensor(),
        ]

    async def perceive(self) -> EnvironmentState:
        """
        执行环境感知。

        Returns:
            环境状态对象。

        Raises:
            ModuleNotInitializedException: 模块未初始化时抛出。
        """
        if not self._initialized:
            raise ModuleNotInitializedException("EnvironmentPerception not initialized")
        self._logger.debug("[EnvironmentPerception] Starting perceive")
        raw_sensors = await self._read_all_sensors()
        feature_vector = self._normalizer.normalize(raw_sensors)
        feature_vector = self._robust_filter.filter(feature_vector)
        feature_vector = self._adversarial_defender.defend(feature_vector)
        state = self._create_state(raw_sensors, feature_vector)
        self._state_history.append(state)
        self._logger.info(
            f"[EnvironmentPerception] Perceived state: "
            f"cpu={raw_sensors.get('cpu', {}).get('percent', 'N/A')}%, "
            f"memory={raw_sensors.get('memory', {}).get('percent', 'N/A')}%, "
            f"features={feature_vector[:3]}..."
        )
        return state

    async def _read_all_sensors(self) -> Dict[str, Any]:
        tasks = [sensor.read() for sensor in self._sensors]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        raw_sensors: Dict[str, Any] = {}
        for index, sensor in enumerate(self._sensors):
            result = results[index]
            if isinstance(result, Exception):
                raw_sensors[sensor.sensor_type] = {"error": str(result)}
                self._logger.warning(
                    f"[EnvironmentPerception] Sensor {sensor.sensor_type} failed: {result}"
                )
            else:
                raw_sensors[sensor.sensor_type] = result
        return raw_sensors

    def _create_state(
        self, raw_sensors: Dict[str, Any], feature_vector: Any
    ) -> EnvironmentState:
        return EnvironmentState(
            timestamp=time.time(),
            raw_sensors=raw_sensors,
            feature_vector=feature_vector,
        )

    def get_state_history(self, history_size: int) -> List[EnvironmentState]:
        """
        获取最近history_size条状态记录。

        Args:
            history_size: 历史记录数量。

        Returns:
            环境状态对象列表。
        """
        return list(self._state_history)[-history_size:]

    def register_sensor(self, sensor: ISensor) -> None:
        """
        动态注册新传感器。

        Args:
            sensor: 传感器对象。
        """
        self._sensors.append(sensor)

    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查。

        Returns:
            健康状态字典。
        """
        status = "healthy" if self._initialized else "unhealthy"
        return {
            "status": status,
            "metrics": {
                "sensor_count": len(self._sensors),
                "history_size": len(self._state_history),
            },
        }

    async def shutdown(self) -> None:
        """
        优雅关闭，释放资源。
        """
        self._sensors.clear()
        self._state_history.clear()
        self._initialized = False
        self._logger.info("[EnvironmentPerception] Shutdown")
