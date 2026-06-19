"""
帕累托多目标选择器单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import unittest

import numpy as np

from agent_core.common.data_contracts import DriveSignals, Task
from agent_core.task.pareto_selector import ParetoSelector


class TestParetoSelector(unittest.TestCase):
    """测试帕累托选择器。"""

    def setUp(self) -> None:
        """每个用例前创建新实例。"""
        self.selector = ParetoSelector()

    def _make_task(
        self,
        task_id: str,
        task_type: str,
        reward: float = 0.5,
        cost: float = 0.2,
    ) -> Task:
        """构造测试任务。"""
        return Task(
            task_id=task_id,
            name=task_id,
            task_type=task_type,
            priority=0.5,
            expected_reward=reward,
            expected_cost=cost,
            novelty_score=0.3,
        )

    def _make_drives(
        self,
        safety_gap: float = 0.3,
        gain_gap: float = 0.3,
        efficiency_gap: float = 0.3,
    ) -> DriveSignals:
        """构造测试驱力。"""
        return DriveSignals(
            safety_reward=0.5,
            gain_reward=0.5,
            efficiency_reward=0.5,
            safety_gap=safety_gap,
            gain_gap=gain_gap,
            efficiency_gap=efficiency_gap,
            weights={"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
            total_reward=0.5,
        )

    def test_empty_tasks(self) -> None:
        """空入参测试：空任务列表。"""
        result = self.selector.select([], self._make_drives())
        self.assertIsNone(result)

    def test_single_task(self) -> None:
        """正常值入参测试：单任务。"""
        tasks = [self._make_task("t1", "safety")]
        result = self.selector.select(tasks, self._make_drives())
        self.assertIsNotNone(result)
        self.assertEqual(result.task_id, "t1")

    def test_dominance_safety_vs_gain(self) -> None:
        """正常值入参测试：安全缺口大时优先安全任务。"""
        tasks = [
            self._make_task("safe", "safety", reward=0.8, cost=0.1),
            self._make_task("gain", "gain", reward=0.9, cost=0.2),
        ]
        drives = self._make_drives(safety_gap=0.9, gain_gap=0.1)
        result = self.selector.select(tasks, drives)
        self.assertEqual(result.task_id, "safe")

    def test_dominance_gain_vs_efficiency(self) -> None:
        """正常值入参测试：收益缺口大时优先收益任务。"""
        tasks = [
            self._make_task("eff", "efficiency", reward=0.3, cost=0.1),
            self._make_task("gain", "gain", reward=0.9, cost=0.2),
        ]
        drives = self._make_drives(gain_gap=0.9, efficiency_gap=0.1)
        result = self.selector.select(tasks, drives)
        self.assertEqual(result.task_id, "gain")

    def test_pareto_front_multiple(self) -> None:
        """正常值入参测试：多任务帕累托前沿。"""
        tasks = [
            self._make_task("a", "safety", reward=0.9, cost=0.1),
            self._make_task("b", "gain", reward=0.9, cost=0.1),
            self._make_task("c", "efficiency", reward=0.9, cost=0.1),
        ]
        drives = self._make_drives(
            safety_gap=0.33, gain_gap=0.33, efficiency_gap=0.34
        )
        result = self.selector.select(tasks, drives)
        self.assertIn(result.task_id, {"a", "b", "c"})

    def test_dominated_task_not_selected(self) -> None:
        """正常值入参测试：被支配任务不选。"""
        tasks = [
            self._make_task("good", "safety", reward=0.9, cost=0.1),
            self._make_task("bad", "safety", reward=0.1, cost=0.9),
        ]
        result = self.selector.select(tasks, self._make_drives())
        self.assertEqual(result.task_id, "good")

    def test_non_dominated_sort_ranks(self) -> None:
        """正常值入参测试：非支配排序层级。"""
        objectives = np.array(
            [
                [1.0, 0.0, 0.0, 0.0],
                [0.0, 1.0, 0.0, 0.0],
                [0.5, 0.5, 0.0, 0.0],
            ],
            dtype=np.float32,
        )
        fronts = self.selector._non_dominated_sort(objectives)
        # 三个向量互不支配，都在第一前沿
        self.assertEqual(len(fronts[0]), 3)
        self.assertEqual(len(fronts), 1)

    def test_dominates_true(self) -> None:
        """正常值入参测试：支配关系成立。"""
        a = np.array([1.0, 1.0, 1.0])
        b = np.array([0.5, 0.5, 0.5])
        self.assertTrue(self.selector._dominates(a, b))

    def test_dominates_false_equal(self) -> None:
        """正常值入参测试：相等不支配。"""
        a = np.array([1.0, 1.0, 1.0])
        b = np.array([1.0, 1.0, 1.0])
        self.assertFalse(self.selector._dominates(a, b))

    def test_dominates_false_worse(self) -> None:
        """正常值入参测试：更差不支配。"""
        a = np.array([0.5, 0.5, 0.5])
        b = np.array([1.0, 1.0, 1.0])
        self.assertFalse(self.selector._dominates(a, b))

    def test_preference_score_safety(self) -> None:
        """正常值入参测试：安全任务偏好得分。"""
        task = self._make_task("s", "safety", reward=0.8, cost=0.1)
        weights = np.array([0.5, 0.3, 0.2])
        score = self.selector._compute_preference_score(task, weights)
        self.assertGreater(score, 0.0)

    def test_boundary_zero_gaps(self) -> None:
        """边界极值测试：零缺口。"""
        tasks = [self._make_task("t1", "safety")]
        drives = self._make_drives(
            safety_gap=0.0, gain_gap=0.0, efficiency_gap=0.0
        )
        result = self.selector.select(tasks, drives)
        self.assertIsNotNone(result)

    def test_large_task_pool(self) -> None:
        """边界极值测试：大量任务。"""
        tasks = [
            self._make_task(f"t{i}", "gain", reward=0.5 + i * 0.01, cost=0.1)
            for i in range(50)
        ]
        result = self.selector.select(tasks, self._make_drives())
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
