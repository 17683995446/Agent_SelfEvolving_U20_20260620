"""
混沌工程模块。

随机注入故障以验证系统鲁棒性。

第一性原理：
- 生物免疫系统通过持续暴露于弱病原体保持警惕
- 故障应在受控环境下主动触发，而非等待生产事故
- 注入点必须可观测、可恢复、不影响真实数据
"""

import random
import time
from typing import Any, Callable, Dict, List, Optional

from agent_core.common.logger import get_logger


class ChaosEngine:
    """
    混沌引擎。

    按配置概率随机触发各类故障。
    """

    def __init__(self) -> None:
        self._enabled = False
        self._probability = 0.0
        self._faults: Dict[str, Callable[[], None]] = {}
        self._logger = get_logger()
        self._register_default_faults()

    def _register_default_faults(self) -> None:
        self._faults = {
            "memory_spike": self._fault_memory_spike,
            "cpu_spike": self._fault_cpu_spike,
            "sensor_delay": self._fault_sensor_delay,
            "prediction_error": self._fault_prediction_error,
        }

    def configure(self, enabled: bool, probability: float) -> None:
        """配置混沌参数。"""
        self._enabled = enabled
        self._probability = max(0.0, min(1.0, probability))

    def maybe_inject(self) -> Optional[str]:
        """
        按概率决定是否注入故障。

        Returns:
            注入的故障名称，未注入返回None。
        """
        if not self._enabled:
            return None
        if random.random() >= self._probability:
            return None
        fault_name = random.choice(list(self._faults.keys()))
        self._logger.warning(f"[ChaosEngine] Injecting fault: {fault_name}")
        try:
            self._faults[fault_name]()
        except Exception as exc:
            self._logger.error(f"[ChaosEngine] Fault failed: {exc}")
        return fault_name

    def _fault_memory_spike(self) -> None:
        """临时分配大量内存后释放。"""
        _ = bytearray(1024 * 1024 * 10)

    def _fault_cpu_spike(self) -> None:
        """临时CPU高负载。"""
        deadline = time.time() + 0.05
        while time.time() < deadline:
            pass

    def _fault_sensor_delay(self) -> None:
        """模拟传感器延迟。"""
        time.sleep(0.1)

    def _fault_prediction_error(self) -> None:
        """模拟预测异常，直接抛出。"""
        raise RuntimeError("Chaos: simulated prediction failure")

    def list_faults(self) -> List[str]:
        """列出所有可用故障类型。"""
        return list(self._faults.keys())
