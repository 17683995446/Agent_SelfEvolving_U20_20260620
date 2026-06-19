"""
C-7并发安全与数据一致性测试。

验证C-7修复的bug在并发场景下的正确性：
- Bug36: MessageBus _subscribers无锁保护（并发subscribe/dispatch崩溃）
- Bug37: MessageBus SQLite连接每次新建/关闭（并发写入database locked）
- Bug39: MemorySystem异步临界区无锁（在线store与离线review并发数据竞争）

并发场景验证：
- 多线程并发MessageBus subscribe/publish不崩溃
- 多协程并发MemorySystem store不丢数据
- 在线store与离线review并发不数据竞争
- DI容器多Agent实例隔离
"""

import asyncio
import os
import shutil
import tempfile
import threading
import time
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

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
from agent_core.memory.memory_module import MemorySystem
from agent_core.monitoring.dashboard_server import DashboardServer


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


def _make_experience(idx: int = 0) -> Experience:
    return Experience(
        timestamp=time.time() + idx,
        state=_make_state(np.array([float(idx % 10)])),
        prediction=_make_prediction(np.array([float(idx % 10)])),
        drive_signals=_make_drives(),
        selected_task=_make_task(),
        execution_result={"status": "completed"},
        error_metrics=_make_error(),
        priority=0.5,
    )


class TestBug36MessageBusSubscribersLock(unittest.TestCase):
    """Bug36验证：MessageBus _subscribers并发读写不崩溃。"""

    def setUp(self) -> None:
        MessageBus._instance = None
        self._tmpdir = tempfile.mkdtemp(prefix="c7_bus_")

    def tearDown(self) -> None:
        MessageBus._instance = None
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_concurrent_subscribe_and_publish_no_crash(self) -> None:
        """并发subscribe和publish不应崩溃。"""
        bus = MessageBus()
        bus._db_path = os.path.join(self._tmpdir, "test_bus.db")
        bus._init_db()

        received: List[Any] = []
        errors: list = []
        stop = threading.Event()

        def subscriber():
            try:
                while not stop.is_set():
                    bus.subscribe("topic", lambda msg: received.append(msg))
            except Exception as exc:
                errors.append(exc)

        def publisher():
            try:
                i = 0
                while not stop.is_set():
                    bus.publish("topic", {"data": i})
                    i += 1
            except Exception as exc:
                errors.append(exc)

        sub_thread = threading.Thread(target=subscriber)
        pub_thread = threading.Thread(target=publisher)
        sub_thread.start()
        pub_thread.start()

        time.sleep(0.3)
        stop.set()
        sub_thread.join(timeout=2.0)
        pub_thread.join(timeout=2.0)

        self.assertEqual(len(errors), 0, f"Concurrent errors: {errors}")


class TestBug37MessageBusDbConnectionReuse(unittest.TestCase):
    """Bug37验证：MessageBus SQLite连接复用，无database locked。"""

    def setUp(self) -> None:
        MessageBus._instance = None
        self._tmpdir = tempfile.mkdtemp(prefix="c7_db_")

    def tearDown(self) -> None:
        MessageBus._instance = None
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_concurrent_publish_no_db_lock(self) -> None:
        """多线程并发publish不应出现database locked错误。"""
        bus = MessageBus()
        bus._db_path = os.path.join(self._tmpdir, "concurrent.db")
        bus._init_db()

        errors: list = []
        msg_count = {"n": 0}
        lock = threading.Lock()

        def publisher(thread_id: int):
            try:
                for i in range(50):
                    bus.publish(f"topic_{thread_id}", {"thread": thread_id, "msg": i})
                    with lock:
                        msg_count["n"] += 1
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=publisher, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        # 不应有database locked错误
        lock_errors = [e for e in errors if "locked" in e.lower()]
        self.assertEqual(
            len(lock_errors), 0,
            f"Database lock errors: {lock_errors}"
        )
        self.assertEqual(msg_count["n"], 200)

    def test_connection_reused(self) -> None:
        """连接应被复用，不每次新建。"""
        bus = MessageBus()
        bus._db_path = os.path.join(self._tmpdir, "reuse.db")
        bus._init_db()

        # 连接应存在
        self.assertIsNotNone(bus._db_conn)

        # 多次publish后连接仍存在
        for i in range(10):
            bus.publish("topic", {"msg": i})

        self.assertIsNotNone(bus._db_conn)


class TestBug39MemorySystemAsyncLock(unittest.IsolatedAsyncioTestCase):
    """Bug39验证：MemorySystem异步临界区锁保护。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c7_mem_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_concurrent_store_no_data_loss(self) -> None:
        """多协程并发store不应丢数据。"""
        mem = MemorySystem()
        await mem.initialize({"db_path": os.path.join(self._tmpdir, "concurrent.db")})

        # 并发存储100个经验
        async def store_batch(start: int, count: int):
            for i in range(start, start + count):
                await mem.store(_make_experience(i))

        # 10个协程各存10个
        tasks = [store_batch(i * 10, 10) for i in range(10)]
        await asyncio.gather(*tasks)

        # 验证所有经验都被存储
        self.assertEqual(len(mem._experiences), 100)
        await mem.shutdown()

    async def test_concurrent_store_and_review_no_crash(self) -> None:
        """并发store和offline_review不应崩溃或数据竞争。"""
        mem = MemorySystem()
        await mem.initialize({"db_path": os.path.join(self._tmpdir, "race.db")})

        # 先存储一些经验供review
        for i in range(50):
            await mem.store(_make_experience(i))

        predictor = MagicMock()
        predictor.update_all = MagicMock()

        errors: list = []

        async def store_loop():
            try:
                for i in range(50, 150):
                    await mem.store(_make_experience(i))
                    await asyncio.sleep(0.001)
            except Exception as exc:
                errors.append(exc)

        async def review_loop():
            try:
                for _ in range(10):
                    await mem.offline_review(predictor)
                    await asyncio.sleep(0.005)
            except Exception as exc:
                errors.append(exc)

        # 并发执行store和review
        await asyncio.gather(store_loop(), review_loop())

        # 不应有错误
        self.assertEqual(len(errors), 0, f"Concurrent errors: {errors}")

        # 验证经验数量正确（50初始 + 100新增）
        self.assertEqual(len(mem._experiences), 150)

        # 验证predictor被训练过
        self.assertGreater(predictor.update_all.call_count, 0)

        await mem.shutdown()

    async def test_concurrent_store_and_sample_no_crash(self) -> None:
        """并发store和sample_experiences不应崩溃。"""
        mem = MemorySystem()
        await mem.initialize({"db_path": os.path.join(self._tmpdir, "sample.db")})

        # 先存储一些经验
        for i in range(20):
            await mem.store(_make_experience(i))

        errors: list = []

        async def store_loop():
            try:
                for i in range(20, 120):
                    await mem.store(_make_experience(i))
                    await asyncio.sleep(0.001)
            except Exception as exc:
                errors.append(exc)

        async def sample_loop():
            try:
                for _ in range(20):
                    result = await mem.sample_experiences(10)
                    # 采样结果不应超过当前经验数
                    self.assertLessEqual(len(result), len(mem._experiences))
                    await asyncio.sleep(0.002)
            except Exception as exc:
                errors.append(exc)

        await asyncio.gather(store_loop(), sample_loop())

        self.assertEqual(len(errors), 0, f"Concurrent errors: {errors}")
        self.assertEqual(len(mem._experiences), 120)
        await mem.shutdown()


class TestDIContainerMultiAgentIsolation(unittest.IsolatedAsyncioTestCase):
    """DI容器多Agent实例隔离验证。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c7_di_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_multiple_agents_independent_memory(self) -> None:
        """多个Agent实例应有独立的memory。"""
        from agent_core.memory.agent_main import SelfEvolvingAgent

        # 创建两个Agent，使用不同db_path
        agent1 = SelfEvolvingAgent()
        config1 = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {"db_path": os.path.join(self._tmpdir, "agent1.db")},
            "dashboard_port": 0,
        }
        await agent1.initialize(config1)

        agent2 = SelfEvolvingAgent()
        config2 = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {"db_path": os.path.join(self._tmpdir, "agent2.db")},
            "dashboard_port": 0,
        }
        await agent2.initialize(config2)

        # 验证memory是不同实例
        self.assertIsNot(agent1.memory, agent2.memory)

        # 在agent1存储经验
        await agent1.memory.store(_make_experience(1))
        self.assertEqual(len(agent1.memory._experiences), 1)

        # agent2的memory应不受影响
        self.assertEqual(len(agent2.memory._experiences), 0)

        # 清理
        agent1._running = False
        agent2._running = False
        await agent1._shutdown_modules()
        await agent2._shutdown_modules()
        agent1._dashboard.stop()
        agent2._dashboard.stop()
        DashboardServer.reset_for_testing()


class TestConcurrentConfigManagerAccess(unittest.TestCase):
    """ConfigManager并发访问验证（Bug28修复回归）。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()

    def test_high_concurrency_set_get(self) -> None:
        """高并发set/get不崩溃且数据一致。"""
        cm = ConfigManager()
        cm.load({"counter": 0, "data": {"items": []}})

        errors: list = []
        stop = threading.Event()
        written_values: list = []
        write_lock = threading.Lock()

        def writer():
            try:
                i = 0
                while not stop.is_set():
                    val = i
                    cm.set("counter", val)
                    with write_lock:
                        written_values.append(val)
                    i += 1
            except Exception as exc:
                errors.append(exc)

        def reader():
            try:
                while not stop.is_set():
                    val = cm.get("counter", 0)
                    # 读取的值应是数字类型
                    assert isinstance(val, (int, float)), f"Bad type: {type(val)}"
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=writer),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
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
        self.assertGreater(len(written_values), 0)


class TestFullSystemConcurrentSafety(unittest.IsolatedAsyncioTestCase):
    """全系统并发安全：在线循环与离线循环并发运行。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c7_full_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_online_offline_concurrent_no_crash(self) -> None:
        """在线循环与离线循环并发运行不崩溃。"""
        from agent_core.memory.agent_main import SelfEvolvingAgent

        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {"db_path": os.path.join(self._tmpdir, "concurrent.db")},
            "dashboard_port": 0,
        }
        await agent.initialize(config)

        # 用即时executor
        async def fast_execute(task):
            return {"status": "completed", "actions": [], "reward": 0.5}

        agent.task_executor.execute = fast_execute

        # 启动在线循环和离线循环
        async def online_loop():
            for _ in range(100):
                await agent._run_single_cycle(0.001)

        async def offline_loop():
            for _ in range(5):
                await agent.memory.offline_review(agent.predictor)
                await asyncio.sleep(0.01)

        # 并发执行
        await asyncio.gather(online_loop(), offline_loop())

        # 验证系统存活
        self.assertGreater(agent._cycle_count, 50)

        # 验证健康状态
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
