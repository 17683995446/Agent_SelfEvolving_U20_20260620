"""
异常自愈模块。

自动诊断模块健康状态，发现问题后自动修复或重启。

第一性原理：
- 生物免疫系统自动识别并清除异常
- 模块故障不应导致系统崩溃
- 修复动作应最小侵入，优先恢复而非重建
"""

import asyncio
import time
import traceback
from typing import Any, Callable, Dict, List, Optional

from agent_core.common.logger import get_logger

_FAILURE_THRESHOLD = 3
_DIAGNOSIS_INTERVAL = 1.0


class SelfHealingManager:
    """
    自愈管理器。

    监测模块健康，执行诊断与修复策略。
    """

    def __init__(self) -> None:
        self._modules: Dict[str, Dict[str, Any]] = {}
        self._logger = get_logger()
        self._failure_counts: Dict[str, int] = {}
        self._last_health: Dict[str, Dict[str, Any]] = {}
        self._running = False

    def register_module(
        self,
        name: str,
        health_checker: Callable[[], Any],
        recovery_action: Optional[Callable[[], Any]] = None,
    ) -> None:
        """注册模块到自愈系统。"""
        self._modules[name] = {
            "health_checker": health_checker,
            "recovery_action": recovery_action,
        }
        self._failure_counts[name] = 0
        self._logger.info(f"[SelfHealing] Module {name} registered")

    async def diagnose(self) -> Dict[str, Any]:
        """执行全系统诊断。"""
        results: Dict[str, Any] = {}
        for name, info in list(self._modules.items()):
            results[name] = await self._check_module(name, info)
        return results

    async def _check_module(
        self, name: str, info: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            health = await info["health_checker"]()
            self._last_health[name] = health
            return self._evaluate_health(name, health)
        except Exception as exc:
            return self._record_error(name, exc)

    def _evaluate_health(
        self, name: str, health: Dict[str, Any]
    ) -> Dict[str, Any]:
        status = health.get("status", "unknown")
        if status in ("healthy", "safe", "warning", "degraded"):
            if status == "healthy" or status == "safe":
                self._failure_counts[name] = 0
            return {"status": status, "action": "none"}
        self._failure_counts[name] += 1
        return {
            "status": status,
            "failures": self._failure_counts[name],
            "action": "monitor",
        }

    def _record_error(self, name: str, exc: Exception) -> Dict[str, Any]:
        self._failure_counts[name] += 1
        self._logger.error(
            f"[SelfHealing] Health check failed for {name}: {exc}"
        )
        return {
            "status": "error",
            "exception": str(exc),
            "failures": self._failure_counts[name],
            "action": "monitor",
        }

    async def heal(self, diagnosis: Dict[str, Any]) -> Dict[str, Any]:
        """根据诊断结果执行修复。"""
        results: Dict[str, Any] = {}
        for name, report in diagnosis.items():
            failures = report.get("failures", 0)
            if failures >= _FAILURE_THRESHOLD:
                results[name] = await self._attempt_recovery(name)
            else:
                results[name] = {"healed": False, "reason": "threshold_not_met"}
        return results

    async def _attempt_recovery(self, name: str) -> Dict[str, Any]:
        """尝试恢复指定模块。"""
        info = self._modules.get(name)
        if info is None:
            return {"healed": False, "reason": "module_not_found"}
        recovery = info.get("recovery_action")
        if recovery is None:
            self._logger.warning(
                f"[SelfHealing] No recovery action for {name}"
            )
            return {"healed": False, "reason": "no_recovery_action"}
        return await self._run_recovery(name, recovery)

    async def _run_recovery(
        self, name: str, recovery: Callable[[], Any]
    ) -> Dict[str, Any]:
        try:
            self._logger.info(f"[SelfHealing] Recovering module {name}")
            await recovery()
            self._failure_counts[name] = 0
            verified = await self._verify_recovery(name)
            return {
                "healed": True,
                "method": "recovery_action",
                "verified": verified,
            }
        except Exception as exc:
            self._logger.error(
                f"[SelfHealing] Recovery failed for {name}: {exc}\n"
                f"{traceback.format_exc()}"
            )
            return {"healed": False, "reason": str(exc)}

    async def _verify_recovery(self, name: str) -> bool:
        """恢复后重新检查健康状态，确认恢复有效。"""
        info = self._modules.get(name)
        if info is None:
            return False
        try:
            health = await info["health_checker"]()
            self._last_health[name] = health
            status = health.get("status", "unknown")
            return status in ("healthy", "safe", "warning", "degraded")
        except Exception as exc:
            self._logger.warning(
                f"[SelfHealing] Recovery verification failed for {name}: {exc}"
            )
            return False

    async def run_diagnosis_loop(self, interval_seconds: float) -> None:
        """持续诊断循环。"""
        self._running = True
        self._logger.info("[SelfHealing] Diagnosis loop started")
        while self._running:
            await asyncio.sleep(interval_seconds)
            if not self._running:
                break
            try:
                diagnosis = await self.diagnose()
                await self.heal(diagnosis)
            except Exception as exc:
                self._logger.error(
                    f"[SelfHealing] Diagnosis loop error: {exc}\n"
                    f"{traceback.format_exc()}"
                )

    def stop(self) -> None:
        """停止诊断循环。"""
        self._running = False
        self._logger.info("[SelfHealing] Diagnosis loop stopped")

    def get_failure_counts(self) -> Dict[str, int]:
        """获取各模块失败次数。"""
        return self._failure_counts.copy()
