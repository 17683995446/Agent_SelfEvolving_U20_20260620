"""
C-5级联故障混沌测试。

验证C-5修复的5个bug在极端复杂场景下的正确性：
- Bug25: DashboardServer端口泄漏（ReusableHTTPServer + server_close）
- Bug26: save_experiences静默数据丢失（异常重新抛出）
- Bug27: _pending_experiences无限增长（1000上限）
- Bug28: ConfigManager并发访问无锁（threading.RLock）
- Bug29: ResourceGuardian阻塞事件循环（asyncio.to_thread + interval=None）

额外覆盖级联故障场景：
- NaN在感知→预测→驱力→记忆链路中的传播与防护
- 模块连锁故障下系统不崩溃
- 资源耗尽时系统优雅降级
"""

import asyncio
import os
import shutil
import tempfile
import threading
import time
import unittest
from typing import Any, Dict
from unittest.mock import MagicMock, patch

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
from agent_core.memory.agent_main import SelfEvolvingAgent
from agent_core.memory.memory_module import MemorySystem
from agent_core.memory.persistence import PersistenceManager
from agent_core.monitoring.dashboard_server import DashboardServer
from agent_core.monitoring.self_healing import SelfHealingManager


def _make_state(features: np.ndarray) -> EnvironmentState:
    return EnvironmentState(
        timestamp=time.time(),
        raw_sensors={},
        feature_vector=features,
    )


def _make_prediction(ensemble: np.ndarray) -> PredictionResult:
    return PredictionResult(
        low_level=ensemble,
        mid_level=ensemble,
        high_level=ensemble,
        ensemble=ensemble,
        confidence=0.8,
    )


def _make_drives() -> DriveSignals:
    return DriveSignals(
        safety_reward=0.5, gain_reward=0.5, efficiency_reward=0.5,
        safety_gap=0.5, gain_gap=0.5, efficiency_gap=0.5,
        weights={"safety": 0.33, "gain": 0.34, "efficiency": 0.33},
        total_reward=0.5,
    )


def _make_error() -> ErrorMetrics:
    return ErrorMetrics(
        mse=0.1, mae=0.2, mape=0.3,
        direction_accuracy=0.5, error_vector=np.array([0.1]),
    )


def _make_task(task_type: str = "safety") -> Task:
    return Task(
        task_id="t1", name="test", task_type=task_type,
        priority=0.5, expected_reward=0.8, expected_cost=0.2,
        novelty_score=0.3, params={},
    )


def _make_experience(features: np.ndarray = None) -> Experience:
    if features is None:
        features = np.random.rand(10)
    return Experience(
        timestamp=time.time(),
        state=_make_state(features),
        prediction=_make_prediction(features),
        drive_signals=_make_drives(),
        selected_task=_make_task(),
        execution_result={"status": "completed"},
        error_metrics=_make_error(),
        priority=0.5,
    )


class TestBug25DashboardPortReuse(unittest.TestCase):
    """Bug25验证：DashboardServer端口泄漏修复。"""

    def setUp(self) -> None:
        DashboardServer.reset_for_testing()
        # 每个测试用唯一端口，避免TIME_WAIT状态干扰
        import random as _r
        self._port = 18000 + _r.randint(0, 999)

    def tearDown(self) -> None:
        DashboardServer.reset_for_testing()

    def test_restart_reuses_port(self) -> None:
        """停止后重新启动应能绑定同一端口。"""
        server = DashboardServer()
        server.register_state_provider(lambda: {"status": "ok"})
        port = self._port
        server.start(port=port)
        self.assertTrue(server._server is not None)

        server.stop()
        self.assertIsNone(server._server)

        # 重新启动应能绑定同一端口（SO_REUSEADDR生效）
        server2 = DashboardServer()
        server2.register_state_provider(lambda: {"status": "ok"})
        server2.start(port=port)
        self.assertTrue(server2._server is not None)
        server2.stop()

    def test_multiple_restart_cycles(self) -> None:
        """多次启停循环不泄漏端口。"""
        port = self._port + 1
        for i in range(5):
            server = DashboardServer()
            server.register_state_provider(lambda: {"status": f"cycle_{i}"})
            server.start(port=port)
            self.assertTrue(server._server is not None)
            server.stop()
            self.assertIsNone(server._server)
            DashboardServer.reset_for_testing()


class TestBug26PersistenceFailurePropagation(unittest.IsolatedAsyncioTestCase):
    """Bug26验证：save_experiences失败时异常重新抛出。"""

    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="c5_bug26_")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_disk_error_raises_exception(self) -> None:
        """磁盘错误时save_experiences应抛出异常而非静默吞掉。"""
        db_path = os.path.join(self._tmpdir, "persist.db")
        persistence = PersistenceManager(db_path)

        exp = _make_experience()
        persistence.save_experiences([exp])

        # 模拟磁盘错误
        with patch.object(
            persistence,
            "_insert_rows",
            side_effect=OSError("disk full"),
        ):
            with self.assertRaises(OSError):
                persistence.save_experiences([exp])

    async def test_successful_save_does_not_raise(self) -> None:
        """正常保存不抛异常。"""
        db_path = os.path.join(self._tmpdir, "ok.db")
        persistence = PersistenceManager(db_path)

        exp = _make_experience()
        # 不应抛出异常
        persistence.save_experiences([exp])


class TestBug27PendingExperiencesCap(unittest.IsolatedAsyncioTestCase):
    """Bug27验证：_pending_experiences上限1000。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c5_bug27_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_pending_capped_at_threshold(self) -> None:
        """pending经验超过上限时丢弃最旧的。"""
        from agent_core.memory.memory_module import _MAX_PENDING_EXPERIENCES

        mem = MemorySystem()
        await mem.initialize({"db_path": os.path.join(self._tmpdir, "cap.db")})

        # 存储超过上限的经验
        total = _MAX_PENDING_EXPERIENCES + 200
        for i in range(total):
            exp = _make_experience(np.array([float(i)]))
            await mem.store(exp)

        # pending不应超过上限
        self.assertLessEqual(
            len(mem._pending_experiences),
            _MAX_PENDING_EXPERIENCES,
        )
        await mem.shutdown()

    async def test_pending_does_not_grow_unbounded(self) -> None:
        """大量存储后pending保持在上限内。"""
        from agent_core.memory.memory_module import _MAX_PENDING_EXPERIENCES

        mem = MemorySystem()
        await mem.initialize({"db_path": os.path.join(self._tmpdir, "ub.db")})

        # 存储大量经验
        for i in range(3000):
            exp = _make_experience(np.array([float(i % 100)]))
            await mem.store(exp)

        self.assertLessEqual(
            len(mem._pending_experiences),
            _MAX_PENDING_EXPERIENCES,
        )
        await mem.shutdown()


class TestBug28ConfigManagerConcurrentAccess(unittest.TestCase):
    """Bug28验证：ConfigManager并发读写线程安全。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()

    def test_concurrent_set_get_no_crash(self) -> None:
        """多线程并发set/get不崩溃。"""
        cm = ConfigManager()
        cm.load({"counter": 0, "data": {"nested": True}})

        errors: list = []
        stop = threading.Event()

        def writer() -> None:
            try:
                i = 0
                while not stop.is_set():
                    cm.set("counter", i)
                    cm.set(f"key_{i % 10}", {"val": i})
                    i += 1
            except Exception as exc:
                errors.append(exc)

        def reader() -> None:
            try:
                while not stop.is_set():
                    cm.get("counter", 0)
                    cm.get("data", {})
                    cm.get_all()
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()

        time.sleep(0.5)
        stop.set()
        for t in threads:
            t.join(timeout=2.0)

        self.assertEqual(len(errors), 0, f"Concurrent errors: {errors}")

    def test_get_returns_deepcopy(self) -> None:
        """get返回深拷贝，外部修改不污染内部状态。"""
        cm = ConfigManager()
        cm.load({"data": {"nested": {"value": 42}}})

        val = cm.get("data")
        val["nested"]["value"] = 999

        # 内部状态不应被修改
        val2 = cm.get("data")
        self.assertEqual(val2["nested"]["value"], 42)

    def test_set_stores_deepcopy(self) -> None:
        """set存储深拷贝，外部修改不污染内部状态。"""
        cm = ConfigManager()
        original = {"key": "value"}
        cm.set("test", original)

        # 修改原始对象
        original["key"] = "modified"

        # 内部存储不应被修改
        stored = cm.get("test")
        self.assertEqual(stored["key"], "value")


class TestBug29GuardianNonBlocking(unittest.IsolatedAsyncioTestCase):
    """Bug29验证：ResourceGuardian不阻塞事件循环。"""

    async def test_check_does_not_block_event_loop(self) -> None:
        """guardian.check()不应阻塞事件循环。"""
        from agent_core.memory.resource_guardian import ResourceGuardian

        guardian = ResourceGuardian()

        # 并发执行check和ping，验证事件循环响应性
        ping_times: list = []
        check_task = asyncio.create_task(guardian.check())

        for _ in range(5):
            start = time.monotonic()
            await asyncio.sleep(0.01)
            ping_times.append(time.monotonic() - start)

        result = await check_task

        # 事件循环应保持响应（每次ping应接近0.01s）
        max_ping = max(ping_times)
        self.assertLess(
            max_ping, 0.1,
            f"Event loop blocked: max_ping={max_ping}"
        )
        self.assertIn(result["status"], ("safe", "warning", "critical"))

    async def test_guardian_with_high_cpu(self) -> None:
        """高CPU时guardian返回critical但不崩溃。"""
        from agent_core.memory.resource_guardian import ResourceGuardian

        guardian = ResourceGuardian()

        # 模拟高CPU
        with patch("psutil.cpu_percent", return_value=95.0):
            result = await guardian.check()

        self.assertEqual(result["status"], "critical")
        self.assertFalse(result["can_execute"])


class TestNaNCascadeProtection(unittest.IsolatedAsyncioTestCase):
    """NaN级联故障防护：NaN在感知→预测→驱力→记忆链路中被清洗。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c5_nan_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_nan_features_do_not_crash_system(self) -> None:
        """NaN特征向量不应导致系统崩溃。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "nan.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        # 注入NaN特征到感知模块（用AsyncMock模拟async方法）
        from unittest.mock import AsyncMock
        nan_state = EnvironmentState(
            timestamp=time.time(),
            raw_sensors={},
            feature_vector=np.array([np.nan, np.inf, -np.inf, 0.5, 0.5,
                                     0.5, 0.5, 0.5, 0.5, 0.5]),
        )
        agent.perception.perceive = AsyncMock(return_value=nan_state)

        # 运行周期不应崩溃（NaN被清洗，周期正常完成）
        for _ in range(10):
            await agent._run_single_cycle(0.001)

        # 系统应存活，周期计数应增加（NaN被清洗后周期正常完成）
        self.assertGreater(agent._cycle_count, 0)

        # 健康检查应返回healthy或degraded
        health = await agent.health_check()
        self.assertIn(health["status"], ("healthy", "degraded"))

        # 清理
        agent._running = False
        await agent._cancel_task(agent._pending_execution)
        agent._pending_execution = None
        agent._current_task = None
        await agent._shutdown_modules()
        agent._dashboard.stop()

    async def test_nan_prediction_does_not_propagate(self) -> None:
        """NaN预测结果不应传播到驱力引擎和记忆。"""
        from agent_core.predictor.ensemble import EnsemblePredictor
        from agent_core.predictor.predictor_module import MultiLayerPredictor

        predictor = MultiLayerPredictor()
        await predictor.initialize({"feature_dimensions": 3})

        # 用NaN输入调用predict_all
        nan_input = np.array([np.nan, np.inf, 0.5])
        result = predictor.predict_all(nan_input)

        # 结果应被清洗，不含NaN
        self.assertTrue(np.all(np.isfinite(result.ensemble)),
                        f"Ensemble contains NaN/inf: {result.ensemble}")
        self.assertTrue(np.isfinite(result.confidence),
                        f"Confidence is not finite: {result.confidence}")


class TestModuleCascadeFailure(unittest.IsolatedAsyncioTestCase):
    """模块连锁故障：一个模块故障不应导致整个系统崩溃。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c5_cascade_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_perception_failure_does_not_crash_agent(self) -> None:
        """感知模块持续故障时Agent不崩溃，周期继续执行。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "cascade.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        # 感知模块持续抛异常
        async def failing_perceive():
            raise ConnectionError("sensor offline")

        agent.perception.perceive = failing_perceive

        # 运行周期，异常应被捕获，不传播
        for _ in range(20):
            await agent._run_single_cycle(0.001)

        # Agent应存活（perceive失败时cycle_count不增加是正常的，
        # 因为计数在perceive之后；关键是系统不崩溃）
        # 验证健康检查仍可执行
        health = await agent.health_check()
        self.assertIn(health["status"], ("healthy", "degraded"))

        # 清理
        agent._running = False
        await agent._cancel_task(agent._pending_execution)
        agent._pending_execution = None
        agent._current_task = None
        await agent._shutdown_modules()
        agent._dashboard.stop()

    async def test_memory_failure_does_not_block_cycle(self) -> None:
        """记忆模块故障时不阻塞周期执行。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "mem_fail.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        # 记忆模块store抛异常
        original_store = agent.memory.store

        async def failing_store(exp):
            raise OSError("database locked")

        agent.memory.store = failing_store

        # 用即时executor确保任务完成
        async def fast_execute(task):
            return {"status": "completed", "actions": [], "reward": 0.5}

        agent.task_executor.execute = fast_execute

        # 运行周期
        for _ in range(15):
            await agent._run_single_cycle(0.001)

        # 等待pending任务完成并收割
        if agent._pending_execution is not None:
            if not agent._pending_execution.done():
                try:
                    await asyncio.wait_for(agent._pending_execution, timeout=3.0)
                except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                    pass
            await agent._run_single_cycle(0.001)

        # Agent应存活
        self.assertGreater(agent._cycle_count, 0)

        # 清理
        agent._running = False
        await agent._cancel_task(agent._pending_execution)
        agent._pending_execution = None
        agent._current_task = None
        await agent._shutdown_modules()
        agent._dashboard.stop()


class TestResourceExhaustionGracefulDegradation(unittest.IsolatedAsyncioTestCase):
    """资源耗尽时系统优雅降级。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c5_resource_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_critical_resource_skips_cycles(self) -> None:
        """资源critical时跳过周期执行，但不崩溃。"""
        from agent_core.memory.resource_guardian import ResourceGuardian

        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "resource.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        # 替换guardian为始终返回critical
        original_guardian = agent.guardian

        class CriticalGuardian:
            async def check(self):
                return {
                    "status": "critical",
                    "metrics": {"cpu_percent": 95.0},
                    "can_execute": False,
                }

        agent.guardian = CriticalGuardian()

        # 运行周期，应全部被跳过
        for _ in range(10):
            await agent._run_single_cycle(0.001)

        # 周期计数应为0（全部被guardian跳过）
        self.assertEqual(agent._cycle_count, 0)

        # 恢复guardian
        agent.guardian = original_guardian

        # 运行周期，应正常执行
        for _ in range(5):
            await agent._run_single_cycle(0.001)

        self.assertGreater(agent._cycle_count, 0)

        # 清理
        agent._running = False
        await agent._cancel_task(agent._pending_execution)
        agent._pending_execution = None
        agent._current_task = None
        await agent._shutdown_modules()
        agent._dashboard.stop()

    async def test_guardian_oscillation_recovery(self) -> None:
        """guardian在safe/critical间振荡，系统应恢复执行。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "oscillate.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        original_guardian = agent.guardian
        call_count = {"n": 0}

        class OscillatingGuardian:
            async def check(self):
                call_count["n"] += 1
                # 每3次返回critical，其余safe
                if call_count["n"] % 3 == 0:
                    return {
                        "status": "critical",
                        "metrics": {},
                        "can_execute": False,
                    }
                return {
                    "status": "safe",
                    "metrics": {},
                    "can_execute": True,
                }

        agent.guardian = OscillatingGuardian()

        # 运行30个周期，约10个被跳过，20个执行
        for _ in range(30):
            await agent._run_single_cycle(0.001)

        # 应有部分周期被执行（非全部跳过）
        self.assertGreater(agent._cycle_count, 5)
        self.assertLess(agent._cycle_count, 30)

        # 清理
        agent._running = False
        await agent._cancel_task(agent._pending_execution)
        agent._pending_execution = None
        agent._current_task = None
        await agent._shutdown_modules()
        agent._dashboard.stop()


class TestFullSystemCascadeChaos(unittest.IsolatedAsyncioTestCase):
    """全系统级联混沌：多模块同时故障，验证系统不崩溃。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c5_full_chaos_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_multi_module_failure_survival(self) -> None:
        """多模块间歇性故障下系统存活。"""
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "multi.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        # 感知模块间歇性返回NaN
        perceive_count = {"n": 0}
        original_perceive = agent.perception.perceive

        async def flaky_perceive():
            perceive_count["n"] += 1
            if perceive_count["n"] % 5 == 0:
                # 返回含NaN的状态
                return EnvironmentState(
                    timestamp=time.time(),
                    raw_sensors={},
                    feature_vector=np.array([np.nan] * 10),
                )
            return await original_perceive()

        agent.perception.perceive = flaky_perceive

        # 记忆模块间歇性故障
        store_count = {"n": 0}
        original_store = agent.memory.store

        async def flaky_store(exp):
            store_count["n"] += 1
            if store_count["n"] % 7 == 0:
                raise OSError("intermittent DB lock")
            await original_store(exp)

        agent.memory.store = flaky_store

        # 用即时executor
        async def fast_execute(task):
            return {"status": "completed", "actions": [], "reward": 0.5}

        agent.task_executor.execute = fast_execute

        # 运行大量周期
        for _ in range(50):
            await agent._run_single_cycle(0.001)

        # 等待pending任务完成
        if agent._pending_execution is not None:
            if not agent._pending_execution.done():
                try:
                    await asyncio.wait_for(agent._pending_execution, timeout=3.0)
                except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                    pass
            await agent._run_single_cycle(0.001)

        # 系统应存活
        self.assertGreater(agent._cycle_count, 10)

        # 健康检查应返回healthy或degraded（非crash）
        health = await agent.health_check()
        self.assertIn(health["status"], ("healthy", "degraded"))

        # 清理
        agent._running = False
        await agent._cancel_task(agent._pending_execution)
        agent._pending_execution = None
        agent._current_task = None
        await agent._shutdown_modules()
        agent._dashboard.stop()


if __name__ == "__main__":
    unittest.main()
