"""
驱力引擎模块单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import asyncio
import unittest

import numpy as np

from agent_core.common.data_contracts import DriveSignals, EnvironmentState
from agent_core.drive.drive_calculator import (
    EfficiencyDriveCalculator,
    GainDriveCalculator,
    SafetyDriveCalculator,
)
from agent_core.drive.drive_module import DriveEngine
from agent_core.drive.weight_adjuster import DynamicWeightAdjuster


class TestSafetyDriveCalculator(unittest.TestCase):
    """测试安全驱力计算器。"""

    def test_normal_compute(self) -> None:
        """正常值入参测试。"""
        calculator = SafetyDriveCalculator()
        state = EnvironmentState(
            timestamp=1.0,
            raw_sensors={
                "cpu": {"percent": 50.0, "load_avg_1m": 2.0},
                "memory": {"percent": 60.0, "swap_percent": 10.0},
                "log": {"error_count": 0, "warning_count": 0},
                "process": {"zombie_count": 0},
            },
            feature_vector=np.array([0.5, 0.3, 0.7, 0.2]),
        )
        reward = calculator.compute(state)
        self.assertTrue(0.0 <= reward <= 1.0)

    def test_empty_sensors(self) -> None:
        """空入参测试：缺失传感器数据。"""
        calculator = SafetyDriveCalculator()
        state = EnvironmentState(
            timestamp=1.0,
            raw_sensors={},
            feature_vector=np.array([0.0]),
        )
        reward = calculator.compute(state)
        self.assertTrue(0.0 <= reward <= 1.0)

    def test_boundary_values(self) -> None:
        """边界极值测试：系统满载。"""
        calculator = SafetyDriveCalculator()
        state = EnvironmentState(
            timestamp=1.0,
            raw_sensors={
                "cpu": {"percent": 100.0, "load_avg_1m": 20.0},
                "memory": {"percent": 100.0, "swap_percent": 100.0},
                "log": {"error_count": 100, "warning_count": 100},
                "process": {"zombie_count": 20},
            },
            feature_vector=np.array([1.0, 1.0, 1.0, 1.0]),
        )
        reward = calculator.compute(state)
        self.assertTrue(0.0 <= reward <= 1.0)


class TestGainDriveCalculator(unittest.TestCase):
    """测试收益驱力计算器。"""

    def test_normal_compute(self) -> None:
        """正常值入参测试。"""
        calculator = GainDriveCalculator()
        state = EnvironmentState(
            timestamp=1.0,
            raw_sensors={},
            feature_vector=np.array([0.1, 0.2, 0.3, 0.4]),
        )
        reward = calculator.compute(state)
        self.assertTrue(0.0 <= reward <= 1.0)

    def test_empty_state(self) -> None:
        """空入参测试：空特征向量。"""
        calculator = GainDriveCalculator()
        state = EnvironmentState(
            timestamp=1.0,
            raw_sensors={},
            feature_vector=np.array([]),
        )
        reward = calculator.compute(state)
        self.assertTrue(0.0 <= reward <= 1.0)


class TestEfficiencyDriveCalculator(unittest.TestCase):
    """测试能效驱力计算器。"""

    def test_normal_compute(self) -> None:
        """正常值入参测试。"""
        calculator = EfficiencyDriveCalculator()
        state = EnvironmentState(
            timestamp=1.0,
            raw_sensors={
                "cpu": {"percent": 40.0},
                "memory": {"percent": 40.0},
                "disk": {"partitions": [{"percent": 50.0}]},
            },
            feature_vector=np.array([0.4, 0.4, 0.5]),
        )
        reward = calculator.compute(state)
        self.assertTrue(0.0 <= reward <= 1.0)

    def test_empty_sensors(self) -> None:
        """空入参测试：缺失传感器数据。"""
        calculator = EfficiencyDriveCalculator()
        state = EnvironmentState(
            timestamp=1.0,
            raw_sensors={},
            feature_vector=np.array([0.0]),
        )
        reward = calculator.compute(state)
        self.assertTrue(0.0 <= reward <= 1.0)


class TestDynamicWeightAdjuster(unittest.TestCase):
    """测试动态权重调整器。"""

    def test_normal_adjust(self) -> None:
        """正常值入参测试。"""
        adjuster = DynamicWeightAdjuster()
        gaps = {"safety": 0.3, "gain": 0.3, "efficiency": 0.3}
        weights = adjuster.adjust(gaps, {})
        total = sum(weights.values())
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_empty_gaps(self) -> None:
        """空入参测试：空缺口字典。"""
        adjuster = DynamicWeightAdjuster()
        weights = adjuster.adjust({}, {})
        total = sum(weights.values())
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_boundary_values(self) -> None:
        """边界极值测试：安全缺口最大。"""
        adjuster = DynamicWeightAdjuster()
        gaps = {"safety": 1.0, "gain": 0.0, "efficiency": 0.0}
        weights = adjuster.adjust(gaps, {})
        self.assertGreater(weights["safety"], weights["gain"])


class TestDriveEngine(unittest.TestCase):
    """测试驱力引擎模块。"""

    def test_initialization(self) -> None:
        """正常值入参测试：初始化。"""
        engine = DriveEngine()
        result = asyncio.run(engine.initialize({}))
        self.assertTrue(result)

    def test_compute(self) -> None:
        """正常值入参测试：计算驱力。"""
        engine = DriveEngine()
        asyncio.run(engine.initialize({}))
        state = EnvironmentState(
            timestamp=1.0,
            raw_sensors={
                "cpu": {"percent": 50.0, "load_avg_1m": 2.0},
                "memory": {"percent": 60.0, "swap_percent": 10.0},
                "log": {"error_count": 0, "warning_count": 0},
                "process": {"zombie_count": 0},
                "disk": {"partitions": [{"percent": 50.0}]},
            },
            feature_vector=np.array([0.5, 0.3, 0.7, 0.2]),
        )
        signals = asyncio.run(engine.compute(state))
        self.assertIsInstance(signals, DriveSignals)
        self.assertTrue(0.0 <= signals.total_reward <= 1.0)

    def test_compute_without_init(self) -> None:
        """非法格式测试：未初始化调用计算。"""
        engine = DriveEngine()
        state = EnvironmentState(
            timestamp=1.0,
            raw_sensors={},
            feature_vector=np.array([0.0]),
        )
        with self.assertRaises(Exception):
            asyncio.run(engine.compute(state))


if __name__ == "__main__":
    unittest.main()
