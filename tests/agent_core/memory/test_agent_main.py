"""
Agent主类单元测试。

覆盖初始化、健康检查、状态获取的四类用例。
"""

import asyncio
import time
import unittest
from typing import Any, Dict

from agent_core.memory.agent_main import SelfEvolvingAgent


class TestSelfEvolvingAgent(unittest.IsolatedAsyncioTestCase):
    """测试Agent主类。"""

    async def test_initialize(self) -> None:
        """正常值测试：初始化成功。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 8},
            "task_generator": {},
            "decision_engine": {},
            "memory": {},
            "dashboard_port": 0,
        }
        result = await agent.initialize(config)
        self.assertTrue(result)
        await agent.stop()

    async def test_health_check(self) -> None:
        """正常值测试：健康检查返回状态。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {},
            "task_generator": {},
            "decision_engine": {},
            "memory": {},
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        health = await agent.health_check()
        self.assertIn("status", health)
        self.assertIn("modules", health)
        await agent.stop()

    async def test_stop_without_start(self) -> None:
        """边界测试：未启动直接停止。"""
        agent = SelfEvolvingAgent()
        await agent.stop()
        self.assertFalse(agent._running)

    async def test_get_runtime_state(self) -> None:
        """正常值测试：获取运行时状态。"""
        agent = SelfEvolvingAgent()
        state = agent._get_runtime_state()
        self.assertIn("status", state)
        self.assertIn("cycle_count", state)
        self.assertIn("recent_errors", state)
        self.assertIn("recent_rewards", state)
        self.assertIn("interrupt_count", state)
        self.assertIn("config", state)
        self.assertIn("current_task", state)

    async def test_adapt_config_if_needed(self) -> None:
        """正常值测试：自适应配置。"""
        agent = SelfEvolvingAgent()
        ts = time.time()
        agent._recent_errors = [(ts, v) for v in [0.1, 0.2, 0.3, 0.4, 0.5]]
        agent._recent_rewards = [(ts, v) for v in [0.1, 0.2, 0.3, 0.4, 0.5]]
        agent._interrupt_history = [(ts, 1)] * 5
        agent._interrupt_count = 5
        agent._adapt_config_if_needed()

    async def test_record_error(self) -> None:
        """正常值测试：记录误差。"""
        agent = SelfEvolvingAgent()
        agent._record_error(0.5)
        self.assertEqual(len(agent._recent_errors), 1)
        self.assertAlmostEqual(agent._recent_errors[0][1], 0.5)

    async def test_record_error_overflow(self) -> None:
        """边界测试：误差历史溢出。"""
        agent = SelfEvolvingAgent()
        for i in range(25):
            agent._record_error(float(i) / 100.0)
        self.assertEqual(len(agent._recent_errors), 20)

    async def test_record_reward(self) -> None:
        """正常值测试：记录奖励。"""
        agent = SelfEvolvingAgent()
        result: Dict[str, Any] = {"reward": 0.8}
        agent._record_reward(result)
        self.assertEqual(len(agent._recent_rewards), 1)
        self.assertAlmostEqual(agent._recent_rewards[0][1], 0.8)

    async def test_build_health_result_healthy(self) -> None:
        """正常值测试：构建健康结果。"""
        agent = SelfEvolvingAgent()
        checks = (
            {"status": "healthy"},
            {"status": "safe"},
        )
        result = agent._build_health_result(checks, ["a", "b"])
        self.assertEqual(result["status"], "healthy")

    async def test_build_health_result_degraded(self) -> None:
        """边界测试：健康结果降级。"""
        agent = SelfEvolvingAgent()
        checks = (
            {"status": "healthy"},
            {"status": "unhealthy"},
        )
        result = agent._build_health_result(checks, ["a", "b"])
        self.assertEqual(result["status"], "degraded")

    async def test_cancel_task_none(self) -> None:
        """空值测试：取消None任务。"""
        agent = SelfEvolvingAgent()
        await agent._cancel_task(None)

    async def test_cancel_task_valid(self) -> None:
        """正常值测试：取消有效任务。"""
        agent = SelfEvolvingAgent()

        async def dummy() -> None:
            await asyncio.sleep(10)

        task = asyncio.create_task(dummy())
        await agent._cancel_task(task)

    async def test_update_predictor_first_call(self) -> None:
        """边界测试：首次更新预测器。"""
        agent = SelfEvolvingAgent()
        import numpy as np

        state = type("S", (), {"feature_vector": np.zeros(10)})()
        agent._update_predictor(state)
        self.assertIsNotNone(agent._previous_state)

    async def test_update_predictor_subsequent_call(self) -> None:
        """正常值测试：后续更新预测器。"""
        agent = SelfEvolvingAgent()
        import numpy as np

        state1 = type("S", (), {"feature_vector": np.zeros(10)})()
        state2 = type("S", (), {"feature_vector": np.ones(10)})()
        agent._update_predictor(state1)
        agent._update_predictor(state2)
        self.assertTrue(np.array_equal(agent._previous_state, np.ones(10)))

    async def test_log_task_result(self) -> None:
        """正常值测试：记录任务结果。"""
        agent = SelfEvolvingAgent()
        agent._log_task_result({"status": "done", "reward": 0.5})

    async def test_log_task_count(self) -> None:
        """正常值测试：记录任务数量。"""
        agent = SelfEvolvingAgent()
        agent._log_task_count([1, 2, 3])

    async def test_log_drives(self) -> None:
        """正常值测试：记录驱力。"""
        agent = SelfEvolvingAgent()
        drives = type(
            "D",
            (),
            {
                "safety_reward": 0.1,
                "safety_gap": 0.2,
                "gain_reward": 0.3,
                "efficiency_reward": 0.4,
                "total_reward": 0.8,
            },
        )()
        agent._log_drives(drives)

    async def test_log_prediction(self) -> None:
        """正常值测试：记录预测。"""
        agent = SelfEvolvingAgent()
        pred = type("P", (), {"confidence": 0.9})()
        agent._log_prediction(pred)

    async def test_log_error(self) -> None:
        """正常值测试：记录误差。"""
        agent = SelfEvolvingAgent()
        error = type("E", (), {"mae": 0.1, "mse": 0.2})()
        agent._log_error(error)

    async def test_register_modules_for_healing(self) -> None:
        """正常值测试：注册自愈模块。"""
        agent = SelfEvolvingAgent()
        agent._register_modules_for_healing()
        self.assertIn("perception", agent._self_healing._modules)

    async def test_start_without_initialize(self) -> None:
        """异常测试：未初始化启动。"""
        agent = SelfEvolvingAgent()
        with self.assertRaises(Exception):
            await agent.start(1.0, 10.0)

    async def test_start_already_running(self) -> None:
        """边界测试：重复启动不崩溃。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {},
            "task_generator": {},
            "decision_engine": {},
            "memory": {},
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        await agent.start(1.0, 10.0)
        await agent.start(1.0, 10.0)
        await agent.stop()

    async def test_update_predictor_no_learn(self) -> None:
        """边界测试：不学习时只推进状态。"""
        agent = SelfEvolvingAgent()
        import numpy as np

        state1 = type("S", (), {"feature_vector": np.zeros(10)})()
        state2 = type("S", (), {"feature_vector": np.ones(10)})()
        agent._update_predictor(state1)
        agent._update_predictor(state2, learn=False)
        self.assertTrue(np.array_equal(agent._previous_state, np.ones(10)))

    async def test_check_guardian_skip(self) -> None:
        """业务场景测试：guardian 阻止后续执行。"""
        agent = SelfEvolvingAgent()

        class FakeGuardian:
            async def check(self):
                return {"can_execute": False, "status": "critical"}

        agent.guardian = FakeGuardian()
        result = await agent._check_guardian(0.01)
        self.assertFalse(result)

    async def test_check_guardian_allow(self) -> None:
        """业务场景测试：guardian 允许执行。"""
        agent = SelfEvolvingAgent()

        class FakeGuardian:
            async def check(self):
                return {"can_execute": True, "status": "safe"}

        agent.guardian = FakeGuardian()
        result = await agent._check_guardian(0.01)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
