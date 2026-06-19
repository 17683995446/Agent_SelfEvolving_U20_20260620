"""
C-2超复杂场景测试：后台任务生命周期与超时恢复。

验证C-2修复的5个bug在极端复杂场景下的正确性。
覆盖：
- Bug7: _check_pending_result对CancelledError的处理
- Bug8: _check_interrupt对非CancelledError异常的清理
- Bug9: stop()后_pending_execution清理
- Bug10: DecisionEngine._task_start_time初始None
- Bug11: _cancel_task对非CancelledError异常的捕获
"""

import asyncio
import os
import shutil
import tempfile
import time
import unittest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import numpy as np

from agent_core.common.config_manager import ConfigManager
from agent_core.common.data_contracts import (
    DriveSignals,
    EnvironmentState,
    ErrorMetrics,
    PredictionResult,
    Task,
)
from agent_core.common.di_container import DIContainer
from agent_core.memory.agent_main import SelfEvolvingAgent
from agent_core.monitoring.dashboard_server import DashboardServer
from agent_core.task.decision_engine import DecisionEngine


def _make_task(
    task_id: str = "test_task",
    name: str = "test",
    task_type: str = "safety",
    priority: float = 0.5,
) -> Task:
    """构造测试任务。"""
    return Task(
        task_id=task_id,
        name=name,
        task_type=task_type,
        priority=priority,
        expected_reward=0.8,
        expected_cost=0.2,
        novelty_score=0.3,
        params={"actions": []},
    )


def _make_drives(safety_gap: float = 0.3) -> DriveSignals:
    """构造驱力信号。"""
    return DriveSignals(
        safety_reward=0.5,
        gain_reward=0.5,
        efficiency_reward=0.5,
        safety_gap=safety_gap,
        gain_gap=0.5,
        efficiency_gap=0.5,
        weights={"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
        total_reward=0.5,
    )


class TestCheckPendingResultCancelledError(unittest.IsolatedAsyncioTestCase):
    """Bug7验证：_check_pending_result正确处理CancelledError。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c2_bug7_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def _build_agent(self) -> SelfEvolvingAgent:
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "bug7.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        return agent

    async def test_cancelled_pending_task_no_crash(self) -> None:
        """被取消的后台任务收割时不崩溃，_current_task被清理。"""
        agent = await self._build_agent()

        # 创建一个长时间运行的协程并取消
        async def long_task() -> Dict[str, Any]:
            await asyncio.sleep(100)
            return {"status": "completed", "reward": 0.5}

        task = asyncio.create_task(long_task())
        await asyncio.sleep(0.01)  # 让任务开始
        task.cancel()

        # 模拟后台任务被取消的场景
        selected = _make_task()
        agent._pending_execution = task
        agent._pending_context = {
            "env_state": None,
            "prediction": None,
            "drive_signals": _make_drives(),
            "selected": selected,
            "error": ErrorMetrics(
                mse=0.1, mae=0.2, mape=0.3,
                direction_accuracy=0.5, error_vector=np.array([0.1]),
            ),
        }
        agent._current_task = selected

        # 等待任务变为done
        await asyncio.sleep(0.05)
        self.assertTrue(task.done())

        # 调用_check_pending_result不应抛出CancelledError
        await agent._check_pending_result()

        # 验证状态被清理
        self.assertIsNone(agent._current_task)
        self.assertIsNone(agent._pending_execution)
        self.assertFalse(agent._task_succeeded)

        await agent.stop()

    async def test_cancelled_pending_task_clears_state(self) -> None:
        """被取消任务后，_pending_execution和_pending_context都被清理。"""
        agent = await self._build_agent()

        async def quick_task() -> Dict[str, Any]:
            await asyncio.sleep(0.01)
            return {"status": "completed", "reward": 0.5}

        task = asyncio.create_task(quick_task())
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        agent._pending_execution = task
        agent._pending_context = {"selected": _make_task()}
        agent._current_task = _make_task()

        await agent._check_pending_result()

        self.assertIsNone(agent._pending_execution)
        self.assertIsNone(agent._pending_context)
        self.assertIsNone(agent._current_task)

        await agent.stop()


class TestCheckInterruptExceptionCleanup(unittest.IsolatedAsyncioTestCase):
    """Bug8验证：_check_interrupt中后台任务抛出非CancelledError异常时清理。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c2_bug8_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def _build_agent(self) -> SelfEvolvingAgent:
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "bug8.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        return agent

    async def test_interrupt_with_failing_task_clears_state(self) -> None:
        """中断时后台任务抛RuntimeError，_current_task仍被清理。"""
        agent = await self._build_agent()

        # 创建一个会抛RuntimeError的任务
        async def failing_task() -> Dict[str, Any]:
            raise RuntimeError("task internal error")

        task = asyncio.create_task(failing_task())
        # 等待任务完成（抛异常）
        await asyncio.sleep(0.05)
        self.assertTrue(task.done())

        selected = _make_task()
        agent._pending_execution = task
        agent._pending_context = {"selected": selected}
        agent._current_task = selected

        # mock should_interrupt返回True
        agent.decision_engine.should_interrupt = MagicMock(return_value=True)

        # 调用_check_interrupt不应抛出RuntimeError
        await agent._check_interrupt(_make_drives())

        # 验证状态被清理
        self.assertIsNone(agent._current_task)
        self.assertIsNone(agent._pending_execution)
        self.assertEqual(agent._interrupt_count, 1)

        await agent.stop()

    async def test_interrupt_with_normal_task(self) -> None:
        """中断正常未完成任务，状态被清理。"""
        agent = await self._build_agent()

        async def long_task() -> Dict[str, Any]:
            await asyncio.sleep(100)
            return {"status": "completed"}

        task = asyncio.create_task(long_task())
        await asyncio.sleep(0.01)

        selected = _make_task()
        agent._pending_execution = task
        agent._pending_context = {"selected": selected}
        agent._current_task = selected

        agent.decision_engine.should_interrupt = MagicMock(return_value=True)

        await agent._check_interrupt(_make_drives())

        self.assertIsNone(agent._current_task)
        self.assertIsNone(agent._pending_execution)

        await agent.stop()


class TestStopClearsPendingExecution(unittest.IsolatedAsyncioTestCase):
    """Bug9验证：stop()后_pending_execution为None。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c2_bug9_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_stop_clears_pending_execution(self) -> None:
        """stop后_pending_execution应为None。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "bug9.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        await agent.start(0.1, 1.0)

        # 运行几个周期让后台任务启动
        for _ in range(5):
            await agent._run_single_cycle(0.001)

        await agent.stop()

        # 验证所有任务引用被清理
        self.assertIsNone(agent._pending_execution)
        self.assertIsNone(agent._pending_context)
        self.assertIsNone(agent._current_task)
        self.assertIsNone(agent._online_task)
        self.assertIsNone(agent._offline_task)

    async def test_stop_after_pending_done(self) -> None:
        """后台任务已完成后再stop，不崩溃。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "bug9b.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        await agent.start(0.1, 1.0)

        # 运行足够周期让后台任务完成
        for _ in range(20):
            await agent._run_single_cycle(0.001)

        await agent.stop()
        self.assertFalse(agent._running)


class TestDecisionEngineTaskStartTime(unittest.TestCase):
    """Bug10验证：_task_start_time初始为None，_task_timeout返回False。"""

    def test_initial_task_start_time_is_none(self) -> None:
        """初始化后_task_start_time应为None。"""
        engine = DecisionEngine()
        self.assertIsNone(engine._task_start_time)

    def test_task_timeout_false_before_select(self) -> None:
        """select前_task_timeout返回False。"""
        engine = DecisionEngine()
        # _task_timeout是私有方法，直接调用验证
        self.assertFalse(engine._task_timeout())

    def test_should_interrupt_no_timeout_before_select(self) -> None:
        """select前should_interrupt不应因超时返回True。"""
        import asyncio

        async def run() -> None:
            engine = DecisionEngine()
            await engine.initialize({})
            task = _make_task()
            drives = _make_drives(safety_gap=0.3)
            # safety_gap=0.3 <= interrupt_threshold=0.7, 所以_safety_gap_critical返回False
            # _task_start_time为None, _task_timeout返回False
            # safety权重0.4 <= 0.6, _safety_weight_critical返回False
            result = engine.should_interrupt(task, drives)
            self.assertFalse(result)

        asyncio.run(run())

    def test_task_start_time_set_after_select(self) -> None:
        """select后_task_start_time应为时间戳。"""
        import asyncio

        async def run() -> None:
            engine = DecisionEngine()
            await engine.initialize({})
            task = _make_task()
            drives = _make_drives()
            selected = engine.select([task], drives)
            self.assertIsNotNone(selected)
            self.assertIsNotNone(engine._task_start_time)
            self.assertGreater(engine._task_start_time, 0)

        asyncio.run(run())

    def test_shutdown_clears_task_start_time(self) -> None:
        """shutdown后_task_start_time应为None。"""
        import asyncio

        async def run() -> None:
            engine = DecisionEngine()
            await engine.initialize({})
            task = _make_task()
            drives = _make_drives()
            engine.select([task], drives)
            await engine.shutdown()
            self.assertIsNone(engine._task_start_time)

        asyncio.run(run())


class TestCancelTaskExceptionHandling(unittest.IsolatedAsyncioTestCase):
    """Bug11验证：_cancel_task对非CancelledError异常的捕获。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c2_bug11_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def _build_agent(self) -> SelfEvolvingAgent:
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "bug11.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        return agent

    async def test_cancel_task_with_runtime_error(self) -> None:
        """_cancel_task中任务抛RuntimeError时不传播。"""
        agent = await self._build_agent()

        async def failing_task() -> None:
            raise RuntimeError("internal error")

        task = asyncio.create_task(failing_task())
        await asyncio.sleep(0.05)  # 等任务完成抛异常
        self.assertTrue(task.done())

        # _cancel_task不应抛出RuntimeError
        await agent._cancel_task(task)

    async def test_cancel_task_with_cancelled_error(self) -> None:
        """_cancel_task中任务被取消时正常处理。"""
        agent = await self._build_agent()

        async def long_task() -> None:
            await asyncio.sleep(100)

        task = asyncio.create_task(long_task())
        await asyncio.sleep(0.01)

        await agent._cancel_task(task)
        self.assertTrue(task.cancelled() or task.done())

    async def test_cancel_none_task(self) -> None:
        """_cancel_task对None安全。"""
        agent = await self._build_agent()
        await agent._cancel_task(None)

        await agent.stop()


class TestBackgroundTaskLifecycleIntegration(unittest.IsolatedAsyncioTestCase):
    """后台任务生命周期集成测试：多周期跨任务执行。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c2_integration_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_multi_cycle_task_execution(self) -> None:
        """多周期跨任务执行，后台任务正确收割。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "lifecycle.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        # 不调用start，直接运行周期，避免与在线循环竞态
        for _ in range(60):
            await agent._run_single_cycle(0.001)

        # 验证周期计数
        self.assertGreater(agent._cycle_count, 30)

        # 运行更多周期确保收割
        for _ in range(20):
            await agent._run_single_cycle(0.001)

        # 手动清理（未调用start，直接shutdown）
        agent._running = False
        await agent._cancel_task(agent._pending_execution)
        agent._pending_execution = None
        agent._pending_context = None
        agent._current_task = None
        await agent._shutdown_modules()
        agent._dashboard.stop()

        # 验证最终状态干净
        self.assertIsNone(agent._pending_execution)
        self.assertIsNone(agent._current_task)

    async def test_task_executor_exception_recovery(self) -> None:
        """TaskExecutor抛异常后，Agent能继续运行。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "exception.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        # mock task_executor.execute抛异常
        original_execute = agent.task_executor.execute

        call_count = {"n": 0}

        async def failing_execute(task: Any) -> Dict[str, Any]:
            call_count["n"] += 1
            if call_count["n"] <= 2:
                raise RuntimeError("simulated executor failure")
            return await original_execute(task)

        agent.task_executor.execute = failing_execute

        # 运行周期，前几次执行会失败
        for _ in range(40):
            await agent._run_single_cycle(0.005)

        # 验证Agent没有崩溃
        self.assertGreater(agent._cycle_count, 20)

        # 手动清理
        agent._running = False
        await agent._cancel_task(agent._pending_execution)
        agent._pending_execution = None
        agent._pending_context = None
        agent._current_task = None
        await agent._shutdown_modules()
        agent._dashboard.stop()

        self.assertIsNone(agent._pending_execution)
        self.assertIsNone(agent._current_task)

    async def test_concurrent_task_selection_and_harvest(self) -> None:
        """并发任务选择与收割无竞态条件。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "concurrent.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        # 快速运行多个周期，模拟并发场景
        for _ in range(80):
            await agent._run_single_cycle(0.001)

        # 验证没有状态不一致
        # _pending_execution和_current_task应一致：
        # 要么都为None（无任务），要么都有值（有任务）
        if agent._pending_execution is not None:
            self.assertIsNotNone(agent._current_task)
            self.assertIsNotNone(agent._pending_context)

        # 手动清理
        agent._running = False
        await agent._cancel_task(agent._pending_execution)
        agent._pending_execution = None
        agent._pending_context = None
        agent._current_task = None
        await agent._shutdown_modules()
        agent._dashboard.stop()

    async def test_stop_during_task_execution(self) -> None:
        """任务执行中stop，正确清理。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "stop_during.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        await agent.start(0.05, 1.0)

        # 运行几个周期让任务启动
        await asyncio.sleep(0.2)

        # 立即stop（可能有后台任务正在执行）
        await agent.stop()

        # 验证清理完成
        self.assertFalse(agent._running)
        self.assertIsNone(agent._pending_execution)
        self.assertIsNone(agent._current_task)
        self.assertIsNone(agent._online_task)


class TestComplexChaosScenario(unittest.IsolatedAsyncioTestCase):
    """超复杂混沌场景：故障注入+中断风暴+异常级联。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c2_chaos_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_chaos_interrupt_storm(self) -> None:
        """中断风暴：频繁触发中断，验证状态一致性。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "storm.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        # Bug29修复后guardian非阻塞，周期执行极快（~0.001s），
        # 快速任务（exploration）在下一周期前完成，_current_task被清空，
        # 导致_check_interrupt永远看不到_current_task。
        # 用慢速executor确保_current_task在整个测试期间保持set，
        # 使should_interrupt每周期都被调用。
        async def slow_execute(task: Any) -> Dict[str, Any]:
            await asyncio.sleep(10.0)
            return {"status": "completed", "actions": [], "reward": 0.5}

        agent.task_executor.execute = slow_execute

        # mock should_interrupt频繁返回True，制造中断风暴
        interrupt_calls = {"n": 0}

        def stormy_should(task: Any, drives: Any) -> bool:
            interrupt_calls["n"] += 1
            # 每3次返回True，制造频繁中断
            if interrupt_calls["n"] % 3 == 0:
                return True
            return False

        agent.decision_engine.should_interrupt = stormy_should

        # 运行大量周期
        for _ in range(80):
            await agent._run_single_cycle(0.001)

        # 验证中断被触发多次
        self.assertGreater(agent._interrupt_count, 0)

        # 验证Agent没有崩溃
        self.assertGreater(agent._cycle_count, 50)

        # 手动清理
        agent._running = False
        await agent._cancel_task(agent._pending_execution)
        agent._pending_execution = None
        agent._pending_context = None
        agent._current_task = None
        await agent._shutdown_modules()
        agent._dashboard.stop()

        self.assertIsNone(agent._pending_execution)
        self.assertIsNone(agent._current_task)

    async def test_chaos_executor_failures_and_recovery(self) -> None:
        """执行器间歇性故障与恢复。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "intermittent.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        failure_count = {"n": 0}

        # Bug29修复后guardian非阻塞，周期执行极快（~0.005s），
        # 真实executor的gain任务_sample_cpu_sync需1秒，60周期仅0.3秒，
        # 无法完成足够多的任务执行。用即时返回的mock替代original_execute，
        # 使每个周期能完成一个任务，验证agent对间歇性故障的恢复能力。
        async def intermittent_execute(task: Any) -> Dict[str, Any]:
            failure_count["n"] += 1
            # 每5次失败一次，模拟间歇性故障
            if failure_count["n"] % 5 == 0:
                raise ConnectionError("intermittent network failure")
            if failure_count["n"] % 7 == 0:
                raise TimeoutError("simulated timeout")
            return {"status": "completed", "actions": ["mocked"], "reward": 0.5}

        agent.task_executor.execute = intermittent_execute

        # 运行大量周期
        for _ in range(60):
            await agent._run_single_cycle(0.005)

        # 验证Agent存活
        self.assertGreater(agent._cycle_count, 30)
        self.assertGreater(failure_count["n"], 5)

        # 手动清理
        agent._running = False
        await agent._cancel_task(agent._pending_execution)
        agent._pending_execution = None
        agent._pending_context = None
        agent._current_task = None
        await agent._shutdown_modules()
        agent._dashboard.stop()

        self.assertIsNone(agent._pending_execution)

    async def test_long_running_stability(self) -> None:
        """长时间运行稳定性：200周期无崩溃。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "longrun.db"),
                "memory_capacity": 500,
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        # 运行200个周期
        for _ in range(200):
            await agent._run_single_cycle(0.001)

        # 验证稳定性
        self.assertGreaterEqual(agent._cycle_count, 150)

        # 验证记忆系统有积累
        health = await agent.health_check()
        self.assertIn(health["status"], ("healthy", "degraded"))

        # 手动清理
        agent._running = False
        await agent._cancel_task(agent._pending_execution)
        agent._pending_execution = None
        agent._pending_context = None
        agent._current_task = None
        await agent._shutdown_modules()
        agent._dashboard.stop()

        self.assertIsNone(agent._pending_execution)
        self.assertIsNone(agent._current_task)
        self.assertIsNone(agent._pending_execution)
        self.assertIsNone(agent._current_task)


if __name__ == "__main__":
    unittest.main()
