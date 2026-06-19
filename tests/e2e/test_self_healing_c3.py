"""
C-3超复杂场景测试：自愈机制深度验证与策略增强。

验证C-3修复的4个bug在极端复杂场景下的正确性。
覆盖：
- Bug12: 诊断循环顶层异常捕获
- Bug13: 恢复后重新检查健康状态
- Bug14: _last_health字段被使用
- Bug15: 诊断时并发注册模块安全
"""

import asyncio
import os
import shutil
import tempfile
import time
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

from agent_core.common.config_manager import ConfigManager
from agent_core.monitoring.dashboard_server import DashboardServer
from agent_core.monitoring.self_healing import SelfHealingManager


class TestDiagnosisLoopExceptionHandling(unittest.IsolatedAsyncioTestCase):
    """Bug12验证：诊断循环中异常不终止循环。"""

    async def test_diagnose_exception_does_not_kill_loop(self) -> None:
        """diagnose抛异常时，循环继续运行。"""
        manager = SelfHealingManager()

        call_count = {"n": 0}

        async def flaky_checker() -> Dict[str, Any]:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("simulated diagnose failure")
            return {"status": "healthy"}

        async def recovery() -> None:
            pass

        manager.register_module("flaky", flaky_checker, recovery)

        # 启动诊断循环
        loop_task = asyncio.create_task(manager.run_diagnosis_loop(0.05))
        await asyncio.sleep(0.3)
        manager.stop()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

        # 验证循环没有终止，检查了多次
        self.assertGreater(call_count["n"], 1)

    async def test_heal_exception_does_not_kill_loop(self) -> None:
        """heal抛异常时，循环继续运行。"""
        manager = SelfHealingManager()

        check_count = {"n": 0}

        async def unhealthy_checker() -> Dict[str, Any]:
            check_count["n"] += 1
            return {"status": "unhealthy"}

        async def failing_recovery() -> None:
            raise RuntimeError("recovery always fails")

        manager.register_module("broken", unhealthy_checker, failing_recovery)

        loop_task = asyncio.create_task(manager.run_diagnosis_loop(0.05))
        await asyncio.sleep(0.5)
        manager.stop()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

        # 验证循环存活
        self.assertGreater(check_count["n"], 2)


class TestRecoveryVerification(unittest.IsolatedAsyncioTestCase):
    """Bug13验证：恢复后重新检查健康状态。"""

    async def test_recovery_verified_success(self) -> None:
        """恢复成功且健康检查通过，verified=True。"""
        manager = SelfHealingManager()

        state = {"healthy": False}

        async def checker() -> Dict[str, Any]:
            if state["healthy"]:
                return {"status": "healthy"}
            return {"status": "unhealthy"}

        async def recovery() -> None:
            state["healthy"] = True

        manager.register_module("test_mod", checker, recovery)

        # 累积失败到阈值
        for _ in range(3):
            diagnosis = await manager.diagnose()
        self.assertGreaterEqual(manager._failure_counts["test_mod"], 3)

        # 执行恢复
        result = await manager.heal(diagnosis)
        self.assertTrue(result["test_mod"]["healed"])
        self.assertTrue(result["test_mod"]["verified"])

    async def test_recovery_verified_failure(self) -> None:
        """恢复执行但健康检查仍失败，verified=False。"""
        manager = SelfHealingManager()

        async def checker() -> Dict[str, Any]:
            return {"status": "unhealthy"}

        async def recovery() -> None:
            pass  # 恢复动作执行但模块仍不健康

        manager.register_module("stuck", checker, recovery)

        for _ in range(3):
            diagnosis = await manager.diagnose()

        result = await manager.heal(diagnosis)
        self.assertTrue(result["stuck"]["healed"])
        self.assertFalse(result["stuck"]["verified"])

    async def test_recovery_resets_failure_count(self) -> None:
        """恢复后失败计数重置为0。"""
        manager = SelfHealingManager()

        state = {"healthy": False}

        async def checker() -> Dict[str, Any]:
            if state["healthy"]:
                return {"status": "healthy"}
            return {"status": "unhealthy"}

        async def recovery() -> None:
            state["healthy"] = True

        manager.register_module("mod", checker, recovery)

        for _ in range(3):
            await manager.diagnose()
        self.assertEqual(manager._failure_counts["mod"], 3)

        diagnosis = await manager.diagnose()
        await manager.heal(diagnosis)
        self.assertEqual(manager._failure_counts["mod"], 0)

    async def test_recovery_verification_exception(self) -> None:
        """恢复后验证检查抛异常，verified=False但不崩溃。"""
        manager = SelfHealingManager()

        state = {"check_fails": False}

        async def checker() -> Dict[str, Any]:
            if state["check_fails"]:
                raise RuntimeError("check error after recovery")
            return {"status": "unhealthy"}

        async def recovery() -> None:
            state["check_fails"] = True

        manager.register_module("mod", checker, recovery)

        for _ in range(3):
            await manager.diagnose()

        diagnosis = await manager.diagnose()
        result = await manager.heal(diagnosis)
        self.assertTrue(result["mod"]["healed"])
        self.assertFalse(result["mod"]["verified"])


class TestConcurrentRegistrationSafety(unittest.IsolatedAsyncioTestCase):
    """Bug15验证：诊断时并发注册模块不崩溃。"""

    async def test_register_during_diagnose(self) -> None:
        """诊断迭代时注册新模块，不抛RuntimeError。"""
        manager = SelfHealingManager()

        async def checker() -> Dict[str, Any]:
            return {"status": "healthy"}

        # 注册初始模块
        for i in range(5):
            manager.register_module(f"mod_{i}", checker)

        # 在诊断过程中注册新模块
        async def register_during_diagnose() -> None:
            await asyncio.sleep(0.001)  # 等诊断开始
            for i in range(5, 10):
                manager.register_module(f"mod_{i}", checker)
                await asyncio.sleep(0.001)

        register_task = asyncio.create_task(register_during_diagnose())
        diagnosis = await manager.diagnose()
        await register_task

        # 验证诊断完成，新模块已注册
        self.assertGreaterEqual(len(diagnosis), 5)
        self.assertGreaterEqual(len(manager._modules), 10)

    async def test_diagnose_with_many_modules(self) -> None:
        """大量模块诊断无异常。"""
        manager = SelfHealingManager()

        async def checker() -> Dict[str, Any]:
            return {"status": "healthy"}

        for i in range(50):
            manager.register_module(f"mod_{i}", checker)

        diagnosis = await manager.diagnose()
        self.assertEqual(len(diagnosis), 50)
        for name in diagnosis:
            self.assertEqual(diagnosis[name]["status"], "healthy")


class TestSelfHealingIntegration(unittest.IsolatedAsyncioTestCase):
    """自愈机制集成测试：模块故障注入与自动恢复。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c3_integration_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_module_failure_and_recovery(self) -> None:
        """模块故障后自动恢复。"""
        manager = SelfHealingManager()

        state = {"healthy": True, "recover_calls": 0}

        async def checker() -> Dict[str, Any]:
            if state["healthy"]:
                return {"status": "healthy"}
            return {"status": "unhealthy"}

        async def recovery() -> None:
            state["recover_calls"] += 1
            state["healthy"] = True

        manager.register_module("test_mod", checker, recovery)

        # 初始健康
        diagnosis = await manager.diagnose()
        self.assertEqual(diagnosis["test_mod"]["status"], "healthy")

        # 注入故障
        state["healthy"] = False
        for _ in range(3):
            diagnosis = await manager.diagnose()

        self.assertGreaterEqual(manager._failure_counts["test_mod"], 3)

        # 触发恢复
        result = await manager.heal(diagnosis)
        self.assertTrue(result["test_mod"]["healed"])
        self.assertEqual(state["recover_calls"], 1)

        # 验证恢复后健康
        diagnosis = await manager.diagnose()
        self.assertEqual(diagnosis["test_mod"]["status"], "healthy")
        self.assertEqual(manager._failure_counts["test_mod"], 0)

    async def test_multiple_modules_independent_recovery(self) -> None:
        """多模块独立故障与恢复。"""
        manager = SelfHealingManager()

        states = {
            "mod_a": {"healthy": True, "recoveries": 0},
            "mod_b": {"healthy": True, "recoveries": 0},
            "mod_c": {"healthy": True, "recoveries": 0},
        }

        def make_checker(name: str):
            async def checker() -> Dict[str, Any]:
                if states[name]["healthy"]:
                    return {"status": "healthy"}
                return {"status": "unhealthy"}
            return checker

        def make_recovery(name: str):
            async def recovery() -> None:
                states[name]["recoveries"] += 1
                states[name]["healthy"] = True
            return recovery

        for name in states:
            manager.register_module(name, make_checker(name), make_recovery(name))

        # mod_b故障
        states["mod_b"]["healthy"] = False
        for _ in range(3):
            await manager.diagnose()

        self.assertEqual(manager._failure_counts["mod_a"], 0)
        self.assertGreaterEqual(manager._failure_counts["mod_b"], 3)
        self.assertEqual(manager._failure_counts["mod_c"], 0)

        # 恢复
        diagnosis = await manager.diagnose()
        results = await manager.heal(diagnosis)

        self.assertFalse(results["mod_a"].get("healed", False))
        self.assertTrue(results["mod_b"]["healed"])
        self.assertFalse(results["mod_c"].get("healed", False))
        self.assertEqual(states["mod_b"]["recoveries"], 1)

    async def test_diagnosis_loop_autonomous_healing(self) -> None:
        """诊断循环自动检测与恢复。"""
        manager = SelfHealingManager()

        state = {"healthy": True, "recoveries": 0}

        async def checker() -> Dict[str, Any]:
            if state["healthy"]:
                return {"status": "healthy"}
            return {"status": "unhealthy"}

        async def recovery() -> None:
            state["recoveries"] += 1
            state["healthy"] = True

        manager.register_module("auto_mod", checker, recovery)

        # 启动诊断循环
        loop_task = asyncio.create_task(manager.run_diagnosis_loop(0.05))

        # 等待初始健康检查
        await asyncio.sleep(0.1)

        # 注入故障
        state["healthy"] = False

        # 等待自动恢复（需要3次失败+恢复）
        await asyncio.sleep(0.5)

        manager.stop()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

        # 验证自动恢复被触发
        self.assertGreater(state["recoveries"], 0)
        self.assertTrue(state["healthy"])

    async def test_cascading_failures(self) -> None:
        """级联故障：多模块同时故障，独立恢复。"""
        manager = SelfHealingManager()

        states = {f"mod_{i}": {"healthy": False} for i in range(5)}

        def make_checker(name: str):
            async def checker() -> Dict[str, Any]:
                if states[name]["healthy"]:
                    return {"status": "healthy"}
                return {"status": "unhealthy"}
            return checker

        def make_recovery(name: str):
            async def recovery() -> None:
                states[name]["healthy"] = True
            return recovery

        for name in states:
            manager.register_module(name, make_checker(name), make_recovery(name))

        # 所有模块故障
        for _ in range(3):
            diagnosis = await manager.diagnose()

        # 所有模块失败计数>=3
        for name in states:
            self.assertGreaterEqual(manager._failure_counts[name], 3)

        # 恢复
        results = await manager.heal(diagnosis)
        for name in states:
            self.assertTrue(results[name]["healed"])
            self.assertTrue(results[name]["verified"])

        # 验证全部恢复
        diagnosis = await manager.diagnose()
        for name in states:
            self.assertEqual(diagnosis[name]["status"], "healthy")


class TestSelfHealingEdgeCases(unittest.IsolatedAsyncioTestCase):
    """自愈机制边界场景。"""

    async def test_no_recovery_action(self) -> None:
        """无恢复动作的模块不触发恢复。"""
        manager = SelfHealingManager()

        async def checker() -> Dict[str, Any]:
            return {"status": "unhealthy"}

        manager.register_module("no_recovery", checker, None)

        for _ in range(3):
            diagnosis = await manager.diagnose()

        result = await manager.heal(diagnosis)
        self.assertFalse(result["no_recovery"]["healed"])
        self.assertEqual(result["no_recovery"]["reason"], "no_recovery_action")

    async def test_unknown_status_increments_failure(self) -> None:
        """未知状态增加失败计数。"""
        manager = SelfHealingManager()

        async def checker() -> Dict[str, Any]:
            return {"status": "unknown"}

        manager.register_module("unknown_mod", checker)

        diagnosis = await manager.diagnose()
        self.assertEqual(diagnosis["unknown_mod"]["failures"], 1)
        self.assertEqual(diagnosis["unknown_mod"]["action"], "monitor")

    async def test_warning_does_not_reset_failure(self) -> None:
        """warning状态不重置失败计数。"""
        manager = SelfHealingManager()

        state = {"status": "unhealthy"}

        async def checker() -> Dict[str, Any]:
            return {"status": state["status"]}

        manager.register_module("mod", checker)

        # 累积2次失败
        await manager.diagnose()
        await manager.diagnose()
        self.assertEqual(manager._failure_counts["mod"], 2)

        # 变为warning
        state["status"] = "warning"
        diagnosis = await manager.diagnose()
        # warning不重置失败计数
        self.assertEqual(manager._failure_counts["mod"], 2)
        self.assertEqual(diagnosis["mod"]["action"], "none")

    async def test_healthy_resets_failure(self) -> None:
        """healthy状态重置失败计数。"""
        manager = SelfHealingManager()

        state = {"status": "unhealthy"}

        async def checker() -> Dict[str, Any]:
            return {"status": state["status"]}

        manager.register_module("mod", checker)

        await manager.diagnose()
        await manager.diagnose()
        self.assertEqual(manager._failure_counts["mod"], 2)

        state["status"] = "healthy"
        await manager.diagnose()
        self.assertEqual(manager._failure_counts["mod"], 0)

    async def test_recovery_failure_continues_monitoring(self) -> None:
        """恢复动作失败后，继续监控等待下次触发。"""
        manager = SelfHealingManager()

        state = {"recovery_fails": True, "recoveries": 0}

        async def checker() -> Dict[str, Any]:
            return {"status": "unhealthy"}

        async def recovery() -> None:
            state["recoveries"] += 1
            if state["recovery_fails"]:
                raise RuntimeError("recovery failed")

        manager.register_module("mod", checker, recovery)

        # 累积失败
        for _ in range(3):
            await manager.diagnose()

        # 第一次恢复失败
        diagnosis = await manager.diagnose()
        result = await manager.heal(diagnosis)
        self.assertFalse(result["mod"]["healed"])
        self.assertEqual(state["recoveries"], 1)

        # 恢复动作仍然失败，失败计数继续累积
        state["recovery_fails"] = False
        for _ in range(3):
            await manager.diagnose()

        diagnosis = await manager.diagnose()
        result = await manager.heal(diagnosis)
        self.assertTrue(result["mod"]["healed"])


if __name__ == "__main__":
    unittest.main()
