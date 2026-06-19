"""
异常自愈模块。

自动诊断模块健康状态，发现问题后自动修复或重启。

第一性原理：
- 生物免疫系统自动识别并清除异常
- 模块故障不应导致系统崩溃
- 修复动作应最小侵入，优先恢复而非重建

C-8增强：
- 策略库（StrategyRegistry）：多策略选择、命中率跟踪、低效淘汰
- 预诊断机制：基于异常分数提前触发轻量恢复，避免硬故障
- 幂等性保证：冷却期内同一模块不重复恢复
- 回滚机制：恢复失败时记录快照前状态，支持回滚
"""

import asyncio
import time
import traceback
from typing import Any, Awaitable, Callable, Dict, List, Optional

from agent_core.common.logger import get_logger
from agent_core.monitoring.strategy_registry import StrategyRegistry

_FAILURE_THRESHOLD = 3
_DIAGNOSIS_INTERVAL = 1.0
# C-8: 预诊断异常分数阈值（超过则提前触发轻量恢复）
_PRE_DIAGNOSIS_ANOMALY_THRESHOLD = 0.7
# C-8: 幂等冷却期（秒），同一模块恢复动作在此期间不重复触发
_RECOVERY_COOLDOWN_SECONDS = 3.0
# C-8: 回滚快照保留数量
_ROLLBACK_SNAPSHOT_LIMIT = 5


class SelfHealingManager:
    """
    自愈管理器。

    监测模块健康，执行诊断与修复策略。

    C-8增强：
    - 集成 StrategyRegistry 支持多策略
    - 支持预诊断回调（基于预测异常分数）
    - 恢复动作幂等性（冷却期）
    - 回滚快照机制
    """

    def __init__(self) -> None:
        self._modules: Dict[str, Dict[str, Any]] = {}
        self._logger = get_logger()
        self._failure_counts: Dict[str, int] = {}
        self._last_health: Dict[str, Dict[str, Any]] = {}
        self._running = False
        # C-8: 策略库
        self._strategy_registry = StrategyRegistry()
        # C-8: 预诊断回调 {module_name: async_callback returning anomaly_score float}
        self._pre_diagnosis_callbacks: Dict[
            str, Callable[[], Awaitable[float]]
        ] = {}
        # C-8: 轻量恢复动作 {module_name: async_action}（预诊断触发，无需达到失败阈值）
        self._lightweight_recoveries: Dict[
            str, Callable[[], Awaitable[Any]]
        ] = {}
        # C-8: 幂等冷却记录 {module_name: last_recovery_timestamp}
        self._recovery_timestamps: Dict[str, float] = {}
        # C-8: 回滚快照 {module_name: deque of snapshots}
        self._rollback_snapshots: Dict[str, List[Dict[str, Any]]] = {}
        # C-8: 最近恢复记录（用于副作用检测）
        self._recent_recoveries: Dict[str, Dict[str, Any]] = {}

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
        self._rollback_snapshots[name] = []
        # C-8: 若提供recovery_action，同时注册为默认策略"recovery_action"
        if recovery_action is not None:
            self._strategy_registry.register(
                name, "recovery_action", recovery_action, priority=0
            )
        self._logger.info(f"[SelfHealing] Module {name} registered")

    # C-8: 策略库扩展接口
    def register_strategy(
        self,
        module: str,
        name: str,
        action: Callable[[], Awaitable[Any]],
        priority: int = 0,
    ) -> None:
        """注册额外恢复策略到策略库。"""
        self._strategy_registry.register(module, name, action, priority)

    def register_pre_diagnosis(
        self,
        module: str,
        anomaly_callback: Callable[[], Awaitable[float]],
        lightweight_recovery: Callable[[], Awaitable[Any]],
    ) -> None:
        """
        注册预诊断回调与轻量恢复动作。

        Args:
            module: 模块名。
            anomaly_callback: 异步回调，返回异常分数[0,1]。
            lightweight_recovery: 异步轻量恢复动作（无需达到失败阈值）。
        """
        self._pre_diagnosis_callbacks[module] = anomaly_callback
        self._lightweight_recoveries[module] = lightweight_recovery
        self._logger.info(
            f"[SelfHealing] Pre-diagnosis registered for {module}"
        )

    def get_strategy_registry(self) -> StrategyRegistry:
        """获取策略库实例（供外部查询统计）。"""
        return self._strategy_registry

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

    # C-8: 预诊断——基于异常分数提前触发轻量恢复
    async def pre_diagnose(self) -> Dict[str, Any]:
        """
        预诊断：调用各模块异常分数回调，超阈值则触发轻量恢复。

        与 diagnose() 的区别：
        - diagnose 基于健康检查的失败计数，达到阈值才恢复（硬故障）
        - pre_diagnose 基于异常分数，超阈值即轻量恢复（软故障/早期预警）

        Returns:
            各模块预诊断结果。
        """
        results: Dict[str, Any] = {}
        for module, callback in list(self._pre_diagnosis_callbacks.items()):
            try:
                score = await callback()
                score = float(score) if score is not None else 0.0
                results[module] = {
                    "anomaly_score": score,
                    "threshold": _PRE_DIAGNOSIS_ANOMALY_THRESHOLD,
                }
                if score >= _PRE_DIAGNOSIS_ANOMALY_THRESHOLD:
                    # C-8: 幂等检查——冷却期内不重复触发
                    if self._is_in_cooldown(module):
                        results[module]["action"] = "cooldown_skip"
                        continue
                    recovery = self._lightweight_recoveries.get(module)
                    if recovery is None:
                        results[module]["action"] = "no_lightweight_recovery"
                        continue
                    await self._execute_lightweight_recovery(module, recovery)
                    results[module]["action"] = "lightweight_recovery"
                else:
                    results[module]["action"] = "none"
            except Exception as exc:
                self._logger.warning(
                    f"[SelfHealing] Pre-diagnosis failed for {module}: {exc}"
                )
                results[module] = {
                    "anomaly_score": 0.0,
                    "action": "error",
                    "reason": str(exc),
                }
        return results

    def _is_in_cooldown(self, module: str) -> bool:
        """检查模块是否在恢复冷却期内。"""
        last = self._recovery_timestamps.get(module, 0.0)
        return (time.time() - last) < _RECOVERY_COOLDOWN_SECONDS

    async def _execute_lightweight_recovery(
        self,
        module: str,
        recovery: Callable[[], Awaitable[Any]],
    ) -> None:
        """执行轻量恢复并记录时间戳。"""
        self._recovery_timestamps[module] = time.time()
        try:
            await recovery()
            self._logger.info(
                f"[SelfHealing] Lightweight recovery executed for {module}"
            )
        except Exception as exc:
            self._logger.warning(
                f"[SelfHealing] Lightweight recovery failed for {module}: {exc}"
            )

    async def _attempt_recovery(self, name: str) -> Dict[str, Any]:
        """尝试恢复指定模块。"""
        info = self._modules.get(name)
        if info is None:
            return {"healed": False, "reason": "module_not_found"}
        # C-8: 幂等检查——冷却期内跳过
        if self._is_in_cooldown(name):
            self._logger.info(
                f"[SelfHealing] Recovery skipped for {name} (cooldown)"
            )
            return {"healed": False, "reason": "cooldown"}
        # C-8: 策略库选择
        strategy_name = self._strategy_registry.select(name)
        if strategy_name is None:
            # 回退到原始recovery_action
            recovery = info.get("recovery_action")
            if recovery is None:
                self._logger.warning(
                    f"[SelfHealing] No recovery action for {name}"
                )
                return {"healed": False, "reason": "no_recovery_action"}
            return await self._run_recovery(name, recovery)
        # C-8: 记录回滚快照（恢复前状态）
        self._capture_snapshot(name)
        # C-8: 通过策略库执行
        outcome = await self._strategy_registry.execute(name, strategy_name)
        self._recent_recoveries[name] = {
            "strategy": strategy_name,
            "timestamp": time.time(),
            "success": outcome.success,
        }
        if outcome.success:
            # C-8: 仅成功恢复才设置冷却时间戳（失败后允许立即重试其他策略）
            self._recovery_timestamps[name] = time.time()
            self._failure_counts[name] = 0
            verified = await self._verify_recovery(name)
            # C-8: 恢复后若验证失败，标记副作用并尝试回滚
            if not verified:
                self._strategy_registry.mark_side_effect(name, strategy_name)
                await self._rollback(name)
            return {
                "healed": True,
                "method": strategy_name,
                "verified": verified,
            }
        else:
            # C-8: 恢复失败，尝试回滚（不设置冷却，允许下一轮重试）
            await self._rollback(name)
            return {
                "healed": False,
                "method": strategy_name,
                "reason": outcome.reason,
            }

    async def _run_recovery(
        self, name: str, recovery: Callable[[], Any]
    ) -> Dict[str, Any]:
        try:
            self._logger.info(f"[SelfHealing] Recovering module {name}")
            await recovery()
            self._failure_counts[name] = 0
            self._recovery_timestamps[name] = time.time()
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

    # C-8: 回滚快照机制
    def _capture_snapshot(self, module: str) -> None:
        """捕获模块恢复前快照（用于回滚）。"""
        snapshot: Dict[str, Any] = {
            "timestamp": time.time(),
            "failure_count": self._failure_counts.get(module, 0),
            "last_health": dict(self._last_health.get(module, {})),
        }
        snapshots = self._rollback_snapshots.setdefault(module, [])
        snapshots.append(snapshot)
        # 限制快照数量
        if len(snapshots) > _ROLLBACK_SNAPSHOT_LIMIT:
            snapshots.pop(0)

    async def _rollback(self, module: str) -> None:
        """
        回滚：恢复失败后的状态恢复。

        策略：
        - 恢复失败时，将失败计数回退到阈值（_FAILURE_THRESHOLD），
          使下一轮诊断仍可触发恢复，但给予冷却期避免立即重试同一策略。
        - 验证失败（恢复动作成功但健康未恢复）时，标记副作用并保持计数，
          让策略库淘汰该策略后尝试其他策略。
        """
        snapshots = self._rollback_snapshots.get(module, [])
        if not snapshots:
            self._logger.warning(
                f"[SelfHealing] No snapshot to rollback for {module}"
            )
            return
        snapshot = snapshots[-1]
        # 回退失败计数到阈值，避免无限累积同时允许后续重试
        self._failure_counts[module] = _FAILURE_THRESHOLD
        self._logger.info(
            f"[SelfHealing] Rollback for {module}: "
            f"restored failure_count to threshold {_FAILURE_THRESHOLD}"
        )

    def get_recent_recovery(self, module: str) -> Optional[Dict[str, Any]]:
        """获取模块最近一次恢复记录。"""
        return self._recent_recoveries.get(module)

    async def run_diagnosis_loop(self, interval_seconds: float) -> None:
        """持续诊断循环。"""
        self._running = True
        self._logger.info("[SelfHealing] Diagnosis loop started")
        while self._running:
            await asyncio.sleep(interval_seconds)
            if not self._running:
                break
            try:
                # C-8: 先预诊断（轻量恢复），再硬诊断（阈值恢复）
                await self.pre_diagnose()
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
