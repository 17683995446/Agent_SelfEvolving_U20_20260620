"""
超复杂场景测试。

验证C-1修复的6个bug在极端复杂场景下的正确性。
覆盖：驱力计算状态记忆、任务生成器重启、消息总线恢复、
因果推理学习、异步执行器性能、Dashboard单例隔离。
"""

import asyncio
import os
import shutil
import tempfile
import time
import unittest
from typing import Any, Dict, List, Optional

import numpy as np

from agent_core.common.config_manager import ConfigManager
from agent_core.common.data_contracts import (
    DriveSignals,
    EnvironmentState,
    ErrorMetrics,
    Experience,
    PredictionResult,
    Task,
)
from agent_core.common.message_bus import MessageBus
from agent_core.drive.drive_calculator import GainDriveCalculator
from agent_core.monitoring.dashboard_server import DashboardServer
from agent_core.memory.agent_main import SelfEvolvingAgent
from agent_core.task.causal_reasoner import CausalReasoner
from agent_core.task.task_generator import TaskGenerator


class TestGainDriveCalculatorStateMemory(unittest.TestCase):
    """Bug1验证：GainDriveCalculator首次调用应存储vector。"""

    def test_first_call_stores_vector(self) -> None:
        """首次调用后_history应有1条记录。"""
        calc = GainDriveCalculator()
        state = EnvironmentState(
            timestamp=time.time(),
            raw_sensors={},
            feature_vector=np.array([0.1, 0.2, 0.3]),
        )
        # 第一次调用
        calc.compute(state)
        self.assertEqual(len(calc._novelty_history), 1)

    def test_subsequent_calls_compute_change(self) -> None:
        """后续调用应计算变化率。"""
        calc = GainDriveCalculator()
        state1 = EnvironmentState(
            timestamp=time.time(),
            raw_sensors={},
            feature_vector=np.array([0.1, 0.2, 0.3]),
        )
        state2 = EnvironmentState(
            timestamp=time.time(),
            raw_sensors={},
            feature_vector=np.array([0.5, 0.6, 0.7]),
        )
        calc.compute(state1)
        calc.compute(state2)
        self.assertEqual(len(calc._novelty_history), 2)

    def test_change_rate_reflects_difference(self) -> None:
        """变化率应反映向量差异。"""
        calc = GainDriveCalculator()
        # 相同向量
        state_same = EnvironmentState(
            timestamp=time.time(),
            raw_sensors={},
            feature_vector=np.array([0.5, 0.5, 0.5]),
        )
        calc.compute(state_same)
        rate_same = calc._compute_change_rate(np.array([0.5, 0.5, 0.5]))
        # 不同向量
        rate_diff = calc._compute_change_rate(np.array([0.9, 0.9, 0.9]))
        self.assertLess(rate_same, rate_diff)


class TestTaskGeneratorRestart(unittest.IsolatedAsyncioTestCase):
    """Bug2验证：TaskGenerator shutdown后initialize模板不丢失。"""

    async def test_restart_preserves_templates(self) -> None:
        """shutdown后重新initialize，模板应可用。"""
        gen = TaskGenerator()
        await gen.initialize({})
        original_count = len(gen._templates)
        self.assertGreater(original_count, 0)

        await gen.shutdown()
        self.assertEqual(len(gen._templates), 0)

        # 重新initialize
        await gen.initialize({})
        self.assertEqual(len(gen._templates), original_count)

    async def test_restart_generates_tasks(self) -> None:
        """重启后能正常生成任务。"""
        gen = TaskGenerator()
        await gen.initialize({})
        await gen.shutdown()
        await gen.initialize({})

        from agent_core.common.data_contracts import DriveSignals, ErrorMetrics
        drives = DriveSignals(
            safety_reward=0.2, gain_reward=0.2, efficiency_reward=0.2,
            safety_gap=0.8, gain_gap=0.8, efficiency_gap=0.8,
            weights={"safety": 0.33, "gain": 0.34, "efficiency": 0.33},
            total_reward=0.2,
        )
        errors = ErrorMetrics(
            mse=0.1, mae=0.3, mape=0.5,
            direction_accuracy=0.5, error_vector=np.array([0.1]),
        )
        tasks = gen.generate(drives, errors)
        self.assertGreater(len(tasks), 0)


class TestMessageBusRecovery(unittest.IsolatedAsyncioTestCase):
    """Bug3验证：MessageBus恢复未消费消息。"""

    def setUp(self) -> None:
        MessageBus._instance = None
        self._tmpdir = tempfile.mkdtemp(prefix="msgbus_test_")

    def tearDown(self) -> None:
        MessageBus._instance = None
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_start_recovers_pending_messages(self) -> None:
        """start应恢复未消费的消息并正确ack。

        publish已同步分发并ack，所以测试直接插入未ack消息验证恢复。
        """
        bus = MessageBus()
        bus._db_path = os.path.join(self._tmpdir, "test_bus.db")
        bus._init_db()

        received: List[Any] = []
        bus.subscribe("test_topic", lambda msg: received.append(msg))

        # 直接插入未ack消息（模拟publish后崩溃场景）
        import sqlite3
        with sqlite3.connect(bus._db_path) as conn:
            conn.execute(
                "INSERT INTO messages (topic, payload, created_at) VALUES (?, ?, ?)",
                ("test_topic", '{"data": "msg1"}', time.time()),
            )
            conn.execute(
                "INSERT INTO messages (topic, payload, created_at) VALUES (?, ?, ?)",
                ("test_topic", '{"data": "msg2"}', time.time()),
            )
            conn.commit()

        # 验证消息已持久化
        with sqlite3.connect(bus._db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        self.assertEqual(count, 2)

        # 启动分发循环（短暂运行）
        task = asyncio.create_task(bus.start())
        await asyncio.sleep(1.0)
        await bus.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # 验证消息已被分发并ack
        self.assertEqual(len(received), 2)
        with sqlite3.connect(bus._db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        self.assertEqual(count, 0)


class TestCausalReasonerLearning(unittest.TestCase):
    """Bug4验证：CausalReasoner能从Experience对象学习。"""

    def test_ingest_experience_object(self) -> None:
        """ingest应正确处理Experience dataclass。"""
        reasoner = CausalReasoner()
        task = Task(
            task_id="t1", name="test", task_type="safety",
            priority=0.5, expected_reward=0.5, expected_cost=0.2,
            novelty_score=0.3, params={},
        )
        state = EnvironmentState(
            timestamp=time.time(),
            raw_sensors={"cpu": {"percent": 50}, "memory": {"percent": 60}},
            feature_vector=np.array([0.5, 0.6]),
        )
        exp = Experience(
            timestamp=time.time(),
            state=state,
            prediction=PredictionResult(
                low_level=np.array([0.5]),
                mid_level=np.array([0.5]),
                high_level=np.array([0.5]),
                ensemble=np.array([0.5]),
                confidence=0.8,
            ),
            drive_signals=DriveSignals(
                safety_reward=0.5, gain_reward=0.5, efficiency_reward=0.5,
                safety_gap=0.5, gain_gap=0.5, efficiency_gap=0.5,
                weights={"safety": 0.33, "gain": 0.34, "efficiency": 0.33},
                total_reward=0.5,
            ),
            selected_task=task,
            execution_result={"status": "completed"},
            error_metrics=ErrorMetrics(
                mse=0.1, mae=0.2, mape=0.3,
                direction_accuracy=0.5, error_vector=np.array([0.1]),
            ),
            priority=0.5,
        )
        reasoner.ingest(exp)

        # 验证因果关系已学习
        effects = reasoner.get_effects("safety")
        self.assertIn("cpu", effects)
        self.assertIn("memory", effects)

    def test_ingest_dict_still_works(self) -> None:
        """ingest应仍支持dict格式。"""
        reasoner = CausalReasoner()
        reasoner.ingest({
            "state": {"cpu": 50},
            "action": {"task_type": "gain"},
        })
        effects = reasoner.get_effects("gain")
        self.assertIn("cpu", effects)

    def test_ingest_none_task_skipped(self) -> None:
        """无任务的Experience应跳过。"""
        reasoner = CausalReasoner()
        state = EnvironmentState(
            timestamp=time.time(),
            raw_sensors={"cpu": 50},
            feature_vector=np.array([0.5]),
        )
        exp = Experience(
            timestamp=time.time(),
            state=state,
            prediction=PredictionResult(
                low_level=np.array([0.5]),
                mid_level=np.array([0.5]),
                high_level=np.array([0.5]),
                ensemble=np.array([0.5]),
                confidence=0.8,
            ),
            drive_signals=DriveSignals(
                safety_reward=0.5, gain_reward=0.5, efficiency_reward=0.5,
                safety_gap=0.5, gain_gap=0.5, efficiency_gap=0.5,
                weights={"safety": 0.33, "gain": 0.34, "efficiency": 0.33},
                total_reward=0.5,
            ),
            selected_task=None,
            execution_result={},
            error_metrics=ErrorMetrics(
                mse=0.1, mae=0.2, mape=0.3,
                direction_accuracy=0.5, error_vector=np.array([0.1]),
            ),
            priority=0.5,
        )
        reasoner.ingest(exp)
        self.assertEqual(len(reasoner._causal_graph), 0)


class TestTaskExecutorAsyncPerformance(unittest.IsolatedAsyncioTestCase):
    """Bug5验证：TaskExecutor异步化后不阻塞事件循环。"""

    async def test_concurrent_execution_not_blocked(self) -> None:
        """任务执行期间事件循环应保持响应。"""
        from agent_core.task.task_executor import TaskExecutor
        executor = TaskExecutor()

        # 创建一个efficiency任务（会触发GC）
        task = Task(
            task_id="t1", name="efficiency", task_type="efficiency",
            priority=0.5, expected_reward=0.5, expected_cost=0.2,
            novelty_score=0.3, params={"actions": ["optimize_cache"]},
        )

        # 启动任务执行
        execute_task = asyncio.create_task(executor.execute(task))

        # 同时检查事件循环响应性
        ping_times: List[float] = []
        for _ in range(5):
            start = time.monotonic()
            await asyncio.sleep(0.01)
            ping_times.append(time.monotonic() - start)

        result = await execute_task

        # 事件循环应保持响应（每次ping应接近0.01s）
        max_ping = max(ping_times)
        self.assertLess(max_ping, 0.1, f"Event loop blocked: max_ping={max_ping}")
        self.assertEqual(result["status"], "completed")

    async def test_safety_task_async(self) -> None:
        """safety任务异步执行。"""
        from agent_core.task.task_executor import TaskExecutor
        executor = TaskExecutor()
        task = Task(
            task_id="t1", name="safety", task_type="safety",
            priority=0.5, expected_reward=0.5, expected_cost=0.2,
            novelty_score=0.3, params={"actions": ["check_logs"]},
        )
        result = await executor.execute(task)
        self.assertEqual(result["status"], "completed")

    async def test_gain_task_async(self) -> None:
        """gain任务异步执行。"""
        from agent_core.task.task_executor import TaskExecutor
        executor = TaskExecutor()
        task = Task(
            task_id="t1", name="gain", task_type="gain",
            priority=0.5, expected_reward=0.5, expected_cost=0.2,
            novelty_score=0.3, params={"actions": ["explore_state_space"]},
        )
        result = await executor.execute(task)
        self.assertEqual(result["status"], "completed")


class TestDashboardServerReset(unittest.TestCase):
    """Bug6验证：DashboardServer单例可重置。"""

    def setUp(self) -> None:
        DashboardServer.reset_for_testing()

    def tearDown(self) -> None:
        DashboardServer.reset_for_testing()

    def test_reset_creates_new_instance(self) -> None:
        """reset后获取新实例。"""
        server1 = DashboardServer()
        DashboardServer.reset_for_testing()
        server2 = DashboardServer()
        self.assertIsNot(server1, server2)

    def test_reset_clears_state_provider(self) -> None:
        """reset清除状态提供者。"""
        server = DashboardServer()
        server.register_state_provider(lambda: {"status": "test"})
        self.assertIsNotNone(DashboardServer._instance._state_provider)

        DashboardServer.reset_for_testing()
        server2 = DashboardServer()
        self.assertIsNone(server2._state_provider)

    def test_multiple_resets_safe(self) -> None:
        """多次reset安全。"""
        for _ in range(5):
            DashboardServer.reset_for_testing()
            DashboardServer()


class TestComplexIntegratedScenario(unittest.IsolatedAsyncioTestCase):
    """超复杂集成场景：多模块协同，验证所有修复。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="complex_e2e_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def _drain_pending_task(self, agent: SelfEvolvingAgent) -> None:
        """等待后台任务完成并收割结果，确保经验被存储。

        Bug29修复后guardian非阻塞，周期执行极快（~0.001s），
        而后台任务（gain任务_sample_cpu_sync需~1秒）无法在少数周期内完成。
        需显式等待pending任务完成并再跑一周期收割结果。
        """
        if agent._pending_execution is None:
            return
        if not agent._pending_execution.done():
            try:
                await asyncio.wait_for(
                    agent._pending_execution, timeout=5.0
                )
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass
        await agent._run_single_cycle(0.001)

    async def test_full_cycle_with_all_fixes(self) -> None:
        """完整周期验证所有C-1修复。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {"epsilon": 0.3},
            "memory": {
                "memory_capacity": 200,
                "db_path": os.path.join(self._tmpdir, "complex.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        # 运行多个周期，验证驱力计算、因果学习、任务执行
        for _ in range(50):
            await agent._run_single_cycle(0.001)

        # Bug29修复后guardian非阻塞，周期执行变快（0.001s/周期），
        # 后台任务（如gain任务的_sample_cpu_sync需1秒）无法在50周期内完成，
        # 需显式等待pending任务完成并再跑一周期收割结果，否则_current_task
        # 永久阻塞新任务选择，导致无经验存储、因果图为空
        await self._drain_pending_task(agent)

        # 验证驱力计算器有状态记忆
        self.assertGreater(
            len(agent.drive_engine._gain_calc._novelty_history), 0
        )

        # 验证因果推理器学习了关系
        self.assertGreater(len(agent._causal_reasoner._causal_graph), 0)

        # 验证周期计数
        self.assertGreater(agent._cycle_count, 0)

        # 验证健康状态
        health = await agent.health_check()
        self.assertIn(health["status"], ("healthy", "degraded"))

        await agent.stop()

    async def test_restart_after_chaos(self) -> None:
        """混沌后重启验证TaskGenerator模板恢复。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "chaos.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        # 运行一段时间
        for _ in range(20):
            await agent._run_single_cycle(0.001)

        # 停止
        await agent.stop()

        # 重新初始化（验证TaskGenerator模板恢复）
        await agent.initialize(config)
        self.assertGreater(len(agent.task_generator._templates), 0)

        # 验证能继续生成任务
        for _ in range(10):
            await agent._run_single_cycle(0.001)

        await agent.stop()


if __name__ == "__main__":
    unittest.main()
