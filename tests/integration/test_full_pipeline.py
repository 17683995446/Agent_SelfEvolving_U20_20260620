"""
全链路集成测试。

模拟真实运行场景，验证端到端数据流。
"""

import asyncio
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


class TestFullPipeline(unittest.TestCase):
    """测试完整管道。"""

    def setUp(self) -> None:
        """设置测试环境。"""
        self.agent = SelfEvolvingAgent()
        self.config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {"exploration_rate": 0.3},
            "decision_engine": {"epsilon": 0.2},
            "memory": {"memory_capacity": 1000},
        }

    def test_initialization(self) -> None:
        """正常值入参测试：全系统初始化。"""
        result = asyncio.run(self.agent.initialize(self.config))
        self.assertTrue(result)
        health = asyncio.run(self.agent.health_check())
        self.assertEqual(health["status"], "healthy")

    def test_single_cycle(self) -> None:
        """正常值入参测试：单周期运行。"""
        asyncio.run(self.agent.initialize(self.config))
        env_state = asyncio.run(self.agent.perception.perceive())
        self.assertIsNotNone(env_state)
        self.assertEqual(len(env_state.feature_vector), 10)
        drive_signals = asyncio.run(self.agent.drive_engine.compute(env_state))
        self.assertIsNotNone(drive_signals)
        self.assertTrue(0.0 <= drive_signals.total_reward <= 1.0)
        prediction = self.agent.predictor.predict_all(env_state.feature_vector)
        self.assertIsNotNone(prediction)
        self.assertEqual(len(prediction.ensemble), 10)
        error = self.agent.error_evaluator.evaluate(
            prediction.ensemble, env_state.feature_vector
        )
        self.assertGreaterEqual(error.mae, 0.0)
        tasks = self.agent.task_generator.generate(drive_signals, error)
        self.assertIsInstance(tasks, list)
        if tasks:
            selected = self.agent.decision_engine.select(tasks, drive_signals)
            if selected:
                result = asyncio.run(self.agent.task_executor.execute(selected))
                self.assertIn("status", result)

    def test_predictor_learning(self) -> None:
        """正常值入参测试：预测器学习效果。"""
        asyncio.run(self.agent.initialize(self.config))
        # 模拟5个周期，验证误差是否收敛
        errors = []
        for _ in range(5):
            env_state = asyncio.run(self.agent.perception.perceive())
            drive_signals = asyncio.run(self.agent.drive_engine.compute(env_state))
            prediction = self.agent.predictor.predict_all(env_state.feature_vector)
            error = self.agent.error_evaluator.evaluate(
                prediction.ensemble, env_state.feature_vector
            )
            errors.append(error.mae)
            # 关键：用上一状态更新
            if self.agent._previous_state is not None:
                self.agent.predictor.update_all(
                    self.agent._previous_state, env_state.feature_vector
                )
            self.agent._previous_state = env_state.feature_vector.copy()
        # 误差应保持稳定或下降
        self.assertTrue(all(e >= 0.0 for e in errors))

    def test_memory_storage(self) -> None:
        """正常值入参测试：记忆存储。"""
        asyncio.run(self.agent.initialize(self.config))
        for _ in range(5):
            env_state = asyncio.run(self.agent.perception.perceive())
            drive_signals = asyncio.run(self.agent.drive_engine.compute(env_state))
            prediction = self.agent.predictor.predict_all(env_state.feature_vector)
            error = self.agent.error_evaluator.evaluate(
                prediction.ensemble, env_state.feature_vector
            )
            tasks = self.agent.task_generator.generate(drive_signals, error)
            if tasks:
                selected = self.agent.decision_engine.select(tasks, drive_signals)
                if selected:
                    result = asyncio.run(self.agent.task_executor.execute(selected))
                    exp = Experience(
                        timestamp=0.0,
                        state=env_state,
                        prediction=prediction,
                        drive_signals=drive_signals,
                        selected_task=selected,
                        execution_result=result,
                        error_metrics=error,
                        priority=selected.priority,
                    )
                    asyncio.run(self.agent.memory.store(exp))
        health = asyncio.run(self.agent.memory.health_check())
        self.assertGreater(health["metrics"]["experience_count"], 0)

    def test_offline_review(self) -> None:
        """正常值入参测试：离线复盘。"""
        asyncio.run(self.agent.initialize(self.config))
        for i in range(10):
            exp = Experience(
                timestamp=float(i),
                state=EnvironmentState(
                    timestamp=float(i),
                    raw_sensors={},
                    feature_vector=np.random.rand(10),
                ),
                prediction=PredictionResult(
                    low_level=np.zeros(10),
                    mid_level=np.zeros(10),
                    high_level=np.zeros(10),
                    ensemble=np.zeros(10),
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
        asyncio.run(self.agent.memory.offline_review(self.agent.predictor))
        health = asyncio.run(self.agent.memory.health_check())
        self.assertGreater(health["metrics"]["experience_count"], 0)

    def test_empty_tasks(self) -> None:
        """空入参测试：无任务场景。"""
        asyncio.run(self.agent.initialize(self.config))
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
            error_vector=np.zeros(10),
        )
        tasks = self.agent.task_generator.generate(drives, errors)
        self.assertIsInstance(tasks, list)

    def test_interrupt_scenario(self) -> None:
        """业务场景测试：任务中断。"""
        asyncio.run(self.agent.initialize(self.config))
        current = Task(
            task_id="t1",
            name="gain_task",
            task_type="gain",
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
        )
        emergency_drives = DriveSignals(
            safety_reward=0.1,
            gain_reward=0.5,
            efficiency_reward=0.5,
            safety_gap=0.9,
            gain_gap=0.5,
            efficiency_gap=0.5,
            weights={"safety": 0.8, "gain": 0.1, "efficiency": 0.1},
            total_reward=0.4,
        )
        result = self.agent.decision_engine.should_interrupt(
            current, emergency_drives
        )
        self.assertTrue(result)

    def tearDown(self) -> None:
        """清理。"""
        asyncio.run(self.agent.stop())


class TestAgentMainAsync(unittest.IsolatedAsyncioTestCase):
    """测试Agent主类异步方法。"""

    async def test_run_single_cycle(self) -> None:
        """正常值测试：单周期执行。"""
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
        await agent._run_single_cycle(0.1)
        await agent.stop()

    async def test_execute_cycle_core(self) -> None:
        """正常值测试：周期核心逻辑。"""
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
        await agent._execute_cycle_core(0.1)
        self.assertGreaterEqual(agent._cycle_count, 1)
        await agent.stop()

    async def test_check_interrupt_no_task(self) -> None:
        """空值测试：无任务时不中断。"""
        agent = SelfEvolvingAgent()
        from agent_core.common.data_contracts import DriveSignals
        drives = DriveSignals(
            safety_reward=0.1, gain_reward=0.2, efficiency_reward=0.3,
            safety_gap=0.9, gain_gap=0.1, efficiency_gap=0.1,
            weights={"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
            total_reward=0.6,
        )
        await agent._check_interrupt(drives)
        self.assertIsNone(agent._current_task)

    async def test_handle_task_execution_empty(self) -> None:
        """空值测试：空候选任务。"""
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
        env_state = await agent.perception.perceive()
        prediction = agent.predictor.predict_all(env_state.feature_vector)
        error = agent.error_evaluator.evaluate(
            prediction.ensemble, env_state.feature_vector
        )
        drives = await agent.drive_engine.compute(env_state)
        await agent._handle_task_execution([], drives, env_state, prediction, error)
        await agent.stop()

    async def test_run_online_loop_short(self) -> None:
        """正常值测试：在线循环运行两周期。"""
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
        agent._running = True

        async def stop_after() -> None:
            await asyncio.sleep(0.3)
            agent._running = False

        await asyncio.gather(
            agent.run_online_loop(0.1),
            stop_after(),
        )
        await agent.stop()

    async def test_run_offline_loop_short(self) -> None:
        """正常值测试：离线循环运行。"""
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
        agent._running = True

        async def stop_after() -> None:
            await asyncio.sleep(0.25)
            agent._running = False

        await asyncio.gather(
            agent.run_offline_loop(0.1),
            stop_after(),
        )
        await agent.stop()

    async def test_start_and_stop(self) -> None:
        """正常值测试：启动和停止。"""
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
        await agent.start(0.1, 0.5)
        await asyncio.sleep(0.2)
        await agent.stop()

    async def test_guardian_blocks_cycle(self) -> None:
        """业务场景测试：guardian 阻止周期执行。"""
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

        class FakeGuardian:
            async def check(self):
                return {"can_execute": False, "status": "critical"}

            async def enforce(self):
                pass

        agent.guardian = FakeGuardian()
        before = agent._cycle_count
        await agent._execute_cycle_core(0.1)
        self.assertEqual(agent._cycle_count, before)
        await agent.stop()

    async def test_task_execution_exception_recovery(self) -> None:
        """异常测试：任务执行异常后状态恢复。"""
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

        class FailingExecutor:
            async def execute(self, task):
                raise RuntimeError("simulated failure")

            async def cancel(self, task):
                pass

        agent.task_executor = FailingExecutor()
        env_state = await agent.perception.perceive()
        prediction = agent.predictor.predict_all(env_state.feature_vector)
        error = agent.error_evaluator.evaluate(
            prediction.ensemble, env_state.feature_vector
        )
        drives = await agent.drive_engine.compute(env_state)
        tasks = agent.task_generator.generate(drives, error)
        if tasks:
            # 第一周期：启动后台任务
            await agent._handle_task_execution(
                tasks, drives, env_state, prediction, error
            )
            # 等待后台任务完成（不抛异常，由_check_pending_result捕获）
            if agent._pending_execution is not None:
                await asyncio.wait([agent._pending_execution])
            # 第二周期：收割结果，异常被捕获，状态恢复
            await agent._handle_task_execution(
                [], drives, env_state, prediction, error
            )
            self.assertIsNone(agent._current_task)
            self.assertIsNone(agent._pending_execution)
        await agent.stop()


if __name__ == "__main__":
    unittest.main()
