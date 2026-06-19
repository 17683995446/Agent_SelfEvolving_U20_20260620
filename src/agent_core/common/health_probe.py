"""
健康检查体系模块。

实现多层次健康探针：存活、就绪、深度检查。

第一性原理：
- 不同场景需要不同深度的健康检查
- 存活检查必须极轻量
- 深度检查可暴露潜在问题
"""

import time
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional

from agent_core.common.interfaces import ModuleInterface
from agent_core.common.logger import get_logger


class ProbeLevel(Enum):
    """探针级别。"""

    LIVENESS = "liveness"
    READINESS = "readiness"
    DEEP = "deep"


class HealthProbe:
    """
    健康探针。

    管理多层次健康检查，聚合所有模块状态。
    """

    def __init__(self) -> None:
        self._modules: Dict[str, ModuleInterface] = {}
        self._custom_checks: Dict[str, Callable[[], Coroutine[Any, Any, bool]]] = {}
        self._logger = get_logger()

    def register_module(self, name: str, module: ModuleInterface) -> None:
        """
        注册模块到健康检查。

        Args:
            name: 模块名称。
            module: 模块实例。
        """
        self._modules[name] = module

    def register_custom_check(
        self,
        name: str,
        check: Callable[[], Coroutine[Any, Any, bool]],
    ) -> None:
        """
        注册自定义健康检查。

        Args:
            name: 检查名称。
            check: 异步检查函数。
        """
        self._custom_checks[name] = check

    async def check(self, level: ProbeLevel = ProbeLevel.READINESS) -> Dict[str, Any]:
        """
        执行健康检查。

        Args:
            level: 检查级别。

        Returns:
            健康状态字典。
        """
        if level == ProbeLevel.LIVENESS:
            return {"status": "alive", "timestamp": time.monotonic()}
        results: Dict[str, Any] = {}
        all_healthy = True
        for name, module in self._modules.items():
            try:
                health = await module.health_check()
                healthy = health.get("status") == "healthy"
                results[name] = {"healthy": healthy, "details": health}
                if not healthy:
                    all_healthy = False
            except Exception as exc:
                results[name] = {"healthy": False, "error": str(exc)}
                all_healthy = False
        if level == ProbeLevel.DEEP:
            for name, check in self._custom_checks.items():
                try:
                    ok = await check()
                    results[name] = {"healthy": ok}
                    if not ok:
                        all_healthy = False
                except Exception as exc:
                    results[name] = {"healthy": False, "error": str(exc)}
                    all_healthy = False
        return {
            "status": "healthy" if all_healthy else "unhealthy",
            "timestamp": time.monotonic(),
            "checks": results,
        }

    async def liveness(self) -> Dict[str, Any]:
        """存活检查。"""
        return await self.check(ProbeLevel.LIVENESS)

    async def readiness(self) -> Dict[str, Any]:
        """就绪检查。"""
        return await self.check(ProbeLevel.READINESS)

    async def deep_check(self) -> Dict[str, Any]:
        """深度检查。"""
        return await self.check(ProbeLevel.DEEP)
