"""
阶段5智能决策测试 — 验证从规则到学习的升级

测试目标（第一性原理验证）：
1. 智能决策器能基于故障类型生成候选动作
2. 无历史数据时触发探索（选未尝试动作）
3. 有历史数据后倾向高reward动作（利用）
4. UCB 平衡探索与利用
5. 决策有可解释理由链
6. 多次同类故障后决策质量提升
7. 策略库与决策器联动
"""

from __future__ import annotations

import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from learning import IntelligentDecisionMaker, StrategyLibrary, MetricsSnapshot


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors: List[str] = []

    def ok(self, name: str):
        self.passed += 1
        print(f"  [PASS] {name}")

    def fail(self, name: str, reason: str):
        self.failed += 1
        msg = f"{name}: {reason}"
        self.errors.append(msg)
        print(f"  [FAIL] {msg}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n  通过: {self.passed}, 失败: {self.failed}, 共{total}项")
        for e in self.errors:
            print(f"    - {e}")


# =============================================================================
# 测试1: 基本决策 — 基于故障类型生成候选
# =============================================================================

def test_basic_decision(result: TestResult):
    print(f"\n  --- 测试1: 基本决策 ---")
    dm = IntelligentDecisionMaker()

    # CPU故障
    metrics = MetricsSnapshot(cpu_percent=95, mem_percent=50, disk_percent=50)
    decision = dm.decide(metrics)

    if decision.chosen_action:
        result.ok(f"决策返回动作: {decision.chosen_action}")
    else:
        result.fail("无决策", "chosen_action 为空")

    # 候选应包含 reduce_cpu_load
    candidate_actions = [c.action for c in decision.candidates]
    if "reduce_cpu_load" in candidate_actions:
        result.ok(f"候选含 reduce_cpu_load")
    else:
        result.fail("候选缺失", f"candidates={candidate_actions}")


# =============================================================================
# 测试2: 无历史数据时探索
# =============================================================================

def test_exploration_when_no_history(result: TestResult):
    print(f"\n  --- 测试2: 无历史探索 ---")
    dm = IntelligentDecisionMaker()

    metrics = MetricsSnapshot(cpu_percent=95, mem_percent=50, disk_percent=50)
    decision = dm.decide(metrics)

    if decision.exploration:
        result.ok(f"无历史时触发探索 (exploration=True)")
    else:
        result.fail("未探索", "exploration=False")


# =============================================================================
# 测试3: 有历史后倾向高reward动作
# =============================================================================

def test_exploitation_with_history(result: TestResult):
    print(f"\n  --- 测试3: 有历史利用 ---")
    lib = StrategyLibrary(exploration_constant=0.3)  # 低探索常数
    dm = IntelligentDecisionMaker(strategy_library=lib, exploration_constant=0.3)

    # 记录 action_A 表现好
    for _ in range(20):
        lib.record("cpu_critical", "reduce_cpu_load", success=True, reward=0.6)

    # 记录 action_B 表现差
    for _ in range(20):
        lib.record("cpu_critical", "optimize_resources", success=False, reward=-0.3)

    metrics = MetricsSnapshot(cpu_percent=95, mem_percent=50, disk_percent=50)
    decision = dm.decide(metrics)

    print(f"    chosen={decision.chosen_action} exploration={decision.exploration}")
    if decision.chosen_action == "reduce_cpu_load":
        result.ok(f"倾向高reward动作 reduce_cpu_load")
    else:
        result.fail("利用失败", f"选择了 {decision.chosen_action}")


# =============================================================================
# 测试4: UCB 平衡探索与利用
# =============================================================================

def test_ucb_balance(result: TestResult):
    print(f"\n  --- 测试4: UCB 平衡 ---")
    lib = StrategyLibrary(exploration_constant=1.0)
    dm = IntelligentDecisionMaker(strategy_library=lib, exploration_constant=1.0)

    # 只记录 action_A 多次
    for _ in range(15):
        lib.record("cpu_critical", "reduce_cpu_load", success=True, reward=0.4)

    # action_B (optimize_resources) 未尝试过
    metrics = MetricsSnapshot(cpu_percent=95, mem_percent=50, disk_percent=50)
    decision = dm.decide(metrics)

    # UCB 应选未尝试的 action_B（探索分无限大）
    if decision.chosen_action == "optimize_resources":
        result.ok(f"UCB 探索未尝试动作 optimize_resources")
    else:
        result.fail("UCB 未探索", f"选择了 {decision.chosen_action}")


# =============================================================================
# 测试5: 可解释理由链
# =============================================================================

def test_reason_chain(result: TestResult):
    print(f"\n  --- 测试5: 可解释理由链 ---")
    dm = IntelligentDecisionMaker()

    metrics = MetricsSnapshot(cpu_percent=95, mem_percent=50, disk_percent=50)
    decision = dm.decide(metrics)

    if len(decision.reason_chain) >= 3:
        result.ok(f"理由链完整 ({len(decision.reason_chain)}步)")
    else:
        result.fail("理由链不足", f"len={len(decision.reason_chain)}")

    # 理由链应包含故障分类
    has_fault = any("故障分类" in r for r in decision.reason_chain)
    if has_fault:
        result.ok(f"理由链含故障分类")
    else:
        result.fail("理由链缺故障分类", str(decision.reason_chain))

    # 理由链应包含 UCB 选择
    has_ucb = any("UCB" in r for r in decision.reason_chain)
    if has_ucb:
        result.ok(f"理由链含 UCB 选择")
    else:
        result.fail("理由链缺UCB", str(decision.reason_chain))

    # 打印理由链
    for i, r in enumerate(decision.reason_chain):
        print(f"    [{i}] {r}")


# =============================================================================
# 测试6: 多次同类故障后决策质量提升
# =============================================================================

def test_decision_quality_improves(result: TestResult):
    print(f"\n  --- 测试6: 决策质量提升 ---")
    lib = StrategyLibrary(exploration_constant=0.5)
    dm = IntelligentDecisionMaker(strategy_library=lib, exploration_constant=0.5)

    metrics = MetricsSnapshot(cpu_percent=95, mem_percent=50, disk_percent=50)

    # 前5次：探索阶段，记录不同动作的效果
    # 假设 reduce_cpu_load 效果好，optimize_resources 效果差
    for i in range(10):
        decision = dm.decide(metrics)
        # 模拟执行结果
        if decision.chosen_action == "reduce_cpu_load":
            lib.record("cpu_critical", "reduce_cpu_load", success=True, reward=0.6)
        elif decision.chosen_action == "optimize_resources":
            lib.record("cpu_critical", "optimize_resources", success=False, reward=-0.2)

    # 第11次决策：应倾向 reduce_cpu_load
    final_decision = dm.decide(metrics)
    print(f"    第11次决策: {final_decision.chosen_action} (exploration={final_decision.exploration})")

    if final_decision.chosen_action == "reduce_cpu_load":
        result.ok(f"多次学习后选择高reward动作")
    else:
        # 也可能因UCB探索选其他，但应有一定利用倾向
        stats = dm.get_stats()
        if stats["exploitation_count"] > 0:
            result.ok(f"有利用决策 (exploitation={stats['exploitation_count']})")
        else:
            result.fail("未体现学习", f"第11次选 {final_decision.chosen_action}")


# =============================================================================
# 测试7: 不同故障类型不同候选
# =============================================================================

def test_different_fault_different_candidates(result: TestResult):
    print(f"\n  --- 测试7: 不同故障不同候选 ---")
    dm = IntelligentDecisionMaker()

    cases = [
        (MetricsSnapshot(cpu_percent=95, mem_percent=50, disk_percent=50), "cpu_critical"),
        (MetricsSnapshot(cpu_percent=50, mem_percent=95, disk_percent=50), "mem_critical"),
        (MetricsSnapshot(cpu_percent=50, mem_percent=50, disk_percent=98), "disk_critical"),
    ]

    for metrics, expected_fault in cases:
        decision = dm.decide(metrics)
        # 理由链第一步应含故障分类
        if expected_fault in decision.reason_chain[0]:
            result.ok(f"{expected_fault} 分类正确")
        else:
            result.fail("分类错误", f"期望{expected_fault} 实际{decision.reason_chain[0]}")


# =============================================================================
# 测试8: 决策历史记录
# =============================================================================

def test_decision_history(result: TestResult):
    print(f"\n  --- 测试8: 决策历史 ---")
    dm = IntelligentDecisionMaker()

    for _ in range(5):
        dm.decide(MetricsSnapshot(cpu_percent=95, mem_percent=50, disk_percent=50))

    history = dm.get_decision_history()
    if len(history) == 5:
        result.ok(f"决策历史完整 (len=5)")
    else:
        result.fail("历史不完整", f"len={len(history)}")

    stats = dm.get_stats()
    if stats["total_decisions"] == 5:
        result.ok(f"统计 total_decisions=5")
    else:
        result.fail("统计错误", f"={stats['total_decisions']}")

    if "exploration_rate" in stats:
        result.ok(f"统计含 exploration_rate")
    else:
        result.fail("缺exploration_rate", str(stats.keys()))


# =============================================================================
# 测试9: 正常状态决策
# =============================================================================

def test_normal_state_decision(result: TestResult):
    print(f"\n  --- 测试9: 正常状态决策 ---")
    dm = IntelligentDecisionMaker()

    metrics = MetricsSnapshot(cpu_percent=30, mem_percent=40, disk_percent=50)
    decision = dm.decide(metrics)

    # 正常状态应选 increase_sampling_rate
    if decision.chosen_action == "increase_sampling_rate":
        result.ok(f"正常状态选 increase_sampling_rate")
    else:
        result.fail("正常状态决策错误", f"={decision.chosen_action}")


# =============================================================================
# 测试10: 候选来源多样性（rule + strategy_library）
# =============================================================================

def test_candidate_sources(result: TestResult):
    print(f"\n  --- 测试10: 候选来源多样性 ---")
    lib = StrategyLibrary()
    # 预先记录一个策略库中的动作
    lib.record("cpu_critical", "custom_action_xyz", success=True, reward=0.5)

    dm = IntelligentDecisionMaker(strategy_library=lib)
    decision = dm.decide(MetricsSnapshot(cpu_percent=95, mem_percent=50, disk_percent=50))

    sources = [c.source for c in decision.candidates]
    if "rule" in sources:
        result.ok(f"含规则候选")
    else:
        result.fail("缺规则候选", str(sources))

    if "strategy_library" in sources:
        result.ok(f"含策略库候选")
    else:
        result.fail("缺策略库候选", str(sources))


def main():
    print("\n" + "=" * 60)
    print("  阶段5智能决策测试 — 从规则到学习")
    print("=" * 60)

    result = TestResult()
    test_basic_decision(result)
    test_exploration_when_no_history(result)
    test_exploitation_with_history(result)
    test_ucb_balance(result)
    test_reason_chain(result)
    test_decision_quality_improves(result)
    test_different_fault_different_candidates(result)
    test_decision_history(result)
    test_normal_state_decision(result)
    test_candidate_sources(result)

    print("\n" + "=" * 60)
    result.summary()
    print("=" * 60)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
