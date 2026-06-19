"""
任务模板注册表单元测试。

覆盖模板注册、动态扩展、任务生成的四类用例。
"""

import asyncio
import unittest

from agent_core.common.data_contracts import DriveSignals, ErrorMetrics, Task
from agent_core.task.task_generator import TaskGenerator, TaskTemplate


class TestTaskTemplate(unittest.TestCase):
    """测试任务模板。"""

    def test_build_task(self) -> None:
        """正常值测试：构建任务。"""
        template = TaskTemplate(
            name="测试任务",
            task_type="test",
            reward_ratio=0.8,
            cost=0.2,
            actions=["action1"],
            novelty_score=0.5,
        )
        task = template.build(gap=0.5)
        self.assertEqual(task.name, "测试任务")
        self.assertEqual(task.task_type, "test")
        self.assertEqual(task.priority, 0.5)
        self.assertEqual(task.expected_reward, 0.4)
        self.assertEqual(task.expected_cost, 0.2)
        self.assertEqual(task.novelty_score, 0.5)
        self.assertEqual(task.params["actions"], ["action1"])

    def test_build_zero_gap(self) -> None:
        """边界测试：零缺口。"""
        template = TaskTemplate(
            name="零任务", task_type="zero",
            reward_ratio=1.0, cost=0.0,
            actions=[], novelty_score=0.0,
        )
        task = template.build(gap=0.0)
        self.assertEqual(task.expected_reward, 0.0)


class TestTaskGeneratorTemplates(unittest.IsolatedAsyncioTestCase):
    """测试任务生成器模板功能。"""

    async def asyncSetUp(self) -> None:
        """异步设置。"""
        self.generator = TaskGenerator()
        await self.generator.initialize({})

    async def test_default_templates(self) -> None:
        """正常值测试：默认模板已注册。"""
        templates = self.generator.list_templates()
        self.assertIn("safety", templates)
        self.assertIn("gain", templates)
        self.assertIn("efficiency", templates)

    async def test_register_new_template(self) -> None:
        """正常值测试：动态注册新模板。"""
        template = TaskTemplate(
            name="监控任务",
            task_type="monitoring",
            reward_ratio=0.9,
            cost=0.1,
            actions=["check_metrics"],
            novelty_score=0.4,
        )
        self.generator.register_template("monitoring", template)
        self.assertIn("monitoring", self.generator.list_templates())

    async def test_generate_with_custom_template(self) -> None:
        """正常值测试：使用自定义模板生成任务。"""
        template = TaskTemplate(
            name="自定义任务",
            task_type="custom",
            reward_ratio=0.5,
            cost=0.1,
            actions=["custom_action"],
            novelty_score=0.2,
        )
        self.generator.register_template("custom", template)
        drives = DriveSignals(
            safety_reward=0.1,
            gain_reward=0.1,
            efficiency_reward=0.1,
            safety_gap=0.0,
            gain_gap=0.0,
            efficiency_gap=0.0,
            weights={"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
            total_reward=0.3,
        )
        errors = ErrorMetrics(
            mse=0.0, mae=0.0, mape=0.0,
            direction_accuracy=1.0, error_vector=[],
        )
        tasks = self.generator.generate(drives, errors)
        custom_tasks = [t for t in tasks if t.task_type == "custom"]
        self.assertEqual(len(custom_tasks), 0)

    async def test_generate_with_large_gap(self) -> None:
        """正常值测试：大缺口触发任务生成。"""
        drives = DriveSignals(
            safety_reward=0.1,
            gain_reward=0.1,
            efficiency_reward=0.1,
            safety_gap=0.9,
            gain_gap=0.0,
            efficiency_gap=0.0,
            weights={"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
            total_reward=0.3,
        )
        errors = ErrorMetrics(
            mse=0.0, mae=0.0, mape=0.0,
            direction_accuracy=1.0, error_vector=[],
        )
        tasks = self.generator.generate(drives, errors)
        safety_tasks = [t for t in tasks if t.task_type == "safety"]
        self.assertEqual(len(safety_tasks), 1)
        self.assertEqual(safety_tasks[0].name, "安全维护任务")

    async def test_health_check_includes_template_count(self) -> None:
        """正常值测试：健康检查包含模板数量。"""
        health = await self.generator.health_check()
        self.assertEqual(health["metrics"]["template_count"], 3)

    async def test_shutdown_clears_templates(self) -> None:
        """正常值测试：关闭清空模板。"""
        await self.generator.shutdown()
        self.assertEqual(len(self.generator.list_templates()), 0)


if __name__ == "__main__":
    unittest.main()
