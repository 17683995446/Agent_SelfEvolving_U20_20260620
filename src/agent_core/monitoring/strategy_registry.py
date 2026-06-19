"""
自愈策略库。

支持多策略注册、命中率跟踪、副作用记录与低效策略淘汰。

第一性原理：
- 生物免疫系统拥有多种应对策略，根据病原特征选择最匹配的方案
- 策略有效性需基于历史数据动态评估，而非静态预设
- 低效策略应被淘汰，避免长期占用恢复窗口造成二次故障
- 策略选择应考虑副作用（恢复动作本身造成的扰动）

设计要点：
- 线程安全：策略统计可能被诊断循环与查询接口并发访问
- 幂等键：同一故障的重复触发在冷却期内只执行一次（由SelfHealingManager保证）
- 副作用评分：恢复后若引发新故障则记录负分，累计超阈值淘汰该策略
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional

from agent_core.common.logger import get_logger

# 策略统计窗口大小（保留最近N次执行记录用于命中率计算）
_STATS_WINDOW = 20
# 副作用累计阈值：超过则淘汰策略
_SIDE_EFFECT_LIMIT = 3
# 策略命中率下限：低于此值且执行次数足够多则降级
_HIT_RATE_FLOOR = 0.3
# 降级前最小执行次数（样本不足时不降级）
_MIN_SAMPLES_FOR_DEMOTE = 5
# 冷却期：同一策略对同一模块的执行间隔（秒）
_COOLDOWN_SECONDS = 2.0


@dataclass
class StrategyOutcome:
    """单次策略执行结果。"""

    success: bool
    timestamp: float
    duration: float
    side_effect: bool = False
    reason: str = ""


@dataclass
class StrategyStats:
    """策略统计信息。"""

    name: str
    total_executions: int = 0
    successes: int = 0
    failures: int = 0
    side_effects: int = 0
    recent: Deque[StrategyOutcome] = field(
        default_factory=lambda: deque(maxlen=_STATS_WINDOW)
    )
    last_executed: float = 0.0
    demoted: bool = False

    @property
    def hit_rate(self) -> float:
        """近期命中率（基于滑动窗口）。"""
        if not self.recent:
            return 0.0
        wins = sum(1 for o in self.recent if o.success)
        return wins / len(self.recent)

    @property
    def avg_duration(self) -> float:
        """近期平均执行耗时。"""
        if not self.recent:
            return 0.0
        return sum(o.duration for o in self.recent) / len(self.recent)

    def record(self, outcome: StrategyOutcome) -> None:
        """记录一次执行结果并更新统计。"""
        self.total_executions += 1
        if outcome.success:
            self.successes += 1
        else:
            self.failures += 1
        if outcome.side_effect:
            self.side_effects += 1
        self.recent.append(outcome)
        self.last_executed = outcome.timestamp
        # 副作用累计超限 → 淘汰
        if self.side_effects >= _SIDE_EFFECT_LIMIT:
            self.demoted = True
        # 命中率过低且样本充足 → 降级
        elif (
            len(self.recent) >= _MIN_SAMPLES_FOR_DEMOTE
            and self.hit_rate < _HIT_RATE_FLOOR
        ):
            self.demoted = True

    def reset_demotion(self) -> None:
        """重置降级状态（用于策略改进后重新启用）。"""
        self.demoted = False
        self.side_effects = 0
        self.recent.clear()


class StrategyRegistry:
    """
    自愈策略库。

    管理多个恢复策略，按模块组织，支持命中率跟踪与淘汰。
    """

    def __init__(self) -> None:
        self._logger = get_logger()
        self._lock = threading.RLock()
        # 结构: {module_name: {strategy_name: StrategyEntry}}
        self._strategies: Dict[str, Dict[str, "_StrategyEntry"]] = {}
        # 冷却记录: {(module, strategy): last_executed_timestamp}
        self._cooldowns: Dict[str, float] = {}

    def register(
        self,
        module: str,
        name: str,
        action: Callable[[], Awaitable[Any]],
        priority: int = 0,
    ) -> None:
        """
        注册策略。

        Args:
            module: 目标模块名。
            name: 策略名（模块内唯一）。
            action: 异步恢复动作，返回任意结果。
            priority: 优先级（数值越大越优先）。
        """
        with self._lock:
            if module not in self._strategies:
                self._strategies[module] = {}
            self._strategies[module][name] = _StrategyEntry(
                name=name,
                action=action,
                priority=priority,
                stats=StrategyStats(name=name),
            )
        self._logger.info(
            f"[StrategyRegistry] Registered strategy '{name}' for module '{module}'"
        )

    def unregister(self, module: str, name: str) -> bool:
        """注销策略。"""
        with self._lock:
            mods = self._strategies.get(module)
            if not mods or name not in mods:
                return False
            del mods[name]
            return True

    def list_strategies(self, module: str) -> List[str]:
        """列出模块的所有策略名。"""
        with self._lock:
            return list(self._strategies.get(module, {}).keys())

    def get_stats(self, module: str, name: str) -> Optional[StrategyStats]:
        """获取策略统计。"""
        with self._lock:
            entry = self._strategies.get(module, {}).get(name)
            return entry.stats if entry else None

    def get_all_stats(self) -> Dict[str, Dict[str, StrategyStats]]:
        """获取所有模块所有策略的统计快照。"""
        with self._lock:
            return {
                mod: {n: e.stats for n, e in entries.items()}
                for mod, entries in self._strategies.items()
            }

    def select(self, module: str) -> Optional[str]:
        """
        为模块选择一个可用策略。

        选择规则：
        1. 过滤掉降级策略
        2. 过滤掉冷却期内的策略
        3. 按优先级降序、命中率降序、最近执行时间升序排序
        4. 返回最优策略名，无可用则返回None
        """
        with self._lock:
            entries = self._strategies.get(module, {})
            now = time.time()
            candidates: List[_StrategyEntry] = []
            for entry in entries.values():
                if entry.stats.demoted:
                    continue
                cooldown_key = f"{module}:{entry.name}"
                last = self._cooldowns.get(cooldown_key, 0.0)
                if now - last < _COOLDOWN_SECONDS:
                    continue
                candidates.append(entry)
            if not candidates:
                return None
            # 排序：优先级降序 → 命中率降序 → 最近执行时间升序（最久未用的优先）
            candidates.sort(
                key=lambda e: (
                    -e.priority,
                    -e.stats.hit_rate,
                    e.stats.last_executed,
                )
            )
            return candidates[0].name

    async def execute(
        self, module: str, name: str
    ) -> StrategyOutcome:
        """
        执行指定策略并记录结果。

        Args:
            module: 模块名。
            name: 策略名。

        Returns:
            执行结果。
        """
        with self._lock:
            entry = self._strategies.get(module, {}).get(name)
            if entry is None:
                return StrategyOutcome(
                    success=False,
                    timestamp=time.time(),
                    duration=0.0,
                    side_effect=False,
                    reason="strategy_not_found",
                )
            action = entry.action
            self._cooldowns[f"{module}:{name}"] = time.time()

        start = time.time()
        try:
            await action()
            outcome = StrategyOutcome(
                success=True,
                timestamp=start,
                duration=time.time() - start,
                side_effect=False,
                reason="ok",
            )
        except Exception as exc:
            outcome = StrategyOutcome(
                success=False,
                timestamp=start,
                duration=time.time() - start,
                side_effect=False,
                reason=str(exc),
            )
            self._logger.error(
                f"[StrategyRegistry] Strategy '{name}' for '{module}' failed: {exc}"
            )

        with self._lock:
            entry.stats.record(outcome)
        return outcome

    def mark_side_effect(self, module: str, name: str) -> None:
        """
        标记策略产生了副作用（恢复后引发新故障）。

        调用方在恢复后发现新故障时调用此方法。
        """
        with self._lock:
            entry = self._strategies.get(module, {}).get(name)
            if entry is None:
                return
            entry.stats.side_effects += 1
            if entry.stats.side_effects >= _SIDE_EFFECT_LIMIT:
                entry.stats.demoted = True
                self._logger.warning(
                    f"[StrategyRegistry] Strategy '{name}' for '{module}' "
                    f"demoted due to side effects"
                )

    def reset_demotion(self, module: str, name: str) -> bool:
        """重置策略降级状态。"""
        with self._lock:
            entry = self._strategies.get(module, {}).get(name)
            if entry is None:
                return False
            entry.stats.reset_demotion()
            return True

    def clear_cooldowns(self) -> None:
        """清除所有冷却记录（测试辅助）。"""
        with self._lock:
            self._cooldowns.clear()


@dataclass
class _StrategyEntry:
    """策略条目（内部）。"""

    name: str
    action: Callable[[], Awaitable[Any]]
    priority: int
    stats: StrategyStats
