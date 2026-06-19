"""
资源守护模块。

系统资源监控与安全护栏。
"""

import asyncio
from typing import Any, Dict

import gc

import psutil

from agent_core.common.interfaces import IResourceGuardian
from agent_core.common.logger import get_logger


class ResourceGuardian(IResourceGuardian):
    """
    资源守护实现。
    """

    def __init__(self) -> None:
        self._logger = get_logger()

    async def check(self) -> Dict[str, Any]:
        """
        检查资源状态。

        Returns:
            资源状态字典。
        """
        # Bug29修复：_collect_metrics含阻塞调用psutil.cpu_percent，用to_thread避免阻塞事件循环
        metrics = await asyncio.to_thread(self._collect_metrics)
        status = self._determine_status(metrics)
        can_execute = status != "critical"
        return {
            "status": status,
            "metrics": metrics,
            "can_execute": can_execute,
        }

    def _collect_metrics(self) -> Dict[str, Any]:
        # Bug29修复：使用interval=None非阻塞模式，避免阻塞事件循环
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "cpu_percent": cpu_percent,
            "cpu_status": self._status_from_percent(cpu_percent, 70, 90),
            "memory_percent": memory.percent,
            "memory_status": self._status_from_percent(memory.percent, 70, 90),
            "disk_percent": disk.percent,
            "disk_status": self._status_from_percent(disk.percent, 80, 95),
        }

    def _status_from_percent(
        self, percent: float, warning: float, critical: float
    ) -> str:
        if percent >= critical:
            return "critical"
        if percent >= warning:
            return "warning"
        return "safe"

    def _determine_status(self, metrics: Dict[str, Any]) -> str:
        critical_count = sum([
            metrics["cpu_status"] == "critical",
            metrics["memory_status"] == "critical",
            metrics["disk_status"] == "critical",
        ])
        warning_count = sum([
            metrics["cpu_status"] == "warning",
            metrics["memory_status"] == "warning",
            metrics["disk_status"] == "warning",
        ])
        if critical_count > 0:
            return "critical"
        if warning_count > 1:
            return "warning"
        return "safe"

    async def enforce(self) -> None:
        """强制执行资源限制，内存临界时回收。"""
        result = await self.check()
        if result["status"] == "critical":
            self._logger.warning(
                f"[ResourceGuardian] CRITICAL: {result['metrics']}"
            )
            self._emergency_cleanup()
        elif result["status"] == "warning":
            self._logger.warning(
                f"[ResourceGuardian] WARNING: {result['metrics']}"
            )

    def _emergency_cleanup(self) -> None:
        """紧急内存清理。"""
        gc.collect()
        self._logger.info("[ResourceGuardian] Emergency GC triggered")
