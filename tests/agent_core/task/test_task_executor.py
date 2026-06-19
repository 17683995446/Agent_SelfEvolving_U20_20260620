"""
任务执行器单元测试。

覆盖真实动作执行的四类用例。
"""

import asyncio
import unittest

from agent_core.common.data_contracts import Task
from agent_core.task.task_executor import TaskExecutor


class TestTaskExecutorRealActions(unittest.TestCase):
    """测试真实动作执行。"""

    def setUp(self) -> None:
        """设置测试环境。"""
        self.executor = TaskExecutor()

    def test_safety_cleanup_zombies(self) -> None:
        """正常值入参测试：清理僵尸进程。"""
        task = Task(
            task_id="t1",
            name="safety_task",
            task_type="safety",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
            params={"actions": ["cleanup_zombies"]},
        )
        result = asyncio.run(self.executor.execute(task))
        self.assertEqual(result["status"], "completed")
        self.assertTrue(any("zombie" in a for a in result["actions"]))
        self.assertTrue(0.0 <= result["reward"] <= 1.0)

    def test_safety_check_logs(self) -> None:
        """正常值入参测试：分析日志。"""
        task = Task(
            task_id="t1",
            name="safety_task",
            task_type="safety",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
            params={"actions": ["check_logs"]},
        )
        result = asyncio.run(self.executor.execute(task))
        self.assertEqual(result["status"], "completed")
        self.assertTrue(any("error" in a for a in result["actions"]))

    def test_efficiency_gc(self) -> None:
        """正常值入参测试：垃圾回收。"""
        task = Task(
            task_id="t1",
            name="efficiency_task",
            task_type="efficiency",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
            params={"actions": ["optimize_cache"]},
        )
        result = asyncio.run(self.executor.execute(task))
        self.assertEqual(result["status"], "completed")
        self.assertTrue(any("freed" in a for a in result["actions"]))

    def test_gain_sample_states(self) -> None:
        """正常值入参测试：状态采样。"""
        task = Task(
            task_id="t1",
            name="gain_task",
            task_type="gain",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
            params={"actions": ["explore_state_space"]},
        )
        result = asyncio.run(self.executor.execute(task))
        self.assertEqual(result["status"], "completed")
        self.assertTrue(any("sampled" in a for a in result["actions"]))

    def test_exploration_perturb(self) -> None:
        """正常值入参测试：参数扰动。"""
        task = Task(
            task_id="t1",
            name="explore_task",
            task_type="exploration",
            priority=0.5,
            expected_reward=0.4,
            expected_cost=0.35,
            novelty_score=0.9,
            params={},
        )
        result = asyncio.run(self.executor.execute(task))
        self.assertEqual(result["status"], "completed")
        self.assertIn("perturbation_magnitude", result)

    def test_empty_actions(self) -> None:
        """空入参测试：空动作列表。"""
        task = Task(
            task_id="t1",
            name="safety_task",
            task_type="safety",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
            params={"actions": []},
        )
        result = asyncio.run(self.executor.execute(task))
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["actions"]), 0)

    def test_unknown_task_type(self) -> None:
        """非法格式测试：未知任务类型。"""
        task = Task(
            task_id="t1",
            name="unknown",
            task_type="unknown",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
        )
        result = asyncio.run(self.executor.execute(task))
        self.assertEqual(result["status"], "unknown_task_type")


if __name__ == "__main__":
    unittest.main()
