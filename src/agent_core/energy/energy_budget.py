"""
能量预算管理器。

按优先级为模块分配能量预算，实现资源感知的任务调度。

第一性原理：
- 生物代谢系统按器官优先级分配能量：大脑和心脏优先，消化系统次之
- 能量是有限资源，必须按优先级分配
- 活跃模块消耗更多能量，空闲模块消耗少
- 能量耗尽时降级而非崩溃（如生物进入低代谢状态）

设计要点：
- 每模块独立能量账户，按优先级分配预算
- 任务消耗能量，预算按时间补充
- 低预算时拒绝非关键任务
- 线程安全
"""

import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, List, Optional

from agent_core.common.logger import get_logger

# 默认能量补充速率（单位/秒）
_DEFAULT_REPLENISH_RATE = 10.0
# 默认最大预算容量
_DEFAULT_MAX_BUDGET = 100.0
# 低预算阈值（低于此值时降级）
_LOW_BUDGET_THRESHOLD = 20.0
# 清理周期（秒）
_CLEANUP_INTERVAL = 60.0
# 账户过期时间（秒）
_ACCOUNT_TTL = 600.0


class ModulePriority(IntEnum):
    """模块优先级。"""

    CRITICAL = 0  # 关键（感知、自愈）
    HIGH = 1  # 高（预测、决策）
    NORMAL = 2  # 普通（记忆、学习）
    LOW = 3  # 低（文档、测试生成）


# 优先级到预算配额的映射
_PRIORITY_QUOTA: Dict[ModulePriority, float] = {
    ModulePriority.CRITICAL: 1.0,  # 100% 预算
    ModulePriority.HIGH: 0.7,  # 70%
    ModulePriority.NORMAL: 0.5,  # 50%
    ModulePriority.LOW: 0.3,  # 30%
}

# 优先级到补充速率倍率的映射
_PRIORITY_REPLENISH: Dict[ModulePriority, float] = {
    ModulePriority.CRITICAL: 1.5,  # 更快补充
    ModulePriority.HIGH: 1.0,
    ModulePriority.NORMAL: 0.8,
    ModulePriority.LOW: 0.5,  # 更慢补充
}


@dataclass
class BudgetResult:
    """预算检查结果。"""

    allowed: bool
    remaining: float
    max_budget: float
    degraded: bool


@dataclass
class _EnergyAccount:
    """能量账户。"""

    module_name: str
    priority: ModulePriority
    budget: float
    max_budget: float
    replenish_rate: float
    last_refill: float
    last_access: float
    total_consumed: float = 0.0
    total_replenished: float = 0.0


class EnergyBudgetManager:
    """
    能量预算管理器。

    按优先级为模块分配和管理能量预算。
    """

    def __init__(
        self,
        base_replenish_rate: float = _DEFAULT_REPLENISH_RATE,
        base_max_budget: float = _DEFAULT_MAX_BUDGET,
    ) -> None:
        if base_replenish_rate <= 0:
            raise ValueError("base_replenish_rate must be positive")
        if base_max_budget <= 0:
            raise ValueError("base_max_budget must be positive")
        self._base_rate = base_replenish_rate
        self._base_max = base_max_budget
        self._logger = get_logger()
        self._lock = threading.RLock()  # 可重入锁：consume调用register_module
        self._accounts: Dict[str, _EnergyAccount] = {}
        self._last_cleanup = time.monotonic()

    def register_module(
        self,
        module_name: str,
        priority: ModulePriority = ModulePriority.NORMAL,
    ) -> None:
        """注册模块并分配初始预算。"""
        with self._lock:
            if module_name in self._accounts:
                return
            quota = _PRIORITY_QUOTA[priority]
            max_budget = self._base_max * quota
            replenish = self._base_rate * _PRIORITY_REPLENISH[priority]
            now = time.monotonic()
            self._accounts[module_name] = _EnergyAccount(
                module_name=module_name,
                priority=priority,
                budget=max_budget,
                max_budget=max_budget,
                replenish_rate=replenish,
                last_refill=now,
                last_access=now,
            )
            self._logger.info(
                f"[EnergyBudget] Registered '{module_name}' "
                f"priority={priority.name} max={max_budget:.1f}"
            )

    def unregister_module(self, module_name: str) -> None:
        """注销模块。"""
        with self._lock:
            self._accounts.pop(module_name, None)

    def consume(
        self, module_name: str, cost: float = 1.0
    ) -> BudgetResult:
        """
        消耗模块能量预算。

        Args:
            module_name: 模块名。
            cost: 消耗量。

        Returns:
            预算结果。
        """
        now = time.monotonic()
        with self._lock:
            self._maybe_cleanup(now)
            account = self._accounts.get(module_name)
            if account is None:
                # 未注册模块默认低优先级
                self.register_module(module_name, ModulePriority.LOW)
                account = self._accounts[module_name]

            self._refill(account, now)
            account.last_access = now

            if account.budget >= cost:
                account.budget -= cost
                account.total_consumed += cost
                degraded = account.budget < _LOW_BUDGET_THRESHOLD
                return BudgetResult(
                    allowed=True,
                    remaining=account.budget,
                    max_budget=account.max_budget,
                    degraded=degraded,
                )

            # 预算不足
            deficit = cost - account.budget
            # 关键模块允许透支（生物体在紧急时透支能量）
            if account.priority == ModulePriority.CRITICAL:
                account.budget = 0.0
                account.total_consumed += account.budget
                return BudgetResult(
                    allowed=True,
                    remaining=0.0,
                    max_budget=account.max_budget,
                    degraded=True,
                )

            return BudgetResult(
                allowed=False,
                remaining=account.budget,
                max_budget=account.max_budget,
                degraded=True,
            )

    def allow(self, module_name: str, cost: float = 1.0) -> bool:
        """便捷方法：仅返回是否允许。"""
        return self.consume(module_name, cost).allowed

    def get_budget(self, module_name: str) -> Optional[float]:
        """获取模块当前预算。"""
        with self._lock:
            account = self._accounts.get(module_name)
            if account is None:
                return None
            self._refill(account, time.monotonic())
            return account.budget

    def get_stats(self, module_name: str) -> Optional[Dict[str, float]]:
        """获取模块统计信息。"""
        with self._lock:
            account = self._accounts.get(module_name)
            if account is None:
                return None
            self._refill(account, time.monotonic())
            return {
                "budget": account.budget,
                "max_budget": account.max_budget,
                "priority": account.priority.name,
                "replenish_rate": account.replenish_rate,
                "total_consumed": account.total_consumed,
                "total_replenished": account.total_replenished,
            }

    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """获取所有模块统计。"""
        with self._lock:
            now = time.monotonic()
            result = {}
            for name, account in self._accounts.items():
                self._refill(account, now)
                result[name] = {
                    "budget": account.budget,
                    "max_budget": account.max_budget,
                    "priority": account.priority.name,
                    "total_consumed": account.total_consumed,
                }
            return result

    def set_priority(
        self, module_name: str, priority: ModulePriority
    ) -> None:
        """动态调整模块优先级。"""
        with self._lock:
            account = self._accounts.get(module_name)
            if account is None:
                return
            account.priority = priority
            quota = _PRIORITY_QUOTA[priority]
            account.max_budget = self._base_max * quota
            account.replenish_rate = (
                self._base_rate * _PRIORITY_REPLENISH[priority]
            )
            account.budget = min(account.budget, account.max_budget)

    def reset(self) -> None:
        """重置所有账户。"""
        with self._lock:
            self._accounts.clear()

    def _refill(self, account: _EnergyAccount, now: float) -> None:
        """补充能量。"""
        elapsed = now - account.last_refill
        if elapsed <= 0:
            return
        replenished = elapsed * account.replenish_rate
        account.budget = min(
            account.max_budget, account.budget + replenished
        )
        account.total_replenished += replenished
        account.last_refill = now

    def _maybe_cleanup(self, now: float) -> None:
        """清理过期账户。"""
        if now - self._last_cleanup < _CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        expired = [
            name
            for name, acc in self._accounts.items()
            if now - acc.last_access > _ACCOUNT_TTL
        ]
        for name in expired:
            del self._accounts[name]
        if expired:
            self._logger.info(
                f"[EnergyBudget] Cleaned up {len(expired)} expired accounts"
            )
