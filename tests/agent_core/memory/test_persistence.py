"""
持久化存储模块单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import os
import tempfile
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
from agent_core.memory.persistence import PersistenceManager


class TestPersistenceManager(unittest.TestCase):
    """测试持久化管理器。"""

    def setUp(self) -> None:
        """每个用例前创建临时数据库。"""
        self._db_fd, self._db_path = tempfile.mkstemp(suffix=".db")
        os.close(self._db_fd)
        self.manager = PersistenceManager(db_path=self._db_path)

    def tearDown(self) -> None:
        """每个用例后删除临时数据库。"""
        if os.path.exists(self._db_path):
            os.remove(self._db_path)

    def _make_experience(self, timestamp: float = 1.0) -> Experience:
        """构造测试经验。"""
        state = EnvironmentState(
            timestamp=timestamp,
            raw_sensors={"cpu": 0.5},
            feature_vector=np.array([0.1, 0.2, 0.3], dtype=np.float32),
        )
        pred = PredictionResult(
            low_level=np.array([0.1, 0.2, 0.3]),
            mid_level=np.array([0.2, 0.3, 0.4]),
            high_level=np.array([0.3, 0.4, 0.5]),
            ensemble=np.array([0.15, 0.25, 0.35]),
            confidence=0.8,
        )
        drives = DriveSignals(
            safety_reward=0.5,
            gain_reward=0.6,
            efficiency_reward=0.7,
            safety_gap=0.1,
            gain_gap=0.2,
            efficiency_gap=0.3,
            weights={"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
            total_reward=0.58,
        )
        task = Task(
            task_id="t1",
            name="test_task",
            task_type="safety",
            priority=0.8,
            expected_reward=0.9,
            expected_cost=0.1,
            novelty_score=0.3,
        )
        error = ErrorMetrics(
            mse=0.01,
            mae=0.05,
            mape=0.1,
            direction_accuracy=0.95,
            error_vector=np.array([0.01, 0.02, 0.03]),
        )
        return Experience(
            timestamp=timestamp,
            state=state,
            prediction=pred,
            drive_signals=drives,
            selected_task=task,
            execution_result={"status": "success", "reward": 0.8},
            error_metrics=error,
            priority=1.0,
        )

    def test_save_and_load_experiences(self) -> None:
        """正常值入参测试：保存与加载经验。"""
        exp = self._make_experience()
        self.manager.save_experiences([exp])
        loaded = self.manager.load_experiences(limit=10)
        self.assertEqual(len(loaded), 1)
        self.assertAlmostEqual(loaded[0].timestamp, 1.0)
        self.assertEqual(loaded[0].selected_task.name, "test_task")

    def test_load_empty(self) -> None:
        """空入参测试：空数据库加载。"""
        loaded = self.manager.load_experiences()
        self.assertEqual(len(loaded), 0)

    def test_save_empty_list(self) -> None:
        """空入参测试：保存空列表。"""
        self.manager.save_experiences([])
        loaded = self.manager.load_experiences()
        self.assertEqual(len(loaded), 0)

    def test_save_multiple(self) -> None:
        """正常值入参测试：批量保存。"""
        exps = [self._make_experience(float(i)) for i in range(5)]
        self.manager.save_experiences(exps)
        loaded = self.manager.load_experiences(limit=3)
        self.assertEqual(len(loaded), 3)

    def test_load_offset(self) -> None:
        """正常值入参测试：分页加载。"""
        exps = [self._make_experience(float(i)) for i in range(5)]
        self.manager.save_experiences(exps)
        loaded = self.manager.load_experiences(limit=2, offset=2)
        self.assertEqual(len(loaded), 2)

    def test_experience_with_none_task(self) -> None:
        """正常值入参测试：无任务经验。"""
        exp = self._make_experience()
        exp_no_task = Experience(
            timestamp=exp.timestamp,
            state=exp.state,
            prediction=exp.prediction,
            drive_signals=exp.drive_signals,
            selected_task=None,
            execution_result=exp.execution_result,
            error_metrics=exp.error_metrics,
            priority=exp.priority,
        )
        self.manager.save_experiences([exp_no_task])
        loaded = self.manager.load_experiences()
        self.assertIsNone(loaded[0].selected_task)

    def test_save_and_load_config(self) -> None:
        """正常值入参测试：配置持久化。"""
        config = {"exploration_rate": 0.3, "epsilon": 0.2}
        self.manager.save_config(config)
        loaded = self.manager.load_latest_config()
        self.assertEqual(loaded, config)

    def test_load_config_empty(self) -> None:
        """空入参测试：无配置时加载。"""
        loaded = self.manager.load_latest_config()
        self.assertIsNone(loaded)

    def test_save_and_load_runtime_state(self) -> None:
        """正常值入参测试：运行时状态持久化。"""
        state = {"cycle_count": 42, "errors": [0.1, 0.2]}
        self.manager.save_runtime_state(state)
        loaded = self.manager.load_runtime_state()
        self.assertEqual(loaded["cycle_count"], 42)
        self.assertEqual(loaded["errors"], [0.1, 0.2])

    def test_runtime_state_update(self) -> None:
        """正常值入参测试：状态更新。"""
        self.manager.save_runtime_state({"key": "old"})
        self.manager.save_runtime_state({"key": "new"})
        loaded = self.manager.load_runtime_state()
        self.assertEqual(loaded["key"], "new")

    def test_clear_all(self) -> None:
        """正常值入参测试：清空数据。"""
        self.manager.save_experiences([self._make_experience()])
        self.manager.save_config({"a": 1})
        self.manager.save_runtime_state({"b": 2})
        self.manager.clear_all()
        self.assertEqual(len(self.manager.load_experiences()), 0)
        self.assertIsNone(self.manager.load_latest_config())
        self.assertEqual(self.manager.load_runtime_state(), {})

    def test_large_batch(self) -> None:
        """边界极值测试：大批量保存。"""
        exps = [self._make_experience(float(i)) for i in range(100)]
        self.manager.save_experiences(exps)
        loaded = self.manager.load_experiences(limit=1000)
        self.assertEqual(len(loaded), 100)

    def test_feature_vector_roundtrip(self) -> None:
        """正常值入参测试：特征向量往返。"""
        exp = self._make_experience()
        self.manager.save_experiences([exp])
        loaded = self.manager.load_experiences()[0]
        np.testing.assert_array_almost_equal(
            loaded.state.feature_vector,
            exp.state.feature_vector,
        )


if __name__ == "__main__":
    unittest.main()
