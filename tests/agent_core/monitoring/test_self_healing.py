"""
异常自愈模块单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import asyncio
import unittest
from typing import Any, Dict

from agent_core.monitoring.self_healing import SelfHealingManager


class TestSelfHealingManager(unittest.TestCase):
    """测试自愈管理器。"""

    def setUp(self) -> None:
        """每个用例前创建新实例。"""
        self.manager = SelfHealingManager()

    def _healthy_checker(self) -> Dict[str, Any]:
        """健康检查器。"""
        return {"status": "healthy"}

    def _unhealthy_checker(self) -> Dict[str, Any]:
        """不健康检查器。"""
        return {"status": "critical"}

    def _error_checker(self) -> Any:
        """异常检查器。"""
        raise RuntimeError("check failed")

    async def _async_healthy(self) -> Dict[str, Any]:
        """异步健康检查器。"""
        return {"status": "healthy"}

    async def _async_unhealthy(self) -> Dict[str, Any]:
        """异步不健康检查器。"""
        return {"status": "critical"}

    async def _async_error(self) -> Any:
        """异步异常检查器。"""
        raise RuntimeError("async check failed")

    async def _recovery_action(self) -> None:
        """恢复动作。"""
        pass

    def test_register_module(self) -> None:
        """正常值入参测试：注册模块。"""
        self.manager.register_module(
            "test", self._async_healthy, self._recovery_action
        )
        self.assertIn("test", self.manager.get_failure_counts())

    def test_diagnose_healthy(self) -> None:
        """正常值入参测试：健康模块诊断。"""
        self.manager.register_module(
            "healthy", self._async_healthy
        )
        result = asyncio.run(self.manager.diagnose())
        self.assertEqual(result["healthy"]["status"], "healthy")
        self.assertEqual(result["healthy"]["action"], "none")

    def test_diagnose_unhealthy(self) -> None:
        """正常值入参测试：不健康模块诊断。"""
        self.manager.register_module(
            "unhealthy", self._async_unhealthy
        )
        result = asyncio.run(self.manager.diagnose())
        self.assertEqual(result["unhealthy"]["status"], "critical")
        self.assertEqual(result["unhealthy"]["action"], "monitor")

    def test_diagnose_error(self) -> None:
        """正常值入参测试：异常检查器诊断。"""
        self.manager.register_module("error_mod", self._async_error)
        result = asyncio.run(self.manager.diagnose())
        self.assertEqual(result["error_mod"]["status"], "error")
        self.assertEqual(result["error_mod"]["failures"], 1)

    def test_failure_count_accumulation(self) -> None:
        """正常值入参测试：失败次数累积。"""
        self.manager.register_module("bad", self._async_unhealthy)
        for _ in range(3):
            asyncio.run(self.manager.diagnose())
        counts = self.manager.get_failure_counts()
        self.assertEqual(counts["bad"], 3)

    def test_failure_count_reset_on_healthy(self) -> None:
        """正常值入参测试：健康后重置失败次数。"""
        call_count = [0]

        async def toggle() -> Dict[str, Any]:
            call_count[0] += 1
            if call_count[0] <= 2:
                return {"status": "critical"}
            return {"status": "healthy"}

        self.manager.register_module("toggle", toggle)
        asyncio.run(self.manager.diagnose())
        asyncio.run(self.manager.diagnose())
        self.assertEqual(self.manager.get_failure_counts()["toggle"], 2)
        asyncio.run(self.manager.diagnose())
        self.assertEqual(self.manager.get_failure_counts()["toggle"], 0)

    def test_heal_threshold_not_met(self) -> None:
        """正常值入参测试：未达到修复阈值。"""
        self.manager.register_module("mod", self._async_unhealthy)
        diagnosis = asyncio.run(self.manager.diagnose())
        heal_result = asyncio.run(self.manager.heal(diagnosis))
        self.assertFalse(heal_result["mod"]["healed"])

    def test_heal_with_recovery(self) -> None:
        """正常值入参测试：触发修复动作。"""
        recovered = [False]

        async def recover() -> None:
            recovered[0] = True

        self.manager.register_module(
            "mod", self._async_unhealthy, recover
        )
        for _ in range(3):
            asyncio.run(self.manager.diagnose())
        diagnosis = asyncio.run(self.manager.diagnose())
        heal_result = asyncio.run(self.manager.heal(diagnosis))
        self.assertTrue(heal_result["mod"]["healed"])
        self.assertTrue(recovered[0])

    def test_heal_no_recovery_action(self) -> None:
        """正常值入参测试：无恢复动作。"""
        self.manager.register_module("mod", self._async_unhealthy)
        for _ in range(3):
            asyncio.run(self.manager.diagnose())
        diagnosis = asyncio.run(self.manager.diagnose())
        heal_result = asyncio.run(self.manager.heal(diagnosis))
        self.assertFalse(heal_result["mod"]["healed"])
        self.assertEqual(heal_result["mod"]["reason"], "no_recovery_action")

    def test_heal_recovery_failure(self) -> None:
        """正常值入参测试：修复动作失败。"""
        async def bad_recover() -> None:
            raise RuntimeError("recovery failed")

        self.manager.register_module(
            "mod", self._async_unhealthy, bad_recover
        )
        for _ in range(3):
            asyncio.run(self.manager.diagnose())
        diagnosis = asyncio.run(self.manager.diagnose())
        heal_result = asyncio.run(self.manager.heal(diagnosis))
        self.assertFalse(heal_result["mod"]["healed"])

    def test_empty_diagnosis(self) -> None:
        """空入参测试：无模块诊断。"""
        result = asyncio.run(self.manager.diagnose())
        self.assertEqual(result, {})

    def test_multiple_modules(self) -> None:
        """正常值入参测试：多模块诊断。"""
        self.manager.register_module("a", self._async_healthy)
        self.manager.register_module("b", self._async_unhealthy)
        result = asyncio.run(self.manager.diagnose())
        self.assertEqual(len(result), 2)

    def test_heal_unknown_module(self) -> None:
        """非法格式测试：修复未注册模块。"""
        diagnosis = {"unknown": {"failures": 5}}
        result = asyncio.run(self.manager.heal(diagnosis))
        self.assertFalse(result["unknown"]["healed"])


if __name__ == "__main__":
    unittest.main()
