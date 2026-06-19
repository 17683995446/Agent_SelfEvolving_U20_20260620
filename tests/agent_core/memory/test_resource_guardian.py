"""
资源守护模块单元测试。

覆盖资源检查的四类用例。
"""

import asyncio
import unittest
from typing import Any, Dict

from agent_core.memory.resource_guardian import ResourceGuardian


class TestResourceGuardian(unittest.IsolatedAsyncioTestCase):
    """测试资源守护。"""

    async def test_check_returns_status(self) -> None:
        """正常值测试：检查返回状态。"""
        guardian = ResourceGuardian()
        result = await guardian.check()
        self.assertIn("status", result)
        self.assertIn("metrics", result)
        self.assertIn("can_execute", result)

    async def test_check_status_values(self) -> None:
        """正常值测试：状态值合法。"""
        guardian = ResourceGuardian()
        result = await guardian.check()
        self.assertIn(result["status"], ("safe", "warning", "critical"))

    async def test_check_can_execute(self) -> None:
        """正常值测试：can_execute布尔值。"""
        guardian = ResourceGuardian()
        result = await guardian.check()
        self.assertIsInstance(result["can_execute"], bool)

    async def test_status_from_percent_safe(self) -> None:
        """正常值测试：安全状态。"""
        guardian = ResourceGuardian()
        status = guardian._status_from_percent(50.0, 70.0, 90.0)
        self.assertEqual(status, "safe")

    async def test_status_from_percent_warning(self) -> None:
        """正常值测试：警告状态。"""
        guardian = ResourceGuardian()
        status = guardian._status_from_percent(80.0, 70.0, 90.0)
        self.assertEqual(status, "warning")

    async def test_status_from_percent_critical(self) -> None:
        """正常值测试：严重状态。"""
        guardian = ResourceGuardian()
        status = guardian._status_from_percent(95.0, 70.0, 90.0)
        self.assertEqual(status, "critical")

    async def test_determine_status_critical(self) -> None:
        """正常值测试：判定严重。"""
        guardian = ResourceGuardian()
        metrics = {
            "cpu_status": "critical",
            "memory_status": "safe",
            "disk_status": "safe",
        }
        status = guardian._determine_status(metrics)
        self.assertEqual(status, "critical")

    async def test_determine_status_warning(self) -> None:
        """正常值测试：判定警告。"""
        guardian = ResourceGuardian()
        metrics = {
            "cpu_status": "warning",
            "memory_status": "warning",
            "disk_status": "safe",
        }
        status = guardian._determine_status(metrics)
        self.assertEqual(status, "warning")

    async def test_determine_status_safe(self) -> None:
        """正常值测试：判定安全。"""
        guardian = ResourceGuardian()
        metrics = {
            "cpu_status": "safe",
            "memory_status": "safe",
            "disk_status": "safe",
        }
        status = guardian._determine_status(metrics)
        self.assertEqual(status, "safe")

    async def test_enforce(self) -> None:
        """正常值测试：强制执行。"""
        guardian = ResourceGuardian()
        await guardian.enforce()

    async def test_collect_metrics(self) -> None:
        """正常值测试：收集指标。"""
        guardian = ResourceGuardian()
        metrics = guardian._collect_metrics()
        self.assertIn("cpu_percent", metrics)
        self.assertIn("memory_percent", metrics)
        self.assertIn("disk_percent", metrics)


if __name__ == "__main__":
    unittest.main()
