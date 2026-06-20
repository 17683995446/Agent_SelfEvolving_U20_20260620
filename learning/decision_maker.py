"""
智能决策器

第一性原理：生物决策不是纯反射（规则），而是"反射+学习+预测"的融合。
- 反射：规则阈值快速响应已知危险（auto_healing 已实现）
- 学习：从历史经验中学习"什么动作对什么故障有效"（StrategyLibrary 已实现）
- 预测：预测"若执行动作A，未来指标如何变化"，选最优动作

IntelligentDecisionMaker 整合三者：
1. 收集候选动作（规则生成 + 策略库推荐）
2. 用预测器评估每个候选动作的预期效果
3. 用 UCB 平衡探索与利用
4. 输出可解释的决策理由链
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from learning import StrategyLibrary, MetricsSnapshot


@dataclass
class DecisionCandidate:
    """决策候选"""
    action: str                    # 动作名
    source: str                    # 来源：rule/strategy_library/prediction
    expected_reward: float = 0.0   # 预期奖励
    confidence: float = 0.0        # 置信度
    reason: str = ""               # 选择理由


@dataclass
class Decision:
    """决策结果"""
    chosen_action: str
    candidates: List[DecisionCandidate] = field(default_factory=list)
    reason_chain: List[str] = field(default_factory=list)  # 可解释理由链
    timestamp: float = field(default_factory=lambda: time.time())
    exploration: bool = False  # 是否为探索性选择


class IntelligentDecisionMaker:
    """
    智能决策器

    融合规则+学习+预测的决策机制。

    决策流程：
        1. 故障分类（基于当前指标）
        2. 收集候选动作（规则生成 + 策略库已知动作）
        3. 对每个候选评估预期奖励（策略库 avg_reward）
        4. UCB 平衡探索与利用
        5. 输出决策 + 理由链
    """

    # 故障类型 → 候选动作映射（规则生成的候选）
    FAULT_ACTION_CANDIDATES = {
        "cpu_critical": ["reduce_cpu_load", "optimize_resources"],
        "mem_critical": ["free_memory", "optimize_resources"],
        "disk_critical": ["free_disk_space"],
        "resource_high": ["optimize_resources"],
        "normal": ["increase_sampling_rate"],
    }

    def __init__(self,
                 strategy_library: Optional[StrategyLibrary] = None,
                 exploration_constant: float = 1.0,
                 min_confidence_threshold: float = 0.3,
                 max_history_size: int = 500):
        """
        Args:
            strategy_library: 策略库（历史经验）
            exploration_constant: UCB 探索常数
            min_confidence_threshold: 最低置信度阈值（低于此值触发探索）
            max_history_size: 决策历史最大条数（阶段7：防止长期运行内存泄漏）
        """
        self.strategy_library = strategy_library or StrategyLibrary(exploration_constant)
        self.exploration_constant = exploration_constant
        self.min_confidence_threshold = min_confidence_threshold
        self.max_history_size = max_history_size
        self._decision_history: List[Decision] = []
        # 全局计数器（不受历史裁剪影响）
        self._total_decisions = 0
        self._total_exploration = 0

    def decide(self, metrics: MetricsSnapshot) -> Decision:
        """
        智能决策

        Args:
            metrics: 当前系统指标快照

        Returns:
            Decision: 含选择动作 + 理由链
        """
        reason_chain = []

        # 1. 故障分类
        fault_type = self.strategy_library.classify_fault(metrics)
        reason_chain.append(f"故障分类: {fault_type} (cpu={metrics.cpu_percent:.1f}% "
                            f"mem={metrics.mem_percent:.1f}% disk={metrics.disk_percent:.1f}%)")

        # 2. 收集候选动作
        candidates = self._collect_candidates(fault_type, metrics)
        reason_chain.append(f"候选动作: {[c.action for c in candidates]}")

        if not candidates:
            reason_chain.append("无候选动作，选择默认 increase_sampling_rate")
            decision = Decision(
                chosen_action="increase_sampling_rate",
                candidates=candidates,
                reason_chain=reason_chain,
                exploration=False,
            )
            self._record_decision(decision)
            return decision

        # 3. 评估每个候选（用策略库历史数据）
        for candidate in candidates:
            record = self.strategy_library._records.get(
                (fault_type, candidate.action)
            )
            if record and record.total_attempts > 0:
                candidate.expected_reward = record.avg_reward
                candidate.confidence = min(1.0, record.total_attempts / 10.0)
                candidate.reason = (
                    f"历史 {record.total_attempts} 次, avg_reward={record.avg_reward:.3f}, "
                    f"成功率={record.success_count/record.total_attempts:.1%}"
                )
            else:
                candidate.expected_reward = 0.0
                candidate.confidence = 0.0
                candidate.reason = "无历史数据（探索候选）"

        # 4. UCB 选择
        chosen, exploration = self._ucb_select(fault_type, candidates)
        reason_chain.append(
            f"UCB选择: {chosen.action} "
            f"(expected_reward={chosen.expected_reward:.3f}, "
            f"confidence={chosen.confidence:.2f}, "
            f"exploration={exploration})"
        )
        reason_chain.append(f"理由: {chosen.reason}")

        print(f"  [DecisionMaker] decide fault={fault_type} -> {chosen.action} "
              f"(reward={chosen.expected_reward:.3f} conf={chosen.confidence:.2f} "
              f"explore={exploration})")

        decision = Decision(
            chosen_action=chosen.action,
            candidates=candidates,
            reason_chain=reason_chain,
            exploration=exploration,
        )
        self._record_decision(decision)
        return decision

    def _record_decision(self, decision: Decision) -> None:
        """记录决策（阶段7：含全局计数+有界裁剪）"""
        self._total_decisions += 1
        if decision.exploration:
            self._total_exploration += 1
        self._decision_history.append(decision)
        if len(self._decision_history) > self.max_history_size:
            self._decision_history = self._decision_history[-self.max_history_size:]

    def _collect_candidates(self, fault_type: str, metrics: MetricsSnapshot) -> List[DecisionCandidate]:
        """收集候选动作（规则生成 + 策略库已知）"""
        candidates = []
        seen_actions = set()

        # 规则生成的候选
        rule_actions = self.FAULT_ACTION_CANDIDATES.get(fault_type, [])
        for action in rule_actions:
            if action not in seen_actions:
                candidates.append(DecisionCandidate(
                    action=action, source="rule",
                    reason=f"规则推荐: {fault_type} -> {action}",
                ))
                seen_actions.add(action)

        # 策略库中该故障类型的已知动作
        for (ft, act), record in self.strategy_library._records.items():
            if ft == fault_type and act not in seen_actions:
                candidates.append(DecisionCandidate(
                    action=act, source="strategy_library",
                    expected_reward=record.avg_reward,
                    confidence=min(1.0, record.total_attempts / 10.0),
                    reason=f"策略库: {record.total_attempts} 次, avg={record.avg_reward:.3f}",
                ))
                seen_actions.add(act)

        return candidates

    def _ucb_select(self, fault_type: str,
                    candidates: List[DecisionCandidate]) -> Tuple[DecisionCandidate, bool]:
        """
        UCB 选择

        Returns:
            (chosen_candidate, is_exploration)
        """
        import math

        total_attempts = sum(
            self.strategy_library._records.get((fault_type, c.action)).total_attempts
            for c in candidates
            if self.strategy_library._records.get((fault_type, c.action))
        )

        if total_attempts == 0:
            # 全新故障，选第一个候选（纯探索）
            return candidates[0], True

        log_total = math.log(max(total_attempts, 1))
        best = None
        best_score = -float("inf")
        is_exploration = False

        for candidate in candidates:
            record = self.strategy_library._records.get((fault_type, candidate.action))
            if record is None or record.total_attempts == 0:
                # 未尝试过的动作，最高探索分
                score = float("inf")
                exploit = 0
                explore = float("inf")
                is_exploration = True
            else:
                exploit = record.avg_reward
                explore = self.exploration_constant * math.sqrt(log_total / record.total_attempts)
                score = exploit + explore

            if score > best_score:
                best_score = score
                best = candidate
                # 如果探索分占主导，标记为探索
                if record and record.total_attempts > 0:
                    is_exploration = (explore > exploit and explore > 0.5)

        return best, is_exploration

    def get_decision_history(self, limit: int = 20) -> List[Decision]:
        """获取决策历史"""
        return self._decision_history[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        total = self._total_decisions
        exploration_count = self._total_exploration
        return {
            "total_decisions": total,
            "exploration_count": exploration_count,
            "exploitation_count": total - exploration_count,
            "exploration_rate": exploration_count / total if total > 0 else 0.0,
            "history_size": len(self._decision_history),
            "strategy_stats": self.strategy_library.get_stats(),
        }
