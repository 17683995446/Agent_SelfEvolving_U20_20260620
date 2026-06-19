"""
任务生成与决策模块单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import asyncio
import unittest

import numpy as np

from agent_core.common.data_contracts import DriveSignals, ErrorMetrics, Task
from agent_core.task.decision_engine import DecisionEngine
from agent_core.task.task_executor import TaskExecutor
from agent_core.task.task_generator import TaskGenerator


class TestTaskGenerator(unittest.TestCase):
    """测试任务生成器。"""

    def test_normal_generate(self) -> None:
        """正常值入参测试。"""
        generator = TaskGenerator()
        asyncio.run(generator.initialize({"exploration_rate": 0.3}))
        drives = DriveSignals(
            safety_reward=0.3,
            gain_reward=0.7,
            efficiency_reward=0.5,
            safety_gap=0.7,
            gain_gap=0.3,
            efficiency_gap=0.5,
            weights={"safety": 0.5, "gain": 0.3, "efficiency": 0.2},
            total_reward=0.5,
        )
        errors = ErrorMetrics(
            mse=0.1,
            mae=0.4,
            mape=0.2,
            direction_accuracy=0.6,
            error_vector=np.array([0.1, 0.2, 0.3, 0.4]),
        )
        tasks = generator.generate(drives, errors)
        self.assertIsInstance(tasks, list)
        self.assertGreater(len(tasks), 0)

    def test_empty_drives(self) -> None:
        """空入参测试：驱力全满无缺口。"""
        generator = TaskGenerator()
        asyncio.run(generator.initialize({"exploration_rate": 0.0}))
        drives = DriveSignals(
            safety_reward=1.0,
            gain_reward=1.0,
            efficiency_reward=1.0,
            safety_gap=0.0,
            gain_gap=0.0,
            efficiency_gap=0.0,
            weights={"safety": 0.33, "gain": 0.33, "efficiency": 0.34},
            total_reward=1.0,
        )
        errors = ErrorMetrics(
            mse=0.0,
            mae=0.0,
            mape=0.0,
            direction_accuracy=1.0,
            error_vector=np.array([0.0]),
        )
        tasks = generator.generate(drives, errors)
        self.assertIsInstance(tasks, list)

    def test_boundary_values(self) -> None:
        """边界极值测试：最大缺口。"""
        generator = TaskGenerator()
        asyncio.run(generator.initialize({"exploration_rate": 0.0}))
        drives = DriveSignals(
            safety_reward=0.0,
            gain_reward=0.0,
            efficiency_reward=0.0,
            safety_gap=1.0,
            gain_gap=1.0,
            efficiency_gap=1.0,
            weights={"safety": 0.33, "gain": 0.33, "efficiency": 0.34},
            total_reward=0.0,
        )
        errors = ErrorMetrics(
            mse=1.0,
            mae=1.0,
            mape=1.0,
            direction_accuracy=0.0,
            error_vector=np.array([1.0]),
        )
        tasks = generator.generate(drives, errors)
        self.assertGreater(len(tasks), 0)

    def test_generate_without_init(self) -> None:
        """非法格式测试：未初始化调用生成。"""
        generator = TaskGenerator()
        drives = DriveSignals(
            safety_reward=0.5,
            gain_reward=0.5,
            efficiency_reward=0.5,
            safety_gap=0.5,
            gain_gap=0.5,
            efficiency_gap=0.5,
            weights={"safety": 0.33, "gain": 0.33, "efficiency": 0.34},
            total_reward=0.5,
        )
        errors = ErrorMetrics(
            mse=0.1,
            mae=0.1,
            mape=0.1,
            direction_accuracy=0.5,
            error_vector=np.array([0.1]),
        )
        with self.assertRaises(Exception):
            generator.generate(drives, errors)


class TestDecisionEngine(unittest.TestCase):
    """测试决策引擎。"""

    def test_normal_select(self) -> None:
        """正常值入参测试。"""
        engine = DecisionEngine()
        asyncio.run(engine.initialize({"epsilon": 0.0}))
        tasks = [
            Task(
                task_id="t1",
                name="task1",
                task_type="safety",
                priority=0.5,
                expected_reward=0.8,
                expected_cost=0.2,
                novelty_score=0.3,
            ),
            Task(
                task_id="t2",
                name="task2",
                task_type="gain",
                priority=0.3,
                expected_reward=0.6,
                expected_cost=0.3,
                novelty_score=0.5,
            ),
        ]
        drives = DriveSignals(
            safety_reward=0.5,
            gain_reward=0.5,
            efficiency_reward=0.5,
            safety_gap=0.5,
            gain_gap=0.5,
            efficiency_gap=0.5,
            weights={"safety": 0.5, "gain": 0.3, "efficiency": 0.2},
            total_reward=0.5,
        )
        selected = engine.select(tasks, drives)
        self.assertIsNotNone(selected)
        self.assertIsInstance(selected, Task)

    def test_empty_tasks(self) -> None:
        """空入参测试：空任务列表。"""
        engine = DecisionEngine()
        asyncio.run(engine.initialize({"epsilon": 0.0}))
        drives = DriveSignals(
            safety_reward=0.5,
            gain_reward=0.5,
            efficiency_reward=0.5,
            safety_gap=0.5,
            gain_gap=0.5,
            efficiency_gap=0.5,
            weights={"safety": 0.33, "gain": 0.33, "efficiency": 0.34},
            total_reward=0.5,
        )
        selected = engine.select([], drives)
        self.assertIsNone(selected)

    def test_should_interrupt(self) -> None:
        """正常值入参测试：中断判断。"""
        engine = DecisionEngine()
        asyncio.run(engine.initialize({"interrupt_threshold": 0.7}))
        current = Task(
            task_id="t1",
            name="task1",
            task_type="gain",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
        )
        new_drives = DriveSignals(
            safety_reward=0.1,
            gain_reward=0.5,
            efficiency_reward=0.5,
            safety_gap=0.9,
            gain_gap=0.5,
            efficiency_gap=0.5,
            weights={"safety": 0.8, "gain": 0.1, "efficiency": 0.1},
            total_reward=0.4,
        )
        result = engine.should_interrupt(current, new_drives)
        self.assertTrue(result)

    def test_should_not_interrupt_safety(self) -> None:
        """边界极值测试：安全任务不应被安全缺口中断。"""
        engine = DecisionEngine()
        asyncio.run(engine.initialize({"interrupt_threshold": 0.95}))
        current = Task(
            task_id="t1",
            name="task1",
            task_type="safety",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
        )
        new_drives = DriveSignals(
            safety_reward=0.1,
            gain_reward=0.5,
            efficiency_reward=0.5,
            safety_gap=0.5,
            gain_gap=0.5,
            efficiency_gap=0.5,
            weights={"safety": 0.5, "gain": 0.3, "efficiency": 0.2},
            total_reward=0.4,
        )
        engine._task_start_time = engine._get_current_time()
        result = engine.should_interrupt(current, new_drives)
        self.assertFalse(result)

    def test_should_interrupt_by_timeout(self) -> None:
        """边界极值测试：任何任务超时应被中断。"""
        engine = DecisionEngine()
        asyncio.run(engine.initialize({"interrupt_threshold": 0.95}))
        current = Task(
            task_id="t1",
            name="task1",
            task_type="safety",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
        )
        new_drives = DriveSignals(
            safety_reward=0.1,
            gain_reward=0.5,
            efficiency_reward=0.5,
            safety_gap=0.5,
            gain_gap=0.5,
            efficiency_gap=0.5,
            weights={"safety": 0.5, "gain": 0.3, "efficiency": 0.2},
            total_reward=0.4,
        )
        engine._task_start_time = 0.0
        result = engine.should_interrupt(current, new_drives)
        self.assertTrue(result)


class TestTaskExecutor(unittest.TestCase):
    """测试任务执行器。"""

    def test_execute_safety(self) -> None:
        """正常值入参测试：安全任务。"""
        executor = TaskExecutor()
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
        result = asyncio.run(executor.execute(task))
        self.assertEqual(result["status"], "completed")
        self.assertIn("actions", result)

    def test_execute_unknown_type(self) -> None:
        """非法格式测试：未知任务类型。"""
        executor = TaskExecutor()
        task = Task(
            task_id="t1",
            name="unknown",
            task_type="unknown",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
        )
        result = asyncio.run(executor.execute(task))
        self.assertEqual(result["status"], "unknown_task_type")

    def test_cancel_current_task(self) -> None:
        """正常值测试：取消当前任务。"""
        executor = TaskExecutor()
        task = Task(
            task_id="t1",
            name="task1",
            task_type="safety",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
            params={"actions": []},
        )
        executor._current_task = task
        asyncio.run(executor.cancel(task))
        self.assertTrue(executor._cancelled)

    def test_cancel_wrong_task(self) -> None:
        """边界测试：取消不匹配任务。"""
        executor = TaskExecutor()
        task_a = Task(
            task_id="t1",
            name="task1",
            task_type="safety",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
        )
        task_b = Task(
            task_id="t2",
            name="task2",
            task_type="safety",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
        )
        executor._current_task = task_a
        asyncio.run(executor.cancel(task_b))
        self.assertFalse(executor._cancelled)


class TestDecisionEngineExtended(unittest.TestCase):
    """决策引擎扩展测试。"""

    def test_set_epsilon(self) -> None:
        """正常值测试：设置探索率。"""
        engine = DecisionEngine()
        asyncio.run(engine.initialize({"epsilon": 0.2}))
        engine.set_epsilon(0.5)
        self.assertEqual(engine._epsilon, 0.5)

    def test_set_epsilon_clipping(self) -> None:
        """边界测试：探索率裁剪。"""
        engine = DecisionEngine()
        asyncio.run(engine.initialize({"epsilon": 0.2}))
        engine.set_epsilon(2.0)
        self.assertEqual(engine._epsilon, 1.0)
        engine.set_epsilon(-1.0)
        self.assertEqual(engine._epsilon, 0.0)


if __name__ == "__main__":
    unittest.main()
