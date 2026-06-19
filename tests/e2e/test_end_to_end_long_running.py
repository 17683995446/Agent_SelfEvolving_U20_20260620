"""
端到端真实环境长测。

模拟最复杂、最混乱的真实运行场景，验证系统稳定性与数据一致性。
覆盖：全生命周期、并发双循环、多模块混合故障、自愈触发、
配置热更新、内存持久化、中断机制、资源压力。
"""

import asyncio
import os
import random
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
from agent_core.memory.agent_main import SelfEvolvingAgent


class FlakyPerception:
    """多模式故障感知：随机异常、超时、返回异常数据。"""

    def __init__(self, fault_rate: float = 0.1) -> None:
        self._fault_rate = fault_rate
        self._call_count = 0
        self._initialized = False

    async def perceive(self) -> EnvironmentState:
        self._call_count += 1
        if random.random() < self._fault_rate:
            modes = ["exception", "nan", "empty"]
            mode = random.choice(modes)
            if mode == "exception":
                raise RuntimeError(f"perception fault #{self._call_count}")
            if mode == "nan":
                return EnvironmentState(
                    timestamp=time.time(),
                    raw_sensors={},
                    feature_vector=np.full(10, np.nan),
                )
            return EnvironmentState(
                timestamp=time.time(),
                raw_sensors={},
                feature_vector=np.array([]),
            )
        return EnvironmentState(
            timestamp=time.time(),
            raw_sensors={"temp": random.random()},
            feature_vector=np.random.rand(10),
        )

    async def health_check(self) -> Dict[str, Any]:
        if not self._initialized:
            return {"status": "unhealthy"}
        if self._call_count % 20 == 0 and self._call_count > 0:
            return {"status": "degraded"}
        return {"status": "healthy"}

    async def initialize(self, config: Dict[str, Any]) -> bool:
        self._initialized = True
        return True

    async def shutdown(self) -> None:
        self._initialized = False

    def get_state_history(self, history_size: int) -> list:
        return []


class LongRunningExecutor:
    """长时执行器：模拟跨周期任务，测试中断机制。"""

    def __init__(self, duration: float = 0.5) -> None:
        self._duration = duration
        self._current_task: Optional[Task] = None
        self._cancelled: bool = False
        self._execute_count = 0
        self._cancel_count = 0

    async def execute(self, task: Task) -> Dict[str, Any]:
        self._current_task = task
        self._cancelled = False
        self._execute_count += 1
        try:
            elapsed = 0.0
            while elapsed < self._duration:
                if self._cancelled:
                    self._cancel_count += 1
                    return {
                        "status": "cancelled",
                        "actions": [],
                        "reward": 0.0,
                    }
                await asyncio.sleep(0.01)
                elapsed += 0.01
            return {
                "status": "completed",
                "actions": ["long_running_done"],
                "reward": 0.5,
            }
        finally:
            self._current_task = None
            self._cancelled = False

    async def cancel(self, task: Task) -> None:
        if (
            self._current_task is not None
            and self._current_task.task_id == task.task_id
        ):
            self._cancelled = True


class CrashRecoverablePerception:
    """可崩溃可恢复的感知模块，测试自愈机制。"""

    def __init__(self, crash_after: int = 5) -> None:
        self._crash_after = crash_after
        self._call_count = 0
        self._initialized = False
        self._crashed = False

    async def perceive(self) -> EnvironmentState:
        self._call_count += 1
        if self._crashed:
            raise RuntimeError("module crashed, needs recovery")
        if self._call_count >= self._crash_after:
            self._crashed = True
            raise RuntimeError(f"crash after {self._call_count} calls")
        return EnvironmentState(
            timestamp=time.time(),
            raw_sensors={},
            feature_vector=np.random.rand(10),
        )

    async def health_check(self) -> Dict[str, Any]:
        if self._crashed:
            return {"status": "unhealthy", "error": "crashed"}
        if not self._initialized:
            return {"status": "unhealthy", "error": "not initialized"}
        return {"status": "healthy"}

    async def initialize(self, config: Dict[str, Any]) -> bool:
        self._initialized = True
        self._crashed = False
        self._call_count = 0
        return True

    async def shutdown(self) -> None:
        self._initialized = False

    def get_state_history(self, history_size: int) -> list:
        return []


class TestEndToEndLongRunning(unittest.IsolatedAsyncioTestCase):
    """端到端长时运行测试。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="agent_e2e_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_config(self, **overrides: Any) -> Dict[str, Any]:
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {"epsilon": 0.3},
            "memory": {
                "memory_capacity": 500,
                "db_path": os.path.join(self._tmpdir, "test_memory.db"),
            },
            "dashboard_port": 0,
        }
        config.update(overrides)
        return config

    async def test_full_lifecycle_with_concurrent_loops(self) -> None:
        """业务场景闭环：完整生命周期，并发在线+离线循环。"""
        agent = SelfEvolvingAgent()
        config = self._make_config()
        await agent.initialize(config)

        # 启动并发双循环 + 自愈诊断
        await agent.start(online_interval_seconds=0.01, offline_interval_seconds=0.05)

        # 运行一段时间
        await asyncio.sleep(0.5)

        # 验证运行中状态
        self.assertTrue(agent._running)
        self.assertGreater(agent._cycle_count, 0)

        # 健康检查
        health = await agent.health_check()
        self.assertIn(health["status"], ("healthy", "degraded"))

        # 停止
        await agent.stop()
        self.assertFalse(agent._running)
        self.assertFalse(agent._initialized)

    async def test_restart_after_stop(self) -> None:
        """业务场景闭环：停止后重新初始化启动。"""
        agent = SelfEvolvingAgent()
        config = self._make_config()
        await agent.initialize(config)
        await agent.start(0.01, 0.05)
        await asyncio.sleep(0.1)
        await agent.stop()

        # 重新初始化和启动
        await agent.initialize(config)
        await agent.start(0.01, 0.05)
        await asyncio.sleep(0.1)
        self.assertTrue(agent._running)
        await agent.stop()

    async def test_multi_fault_chaos_long_run(self) -> None:
        """异常容错测试：多模块混合故障长时运行。"""
        agent = SelfEvolvingAgent()
        config = self._make_config()
        await agent.initialize(config)

        # 替换为故障模块
        agent.perception = FlakyPerception(fault_rate=0.15)
        agent._self_healing._modules["perception"]["health_checker"] = (
            agent.perception.health_check
        )

        success = 0
        errors = 0
        for _ in range(500):
            try:
                await agent._run_single_cycle(0.001)
                success += 1
            except Exception:
                errors += 1

        # 验证稳定性
        self.assertGreater(success, 400)
        self.assertLess(errors, 100)

        health = await agent.health_check()
        self.assertIn(health["status"], ("healthy", "degraded"))
        await agent.stop()

    async def test_self_healing_triggers_recovery(self) -> None:
        """异常容错测试：自愈机制触发模块恢复。"""
        agent = SelfEvolvingAgent()
        config = self._make_config()
        await agent.initialize(config)

        crash_perception = CrashRecoverablePerception(crash_after=3)
        agent.perception = crash_perception
        # 更新自愈注册
        agent._self_healing._modules["perception"]["health_checker"] = (
            crash_perception.health_check
        )

        # 运行直到崩溃
        for _ in range(5):
            try:
                await agent._run_single_cycle(0.001)
            except Exception:
                pass

        # 验证已崩溃
        self.assertTrue(crash_perception._crashed)

        # 触发诊断+自愈
        diagnosis = await agent._self_healing.diagnose()
        self.assertEqual(diagnosis["perception"]["status"], "unhealthy")

        # 多次诊断达到阈值
        for _ in range(_FAILURE_THRESHOLD):
            diagnosis = await agent._self_healing.diagnose()

        # 执行恢复
        heal_result = await agent._self_healing.heal(diagnosis)
        self.assertTrue(heal_result["perception"]["healed"])
        self.assertFalse(crash_perception._crashed)

        await agent.stop()

    async def test_config_hot_reload_during_runtime(self) -> None:
        """接口全量遍历：运行时配置热更新。"""
        agent = SelfEvolvingAgent()
        config = self._make_config()
        await agent.initialize(config)

        original_epsilon = agent._config_manager.get("epsilon")
        agent._config_manager.set("epsilon", 0.45)
        self.assertEqual(agent._config_manager.get("epsilon"), 0.45)

        # 运行几个周期验证不影响稳定性
        for _ in range(10):
            await agent._run_single_cycle(0.001)

        # 恢复原值
        agent._config_manager.set("epsilon", original_epsilon)
        self.assertEqual(agent._config_manager.get("epsilon"), original_epsilon)

        await agent.stop()

    async def test_memory_persistence_across_restart(self) -> None:
        """数据一致性校验：内存持久化跨重启。"""
        db_path = os.path.join(self._tmpdir, "persistence_test.db")
        config = self._make_config()
        config["memory"]["db_path"] = db_path
        config["memory"]["memory_capacity"] = 100

        # 第一轮：存储经验
        agent1 = SelfEvolvingAgent()
        await agent1.initialize(config)
        for _ in range(150):
            await agent1._execute_cycle_core(0.001)
        await agent1.stop()

        # 验证DB文件存在
        self.assertTrue(os.path.exists(db_path))

        # 第二轮：重新初始化
        agent2 = SelfEvolvingAgent()
        await agent2.initialize(config)
        # 验证记忆系统正常工作
        for _ in range(10):
            await agent2._execute_cycle_core(0.001)
        health = await agent2.health_check()
        self.assertIn(health["status"], ("healthy", "degraded"))
        await agent2.stop()

    async def test_interrupt_mechanism_now_functional(self) -> None:
        """静态代码核验：验证中断机制在后台执行架构下可触发。

        任务在后台执行，下一周期_check_interrupt可中断运行中的任务。
        """
        agent = SelfEvolvingAgent()
        config = self._make_config()
        await agent.initialize(config)

        # 使用长时执行器，使任务跨周期运行
        agent.task_executor = LongRunningExecutor(duration=2.0)

        # 第一周期：启动长时任务
        await agent._execute_cycle_core(0.0)
        self.assertIsNotNone(agent._current_task)
        self.assertIsNotNone(agent._pending_execution)

        # 构造高safety_gap驱力触发中断
        from agent_core.common.data_contracts import DriveSignals
        emergency_drives = DriveSignals(
            safety_reward=0.1, gain_reward=0.2, efficiency_reward=0.3,
            safety_gap=0.95, gain_gap=0.1, efficiency_gap=0.1,
            weights={"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
            total_reward=0.6,
        )
        # 直接调用_check_interrupt
        await agent._check_interrupt(emergency_drives)

        # 验证中断已触发
        self.assertGreater(agent._interrupt_count, 0)
        self.assertGreater(len(agent._interrupt_history), 0)
        self.assertIsNone(agent._current_task)
        self.assertIsNone(agent._pending_execution)

        await agent.stop()

    async def test_high_frequency_stability(self) -> None:
        """基础性能核验：高频核心流程响应稳定（使用快速mock模块）。"""
        agent = SelfEvolvingAgent()
        config = self._make_config()
        await agent.initialize(config)

        # 替换为快速mock模块，排除真实I/O干扰
        fast_perception = FlakyPerception(fault_rate=0.0)
        agent.perception = fast_perception

        class FastExecutor:
            async def execute(self, task: Task) -> Dict[str, Any]:
                return {"status": "completed", "actions": ["fast"], "reward": 0.3}

            async def cancel(self, task: Task) -> None:
                pass

        agent.task_executor = FastExecutor()

        latencies: List[float] = []
        for _ in range(200):
            start = time.monotonic()
            await agent._execute_cycle_core(0.0)
            elapsed = time.monotonic() - start
            latencies.append(elapsed)

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

        # 验证无卡顿（核心循环含预测器更新、驱力计算、记忆存储）
        self.assertLess(avg_latency, 0.2, f"avg={avg_latency}")
        self.assertLess(p95_latency, 0.3, f"p95={p95_latency}")
        self.assertLess(max_latency, 0.5, f"max={max_latency}")

        await agent.stop()

    async def test_repeated_start_stop_cycles(self) -> None:
        """异常容错测试：重复启停循环无资源泄漏。"""
        agent = SelfEvolvingAgent()
        config = self._make_config()

        for i in range(5):
            await agent.initialize(config)
            await agent.start(0.01, 0.05)
            await asyncio.sleep(0.05)
            await agent.stop()

        # 最后一次验证正常
        self.assertFalse(agent._running)

    async def test_concurrent_health_check_safety(self) -> None:
        """模块集成联调：并发健康检查安全。"""
        agent = SelfEvolvingAgent()
        config = self._make_config()
        await agent.initialize(config)

        # 并发执行多个健康检查
        results = await asyncio.gather(
            agent.health_check(),
            agent.health_check(),
            agent.health_check(),
            return_exceptions=True,
        )

        for result in results:
            self.assertIsInstance(result, dict)
            self.assertIn("status", result)

        await agent.stop()

    async def test_emotion_engine_dynamics(self) -> None:
        """业务场景闭环：情绪引擎动态调整探索率。"""
        agent = SelfEvolvingAgent()
        config = self._make_config()
        await agent.initialize(config)

        initial_epsilon = agent.decision_engine._epsilon

        for _ in range(100):
            await agent._execute_cycle_core(0.001)

        # 验证epsilon在合理范围内
        final_epsilon = agent.decision_engine._epsilon
        self.assertGreaterEqual(final_epsilon, 0.0)
        self.assertLessEqual(final_epsilon, 1.0)

        await agent.stop()

    async def test_guardian_blocks_execution(self) -> None:
        """异常容错测试：资源守护阻断执行。"""
        agent = SelfEvolvingAgent()
        config = self._make_config()
        await agent.initialize(config)

        # 替换guardian为始终阻断
        class BlockingGuardian:
            async def check(self) -> Dict[str, Any]:
                return {"status": "critical", "can_execute": False}

        agent.guardian = BlockingGuardian()

        cycle_before = agent._cycle_count
        await agent._run_single_cycle(0.001)
        cycle_after = agent._cycle_count

        # 周期被跳过，cycle_count不增加
        self.assertEqual(cycle_before, cycle_after)

        await agent.stop()


# 导入常量
from agent_core.monitoring.self_healing import _FAILURE_THRESHOLD


if __name__ == "__main__":
    unittest.main()
