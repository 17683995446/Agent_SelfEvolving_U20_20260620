"""
奖励计算器与策略库

第一性原理：生物体的学习基于"行动→结果→强化/抑制"的闭环。
多巴胺系统根据"结果与预期的差异"（reward prediction error）调整未来行为倾向。
- RewardComputer: 把执行结果（成功/失败 + 指标改善幅度）转化为 reward 信号
- StrategyLibrary: 记录"故障类型→修复动作→效果"映射，下次同类故障优先用有效策略

设计原则：
- reward 范围 [-1, 1]，正数=强化（继续用此策略），负数=抑制（避免此策略）
- 策略库按"故障类型+动作"聚合统计成功率，用 UCB 思想平衡探索与利用
- 纯内存实现（阶段5可升级为持久化）
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from core import STATE_IDX_CPU_OVERALL, STATE_IDX_MEM_USED, STATE_IDX_DISK_USED


@dataclass
class MetricsSnapshot:
    """系统指标快照（执行前/后）"""
    cpu_percent: float = 0.0   # 0-100
    mem_percent: float = 0.0
    disk_percent: float = 0.0

    @classmethod
    def from_state_vector(cls, state_vector: Optional[np.ndarray]) -> "MetricsSnapshot":
        if state_vector is None:
            return cls()
        try:
            return cls(
                cpu_percent=float(state_vector[STATE_IDX_CPU_OVERALL]) * 100,
                mem_percent=float(state_vector[STATE_IDX_MEM_USED]) * 100,
                disk_percent=float(state_vector[STATE_IDX_DISK_USED]) * 100,
            )
        except (IndexError, TypeError):
            return cls()

    def delta(self, other: "MetricsSnapshot") -> Dict[str, float]:
        """
        计算 other 相对 self 的改善量（正数=指标下降=改善）

        例如 before.delta(after)：CPU从90降到60，返回 cpu_delta=30（正=改善）
        """
        return {
            "cpu_delta": self.cpu_percent - other.cpu_percent,   # 正=CPU下降=改善
            "mem_delta": self.mem_percent - other.mem_percent,
            "disk_delta": self.disk_percent - other.disk_percent,
        }


class RewardComputer:
    """
    奖励计算器

    把执行结果转化为 reward 信号。

    reward 组成（范围 [-1, 1]）：
    1. 执行成功/失败基础分：success=+0.3, failure=-0.3
    2. 指标改善分：CPU/内存/磁盘下降越多分越高（每项最多±0.2）
    3. 安全执行加分：真实执行（非dry_run）成功额外+0.1
    4. 惩罚：执行失败且有副作用 -0.2

    公式：
        reward = base + improvement + safety_bonus - failure_penalty
    """

    def __init__(self,
                 success_base: float = 0.3,
                 failure_base: float = -0.3,
                 improvement_weight: float = 0.2,
                 real_execution_bonus: float = 0.1,
                 failure_penalty: float = 0.2):
        self.success_base = success_base
        self.failure_base = failure_base
        self.improvement_weight = improvement_weight
        self.real_execution_bonus = real_execution_bonus
        self.failure_penalty = failure_penalty

    def compute(self,
                success: bool,
                executed: bool,
                before: MetricsSnapshot,
                after: MetricsSnapshot,
                task_action: str = "") -> float:
        """
        计算 reward

        Args:
            success: 执行是否成功
            executed: 是否真实执行（非dry_run/log_only）
            before: 执行前指标快照
            after: 执行后指标快照
            task_action: 任务动作（用于日志）

        Returns:
            reward in [-1, 1]
        """
        # 1. 基础分
        reward = self.success_base if success else self.failure_base

        # 2. 指标改善分（仅真实执行时计算，dry_run无指标变化）
        if executed and success:
            delta = before.delta(after)
            # 每项改善（指标下降）给正分，恶化给负分
            for key in ["cpu_delta", "mem_delta", "disk_delta"]:
                d = delta[key]
                # 改善幅度归一化到 [-1, 1]，10%变化=满分
                normalized = max(-1.0, min(1.0, d / 10.0))
                reward += normalized * self.improvement_weight

        # 3. 真实执行加分
        if executed and success:
            reward += self.real_execution_bonus

        # 4. 失败惩罚
        if not success and executed:
            reward -= self.failure_penalty

        # 裁剪到 [-1, 1]
        reward = max(-1.0, min(1.0, reward))

        print(f"  [RewardComputer] action={task_action} success={success} executed={executed} "
              f"reward={reward:.3f} (before cpu={before.cpu_percent:.1f} after cpu={after.cpu_percent:.1f})")
        return reward


@dataclass
class StrategyRecord:
    """策略记录：某个 (故障类型, 动作) 的历史表现"""
    fault_type: str          # 故障类型（cpu_critical/mem_critical/disk_critical/normal）
    action: str              # 执行的动作（reduce_cpu_load/free_memory/...）
    total_attempts: int = 0
    success_count: int = 0
    total_reward: float = 0.0
    avg_reward: float = 0.0
    last_used: float = 0.0
    last_success: Optional[bool] = None

    def update(self, success: bool, reward: float):
        self.total_attempts += 1
        if success:
            self.success_count += 1
        self.total_reward += reward
        self.avg_reward = self.total_reward / self.total_attempts
        self.last_used = time.time()
        self.last_success = success


class StrategyLibrary:
    """
    策略库

    记录"故障类型→动作→效果"映射，用 UCB 平衡探索与利用。

    第一性原理：免疫系统会"记住"有效抗体，下次遇到相同病原体优先使用。
    但也会保留多样性以应对新病原体（探索）。

    UCB 公式：score = avg_reward + c * sqrt(ln(N_total) / n_action)
    - avg_reward: 该动作的平均奖励（利用）
    - c * sqrt(...): 探索项，尝试次数少的动作有更高探索分
    """

    def __init__(self, exploration_constant: float = 1.0):
        self.c = exploration_constant  # 探索常数
        self._records: Dict[Tuple[str, str], StrategyRecord] = {}
        self._total_attempts = 0

    def classify_fault(self, metrics: MetricsSnapshot) -> str:
        """根据指标分类故障类型"""
        if metrics.cpu_percent > 90:
            return "cpu_critical"
        if metrics.mem_percent > 90:
            return "mem_critical"
        if metrics.disk_percent > 95:
            return "disk_critical"
        if metrics.cpu_percent > 70 or metrics.mem_percent > 80:
            return "resource_high"
        return "normal"

    def record(self, fault_type: str, action: str, success: bool, reward: float):
        """记录一次执行结果"""
        key = (fault_type, action)
        if key not in self._records:
            self._records[key] = StrategyRecord(fault_type=fault_type, action=action)
        self._records[key].update(success, reward)
        self._total_attempts += 1
        print(f"  [StrategyLibrary] record fault={fault_type} action={action} "
              f"success={success} reward={reward:.3f} "
              f"(attempts={self._records[key].total_attempts} "
              f"avg_reward={self._records[key].avg_reward:.3f})")

    def recommend(self, fault_type: str, candidate_actions: List[str]) -> Optional[str]:
        """
        用 UCB 推荐最优动作

        Args:
            fault_type: 故障类型
            candidate_actions: 候选动作列表

        Returns:
            推荐的动作，或 None（无候选）
        """
        if not candidate_actions:
            return None

        if self._total_attempts == 0:
            # 无历史数据，随机选一个（纯探索）
            return candidate_actions[0]

        best_action = None
        best_score = -float("inf")
        log_total = math.log(max(self._total_attempts, 1))

        for action in candidate_actions:
            key = (fault_type, action)
            record = self._records.get(key)
            if record is None or record.total_attempts == 0:
                # 未尝试过的动作，给最高探索分
                score = float("inf")
            else:
                # UCB: 利用 + 探索
                exploit = record.avg_reward
                explore = self.c * math.sqrt(log_total / record.total_attempts)
                score = exploit + explore

            if score > best_score:
                best_score = score
                best_action = action

        print(f"  [StrategyLibrary] recommend fault={fault_type} "
              f"candidates={candidate_actions} -> {best_action} (score={best_score:.3f})")
        return best_action

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_strategies": len(self._records),
            "total_attempts": self._total_attempts,
            "by_fault_type": self._stats_by_fault(),
            "top_strategies": self._top_strategies(5),
        }

    def _stats_by_fault(self) -> Dict[str, int]:
        counts: Dict[str, int] = defaultdict(int)
        for (fault, _), rec in self._records.items():
            counts[fault] += rec.total_attempts
        return dict(counts)

    def _top_strategies(self, n: int) -> List[Dict[str, Any]]:
        sorted_recs = sorted(
            self._records.values(),
            key=lambda r: r.avg_reward,
            reverse=True
        )[:n]
        return [
            {
                "fault_type": r.fault_type,
                "action": r.action,
                "attempts": r.total_attempts,
                "success_rate": r.success_count / r.total_attempts if r.total_attempts > 0 else 0,
                "avg_reward": r.avg_reward,
            }
            for r in sorted_recs
        ]
