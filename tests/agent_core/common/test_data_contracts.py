"""
数据契约单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import unittest

import numpy as np

from agent_core.common.data_contracts import (
    DriveSignals,
    EnvironmentState,
    ErrorMetrics,
    PredictionResult,
    Task,
)


class TestEnvironmentState(unittest.TestCase):
    """测试环境状态数据契约。"""

    def test_normal_creation(self) -> None:
        """正常值入参测试。"""
        vector = np.array([0.1, 0.2, 0.3])
        state = EnvironmentState(
            timestamp=1.0,
            raw_sensors={"cpu": {"percent": 50}},
            feature_vector=vector,
        )
        self.assertEqual(state.timestamp, 1.0)
        self.assertEqual(len(state.feature_vector), 3)

    def test_empty_sensors(self) -> None:
        """空入参测试。"""
        vector = np.array([0.0])
        state = EnvironmentState(
            timestamp=0.0,
            raw_sensors={},
            feature_vector=vector,
        )
        self.assertEqual(state.raw_sensors, {})

    def test_boundary_values(self) -> None:
        """边界极值测试。"""
        vector = np.array([0.0, 1.0])
        state = EnvironmentState(
            timestamp=9999999999.0,
            raw_sensors={"memory": {"percent": 100}},
            feature_vector=vector,
        )
        self.assertEqual(state.raw_sensors["memory"]["percent"], 100)

    def test_invalid_format(self) -> None:
        """非法格式测试：特征向量传入字符串应转换失败或异常。"""
        with self.assertRaises((ValueError, TypeError)):
            EnvironmentState(
                timestamp=1.0,
                raw_sensors={},
                feature_vector="invalid",  # type: ignore[arg-type]
            )


class TestDriveSignals(unittest.TestCase):
    """测试驱力信号数据契约。"""

    def test_normal_creation(self) -> None:
        """正常值入参测试。"""
        signals = DriveSignals(
            safety_reward=0.5,
            gain_reward=0.6,
            efficiency_reward=0.7,
            safety_gap=0.5,
            gain_gap=0.4,
            efficiency_gap=0.3,
            weights={"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
            total_reward=0.6,
        )
        self.assertEqual(signals.safety_reward, 0.5)

    def test_empty_weights(self) -> None:
        """空入参测试：权重为空字典。"""
        with self.assertRaises(ValueError):
            DriveSignals(
                safety_reward=0.5,
                gain_reward=0.6,
                efficiency_reward=0.7,
                safety_gap=0.5,
                gain_gap=0.4,
                efficiency_gap=0.3,
                weights={},
                total_reward=0.6,
            )

    def test_boundary_values(self) -> None:
        """边界极值测试：奖励值取0和1。"""
        signals = DriveSignals(
            safety_reward=0.0,
            gain_reward=1.0,
            efficiency_reward=0.0,
            safety_gap=1.0,
            gain_gap=0.0,
            efficiency_gap=0.0,
            weights={"safety": 0.5, "gain": 0.3, "efficiency": 0.2},
            total_reward=0.3,
        )
        self.assertEqual(signals.gain_reward, 1.0)

    def test_invalid_format(self) -> None:
        """非法格式测试：奖励值超出[0,1]范围。"""
        with self.assertRaises(ValueError):
            DriveSignals(
                safety_reward=1.5,
                gain_reward=0.6,
                efficiency_reward=0.7,
                safety_gap=0.5,
                gain_gap=0.4,
                efficiency_gap=0.3,
                weights={"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
                total_reward=0.6,
            )

    def test_invalid_weights_sum(self) -> None:
        """非法格式测试：权重和不等于1.0。"""
        with self.assertRaises(ValueError):
            DriveSignals(
                safety_reward=0.5,
                gain_reward=0.6,
                efficiency_reward=0.7,
                safety_gap=0.5,
                gain_gap=0.4,
                efficiency_gap=0.3,
                weights={"safety": 0.5, "gain": 0.5, "efficiency": 0.5},
                total_reward=0.6,
            )


class TestPredictionResult(unittest.TestCase):
    """测试预测结果数据契约。"""

    def test_normal_creation(self) -> None:
        """正常值入参测试。"""
        result = PredictionResult(
            low_level=np.array([0.1, 0.2]),
            mid_level=np.array([0.15, 0.25]),
            high_level=np.array([0.12, 0.22]),
            ensemble=np.array([0.13, 0.23]),
            confidence=0.8,
        )
        self.assertEqual(result.confidence, 0.8)

    def test_empty_arrays(self) -> None:
        """空入参测试：空数组。"""
        result = PredictionResult(
            low_level=np.array([]),
            mid_level=np.array([]),
            high_level=np.array([]),
            ensemble=np.array([]),
            confidence=0.0,
        )
        self.assertEqual(len(result.ensemble), 0)

    def test_boundary_values(self) -> None:
        """边界极值测试：置信度为1.0。"""
        result = PredictionResult(
            low_level=np.array([1.0]),
            mid_level=np.array([1.0]),
            high_level=np.array([1.0]),
            ensemble=np.array([1.0]),
            confidence=1.0,
        )
        self.assertEqual(result.confidence, 1.0)


class TestErrorMetrics(unittest.TestCase):
    """测试误差指标数据契约。"""

    def test_normal_creation(self) -> None:
        """正常值入参测试。"""
        metrics = ErrorMetrics(
            mse=0.01,
            mae=0.1,
            mape=0.05,
            direction_accuracy=0.7,
            error_vector=np.array([0.1, -0.1]),
        )
        self.assertEqual(metrics.mse, 0.01)

    def test_zero_errors(self) -> None:
        """边界极值测试：全零误差。"""
        metrics = ErrorMetrics(
            mse=0.0,
            mae=0.0,
            mape=0.0,
            direction_accuracy=1.0,
            error_vector=np.array([0.0, 0.0]),
        )
        self.assertEqual(metrics.mae, 0.0)


class TestTask(unittest.TestCase):
    """测试任务数据契约。"""

    def test_normal_creation(self) -> None:
        """正常值入参测试。"""
        task = Task(
            task_id="t1",
            name="test_task",
            task_type="safety",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
        )
        self.assertEqual(task.task_id, "t1")

    def test_compute_score_normal(self) -> None:
        """正常值入参测试：计算得分。"""
        task = Task(
            task_id="t1",
            name="test",
            task_type="safety",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
        )
        score = task.compute_score({"reward": 0.4, "cost": 0.4, "novelty": 0.2})
        expected = 0.4 * 0.8 + 0.2 * 0.3 - 0.4 * 0.2
        self.assertAlmostEqual(score, expected, places=5)

    def test_compute_score_empty_weights(self) -> None:
        """空入参测试：空权重字典。"""
        task = Task(
            task_id="t1",
            name="test",
            task_type="safety",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
        )
        with self.assertRaises(ValueError):
            task.compute_score({})

    def test_compute_score_boundary(self) -> None:
        """边界极值测试：最大奖励零成本。"""
        task = Task(
            task_id="t1",
            name="test",
            task_type="safety",
            priority=1.0,
            expected_reward=1.0,
            expected_cost=0.0,
            novelty_score=1.0,
        )
        score = task.compute_score({"reward": 1.0, "cost": 0.0, "novelty": 0.0})
        self.assertAlmostEqual(score, 1.0, places=5)

    def test_compute_score_invalid_format(self) -> None:
        """非法格式测试：权重字典缺少键。"""
        task = Task(
            task_id="t1",
            name="test",
            task_type="safety",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
        )
        with self.assertRaises(ValueError):
            task.compute_score({"reward": 0.5})


if __name__ == "__main__":
    unittest.main()
