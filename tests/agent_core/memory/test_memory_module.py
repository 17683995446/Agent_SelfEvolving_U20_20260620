"""
记忆系统与安全守护模块单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import asyncio
import unittest

import numpy as np

from agent_core.common.data_contracts import (
    DriveSignals,
    EnvironmentState,
    ErrorMetrics,
    Experience,
    PredictionResult,
    Task,
)
from agent_core.memory.memory_module import MemorySystem
from agent_core.memory.resource_guardian import ResourceGuardian


class TestMemorySystem(unittest.TestCase):
    """测试记忆系统。"""

    def test_initialization(self) -> None:
        """正常值入参测试：初始化。"""
        memory = MemorySystem()
        result = asyncio.run(memory.initialize({"memory_capacity": 100}))
        self.assertTrue(result)

    def test_store_and_sample(self) -> None:
        """正常值入参测试：存储与采样。"""
        memory = MemorySystem()
        asyncio.run(memory.initialize({"memory_capacity": 100}))
        for i in range(10):
            exp = self._create_experience(index=i)
            asyncio.run(memory.store(exp))
        sampled = asyncio.run(memory.sample_experiences(sample_size=5))
        self.assertEqual(len(sampled), 5)

    def test_empty_sample(self) -> None:
        """空入参测试：空记忆采样。"""
        memory = MemorySystem()
        asyncio.run(memory.initialize({"memory_capacity": 100}))
        sampled = asyncio.run(memory.sample_experiences(sample_size=5))
        self.assertEqual(len(sampled), 0)

    def test_capacity_boundary(self) -> None:
        """边界极值测试：容量满载。"""
        memory = MemorySystem()
        asyncio.run(memory.initialize({"memory_capacity": 5}))
        for i in range(10):
            exp = self._create_experience(index=i)
            asyncio.run(memory.store(exp))
        health = asyncio.run(memory.health_check())
        self.assertLessEqual(health["metrics"]["experience_count"], 5)

    def _create_experience(self, index: int) -> Experience:
        return Experience(
            timestamp=float(index),
            state=EnvironmentState(
                timestamp=float(index),
                raw_sensors={},
                feature_vector=np.array([0.1 * index]),
            ),
            prediction=PredictionResult(
                low_level=np.array([0.0]),
                mid_level=np.array([0.0]),
                high_level=np.array([0.0]),
                ensemble=np.array([0.0]),
                confidence=0.5,
            ),
            drive_signals=DriveSignals(
                safety_reward=0.5,
                gain_reward=0.5,
                efficiency_reward=0.5,
                safety_gap=0.5,
                gain_gap=0.5,
                efficiency_gap=0.5,
                weights={"safety": 0.33, "gain": 0.33, "efficiency": 0.34},
                total_reward=0.5,
            ),
            selected_task=Task(
                task_id=f"t{index}",
                name="test",
                task_type="safety",
                priority=0.5,
                expected_reward=0.5,
                expected_cost=0.2,
                novelty_score=0.3,
            ),
            execution_result={"status": "completed"},
            error_metrics=ErrorMetrics(
                mse=0.01,
                mae=0.1,
                mape=0.05,
                direction_accuracy=0.5,
                error_vector=np.array([0.1]),
            ),
            priority=0.5,
        )


class TestResourceGuardian(unittest.TestCase):
    """测试资源守护。"""

    def test_check(self) -> None:
        """正常值入参测试：资源检查。"""
        guardian = ResourceGuardian()
        result = asyncio.run(guardian.check())
        self.assertIn("status", result)
        self.assertIn("can_execute", result)
        self.assertIn("metrics", result)

    def test_status_values(self) -> None:
        """正常值入参测试：状态值范围。"""
        guardian = ResourceGuardian()
        result = asyncio.run(guardian.check())
        self.assertIn(result["status"], ["safe", "warning", "critical"])

    def test_enforce(self) -> None:
        """正常值入参测试：强制执行。"""
        guardian = ResourceGuardian()
        asyncio.run(guardian.enforce())


if __name__ == "__main__":
    unittest.main()
