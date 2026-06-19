"""
混沌场景集成测试。

模拟真实运行时的高复杂度、高混乱度场景，验证系统鲁棒性。
"""

import asyncio
import random
import unittest
from typing import Any, Dict

import numpy as np

from agent_core.common.data_contracts import (
    DriveSignals,
    EnvironmentState,
    ErrorMetrics,
    PredictionResult,
    Task,
)
from agent_core.memory.agent_main import SelfEvolvingAgent


class FailingPerception:
    """模拟感知模块间歇性故障。"""

    def __init__(self, fail_rate: float = 0.3) -> None:
        self._fail_rate = fail_rate
        self._count = 0

    async def perceive(self) -> EnvironmentState:
        """随机抛出异常。"""
        self._count += 1
        if random.random() < self._fail_rate:
            raise RuntimeError("perception failure")
        return EnvironmentState(
            timestamp=0.0,
            raw_sensors={"cpu": 0.5},
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


class FailingTaskExecutor:
    """模拟任务执行器随机故障。"""

    def __init__(self, fail_rate: float = 0.5) -> None:
        self._fail_rate = fail_rate
        self._current_task: Any = None
        self._cancelled = False

    async def execute(self, task: Task) -> Dict[str, Any]:
        """随机失败或成功。"""
        self._current_task = task
        if random.random() < self._fail_rate:
            raise RuntimeError("task execution failure")
        return {"status": "completed", "actions": ["survived"], "reward": 0.5}

    async def cancel(self, task: Task) -> None:
        if (
            self._current_task is not None
            and self._current_task.task_id == task.task_id
        ):
            self._cancelled = True


class TestChaosScenarios(unittest.IsolatedAsyncioTestCase):
    """混沌场景测试。"""

    async def test_interrupt_storm(self) -> None:
        """高混乱场景：连续中断风暴。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {},
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        class HangingTask:
            task_id = "hang"
            name = "hang"
            task_type = "gain"
            priority = 0.5
            expected_reward = 0.8
            expected_cost = 0.1
            novelty_score = 0.3
            params = {}

        agent.decision_engine._task_start_time = 0.0

        emergency = DriveSignals(
            safety_reward=0.1,
            gain_reward=0.5,
            efficiency_reward=0.5,
            safety_gap=0.95,
            gain_gap=0.5,
            efficiency_gap=0.5,
            weights={"safety": 0.8, "gain": 0.1, "efficiency": 0.1},
            total_reward=0.4,
        )
        for i in range(10):
            task = HangingTask()
            task.task_id = f"hang_{i}"
            agent._current_task = task
            await agent._check_interrupt(emergency)
        self.assertEqual(agent._interrupt_count, 10)
        self.assertLessEqual(len(agent._interrupt_history), 20)
        await agent.stop()

    async def test_task_executor_failure_recovery(self) -> None:
        """高混乱场景：任务执行器随机故障后恢复。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {},
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        agent.task_executor = FailingTaskExecutor(fail_rate=1.0)
        env_state = await agent.perception.perceive()
        prediction = agent.predictor.predict_all(env_state.feature_vector)
        error = agent.error_evaluator.evaluate(
            prediction.ensemble, env_state.feature_vector
        )
        drives = await agent.drive_engine.compute(env_state)
        tasks = agent.task_generator.generate(drives, error)
        for _ in range(5):
            if tasks:
                # 第一周期：启动后台任务
                await agent._handle_task_execution(
                    tasks, drives, env_state, prediction, error
                )
                # 等待后台任务完成（不抛异常）
                if agent._pending_execution is not None:
                    await asyncio.wait([agent._pending_execution])
                # 第二周期：收割结果
                await agent._handle_task_execution(
                    [], drives, env_state, prediction, error
                )
            self.assertIsNone(agent._current_task)
            self.assertIsNone(agent._pending_execution)
        await agent.stop()

    async def test_perception_failure_isolation(self) -> None:
        """高混乱场景：感知故障不破坏Agent主循环。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {},
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        agent.perception = FailingPerception(fail_rate=1.0)
        for _ in range(3):
            await agent._run_single_cycle(0.01)
        await agent.stop()

    async def test_resource_guardian_oscillation(self) -> None:
        """高混乱场景：资源守护反复临界。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {},
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        class OscillatingGuardian:
            def __init__(self) -> None:
                self._allow = False

            async def check(self) -> Dict[str, Any]:
                self._allow = not self._allow
                return {
                    "can_execute": self._allow,
                    "status": "safe" if self._allow else "critical",
                }

            async def enforce(self) -> None:
                pass

        agent.guardian = OscillatingGuardian()
        for _ in range(6):
            await agent._execute_cycle_core(0.01)
        await agent.stop()

    async def test_emotion_driven_exploration_bias(self) -> None:
        """复杂场景：极端情绪下的探索率调整。"""
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
        agent._emotion_engine._state.curiosity = 1.0
        agent._emotion_engine._state.boredom = 1.0
        error = type("E", (), {"mae": 0.5})()
        agent._apply_emotion_to_decision(error, [])
        self.assertGreater(agent.decision_engine._epsilon, 0.2)
        await agent.stop()

    async def test_long_run_stability(self) -> None:
        """长时场景：多周期稳定运行。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {"epsilon": 0.5},
            "memory": {},
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        for _ in range(20):
            await agent._execute_cycle_core(0.01)
        self.assertGreaterEqual(agent._cycle_count, 10)
        health = await agent.health_check()
        self.assertIn(health["status"], ("healthy", "degraded"))
        await agent.stop()


if __name__ == "__main__":
    unittest.main()
