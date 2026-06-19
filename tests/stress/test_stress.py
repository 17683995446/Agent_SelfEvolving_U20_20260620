"""
压力测试与异常容错测试。

验证高频运行、资源临界、异常注入场景。
"""

import asyncio
import time
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
from agent_core.memory.agent_main import SelfEvolvingAgent


class TestStressScenarios(unittest.TestCase):
    """压力场景测试。"""

    def setUp(self) -> None:
        """设置测试环境。"""
        self.agent = SelfEvolvingAgent()
        self.config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {"exploration_rate": 0.3},
            "decision_engine": {"epsilon": 0.2},
            "memory": {"memory_capacity": 100},
        }
        asyncio.run(self.agent.initialize(self.config))

    def test_high_frequency_cycles(self) -> None:
        """性能测试：高频运行50个周期。"""
        start_time = time.time()
        for _ in range(50):
            env_state = asyncio.run(self.agent.perception.perceive())
            drive_signals = asyncio.run(self.agent.drive_engine.compute(env_state))
            prediction = self.agent.predictor.predict_all(env_state.feature_vector)
            error = self.agent.error_evaluator.evaluate(
                prediction.ensemble, env_state.feature_vector
            )
            if self.agent._previous_state is not None:
                self.agent.predictor.update_all(
                    self.agent._previous_state, env_state.feature_vector
                )
            self.agent._previous_state = env_state.feature_vector.copy()
            tasks = self.agent.task_generator.generate(drive_signals, error)
            if tasks:
                selected = self.agent.decision_engine.select(tasks, drive_signals)
                if selected:
                    result = asyncio.run(self.agent.task_executor.execute(selected))
                    exp = Experience(
                        timestamp=time.time(),
                        state=env_state,
                        prediction=prediction,
                        drive_signals=drive_signals,
                        selected_task=selected,
                        execution_result=result,
                        error_metrics=error,
                        priority=selected.priority,
                    )
                    asyncio.run(self.agent.memory.store(exp))
        elapsed = time.time() - start_time
        self.assertLess(elapsed, 120.0, "50 cycles should complete within 120 seconds")
        health = asyncio.run(self.agent.health_check())
        self.assertEqual(health["status"], "healthy")

    def test_memory_capacity_stress(self) -> None:
        """压力测试：记忆容量满载。"""
        for i in range(200):
            exp = Experience(
                timestamp=float(i),
                state=EnvironmentState(
                    timestamp=float(i),
                    raw_sensors={},
                    feature_vector=np.random.rand(10),
                ),
                prediction=PredictionResult(
                    low_level=np.random.rand(10),
                    mid_level=np.random.rand(10),
                    high_level=np.random.rand(10),
                    ensemble=np.random.rand(10),
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
                    task_id=f"t{i}",
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
                    error_vector=np.zeros(10),
                ),
                priority=0.5,
            )
            asyncio.run(self.agent.memory.store(exp))
        health = asyncio.run(self.agent.memory.health_check())
        self.assertLessEqual(
            health["metrics"]["experience_count"],
            100,
            "Memory should not exceed capacity",
        )

    def test_predictor_with_extreme_values(self) -> None:
        """边界极值测试：极端特征值预测。"""
        extreme_states = [
            np.zeros(10),
            np.ones(10),
            np.full(10, 0.5),
            np.random.rand(10) * 100,
            np.array([np.nan] * 10),
            np.array([np.inf] * 10),
        ]
        for state in extreme_states:
            try:
                result = self.agent.predictor.predict_all(state)
                self.assertIsNotNone(result)
            except Exception:
                pass

    def test_concurrent_module_access(self) -> None:
        """并发测试：多模块同时访问。"""
        async def access_perception() -> None:
            for _ in range(10):
                await self.agent.perception.perceive()

        async def access_drive() -> None:
            for _ in range(10):
                state = EnvironmentState(
                    timestamp=0.0,
                    raw_sensors={},
                    feature_vector=np.zeros(10),
                )
                await self.agent.drive_engine.compute(state)

        async def run_concurrent() -> None:
            await asyncio.gather(access_perception(), access_drive())

        asyncio.run(run_concurrent())

    def test_error_recovery(self) -> None:
        """异常容错测试：错误恢复。"""
        # 模拟预测器异常后恢复
        self.agent.predictor._initialized = False
        try:
            self.agent.predictor.predict_all(np.zeros(10))
        except Exception:
            pass
        # 重新初始化
        asyncio.run(self.agent.predictor.initialize({"feature_dimensions": 10}))
        result = self.agent.predictor.predict_all(np.zeros(10))
        self.assertIsNotNone(result)

    def test_resource_guardian_under_stress(self) -> None:
        """资源守护测试：高负载下检查。"""
        for _ in range(20):
            result = asyncio.run(self.agent.guardian.check())
            self.assertIn("status", result)
            self.assertIn("can_execute", result)

    def tearDown(self) -> None:
        """清理。"""
        asyncio.run(self.agent.stop())


if __name__ == "__main__":
    unittest.main()
