"""
长时混沌压力测试。

模拟大规模、长时间、高混乱运行，验证稳定性与资源控制。
"""

import asyncio
import random
import unittest
from typing import Any, Dict

import numpy as np

from agent_core.common.data_contracts import DriveSignals, EnvironmentState, Task
from agent_core.memory.agent_main import SelfEvolvingAgent


class RandomFaultPerception:
    """随机故障感知模块。"""

    def __init__(self, fault_rate: float = 0.05) -> None:
        self._fault_rate = fault_rate

    async def perceive(self) -> EnvironmentState:
        if random.random() < self._fault_rate:
            raise RuntimeError("random perception fault")
        return EnvironmentState(
            timestamp=0.0,
            raw_sensors={},
            feature_vector=np.random.rand(10),
        )

    async def health_check(self) -> Dict[str, Any]:
        return {"status": "degraded"}

    async def initialize(self, config: Dict[str, Any]) -> bool:
        return True

    async def shutdown(self) -> None:
        pass

    def get_state_history(self, history_size: int) -> list:
        return []


class RandomFaultExecutor:
    """随机故障执行器。"""

    def __init__(self, fault_rate: float = 0.1) -> None:
        self._fault_rate = fault_rate
        self._current_task: Any = None

    async def execute(self, task: Task) -> Dict[str, Any]:
        self._current_task = task
        if random.random() < self._fault_rate:
            raise RuntimeError("random execution fault")
        return {"status": "completed", "actions": ["ok"], "reward": 0.5}

    async def cancel(self, task: Task) -> None:
        pass


class TestLongRunningChaos(unittest.IsolatedAsyncioTestCase):
    """长时混沌测试。"""

    async def test_thousand_cycles(self) -> None:
        """压力测试：1000周期混合故障运行。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {"epsilon": 0.3},
            "memory": {"memory_capacity": 2000},
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        agent.perception = RandomFaultPerception(fault_rate=0.05)
        agent.task_executor = RandomFaultExecutor(fault_rate=0.1)

        success_count = 0
        error_count = 0
        for _ in range(1000):
            try:
                await agent._run_single_cycle(0.001)
                success_count += 1
            except Exception:
                error_count += 1

        self.assertGreater(success_count, 900)
        self.assertLess(error_count, 100)
        health = await agent.health_check()
        self.assertIn(health["status"], ("healthy", "degraded"))
        await agent.stop()

    async def test_memory_growth_under_load(self) -> None:
        """性能测试：高负载下内存增长可控。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {"memory_capacity": 500},
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        for _ in range(200):
            await agent._execute_cycle_core(0.001)

        self.assertLessEqual(len(agent._recent_errors), 20)
        self.assertLessEqual(len(agent._recent_rewards), 20)
        self.assertLessEqual(len(agent._interrupt_history), 20)
        await agent.stop()

    async def test_adaptive_config_stability(self) -> None:
        """稳定性测试：自适应配置不震荡。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {"epsilon": 0.2},
            "memory": {},
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        for _ in range(100):
            await agent._execute_cycle_core(0.001)
            agent._adapt_config_if_needed()

        epsilon = agent._config_manager.get("epsilon", 0.2)
        self.assertGreaterEqual(epsilon, 0.05)
        self.assertLessEqual(epsilon, 0.5)
        await agent.stop()


if __name__ == "__main__":
    unittest.main()
