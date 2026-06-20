"""
阶段2闭环反馈测试 — 验证 Agent 从执行结果中学习

测试目标（第一性原理验证）：
1. reward 不再固定0.1，基于执行结果+指标改善计算
2. 执行成功 reward > 执行失败 reward
3. 指标改善时 reward 更高（CPU下降=正分）
4. Experience 进入 replay_buffer 且带真实 reward
5. StrategyLibrary 记录"故障类型→动作→效果"
6. 同类故障多次出现后，UCB 能推荐更优动作
7. 策略库统计正确（成功率、平均reward）
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import List

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import (
    AgentConfig, TaskStatus, TaskPriority, DriveType,
    STATE_VECTOR_DIM, STATE_IDX_CPU_OVERALL, STATE_IDX_MEM_USED, STATE_IDX_DISK_USED,
)
from core.types import Task
from learning import RewardComputer, StrategyLibrary, MetricsSnapshot


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


def make_task(name: str, action: str) -> Task:
    return Task(
        id=f"p2_{name}_{int(__import__('time').time()*1000)}",
        name=name, description=f"test {name}",
        priority=TaskPriority.NORMAL, drive_source=DriveType.SAFETY, action=action,
    )


# =============================================================================
# 测试1: RewardComputer 基本计算
# =============================================================================

def test_reward_basic(result: TestResult):
    print(f"\n  --- 测试1: RewardComputer 基本计算 ---")
    rc = RewardComputer()

    # 成功执行，无指标变化（dry_run）
    before = MetricsSnapshot(cpu_percent=90, mem_percent=50, disk_percent=50)
    after = MetricsSnapshot(cpu_percent=90, mem_percent=50, disk_percent=50)
    r_dry_success = rc.compute(success=True, executed=False, before=before, after=after, task_action="test")

    # 真实执行成功，CPU从90降到60（改善30%）
    after_improved = MetricsSnapshot(cpu_percent=60, mem_percent=50, disk_percent=50)
    r_real_improved = rc.compute(success=True, executed=True, before=before, after=after_improved, task_action="test")

    # 真实执行失败
    r_real_failed = rc.compute(success=False, executed=True, before=before, after=before, task_action="test")

    print(f"    dry_success={r_dry_success:.3f} real_improved={r_real_improved:.3f} real_failed={r_real_failed:.3f}")

    # reward 不再是固定0.1
    if r_dry_success != 0.1:
        result.ok(f"dry_run reward 非固定0.1 (={r_dry_success:.3f})")
    else:
        result.fail("reward 仍固定0.1", f"={r_dry_success}")

    # 真实执行成功+指标改善 > dry_run成功
    if r_real_improved > r_dry_success:
        result.ok(f"真实执行+改善 > dry_run ({r_real_improved:.3f} > {r_dry_success:.3f})")
    else:
        result.fail("reward 排序错误", f"{r_real_improved:.3f} <= {r_dry_success:.3f}")

    # 失败 reward < 成功 reward
    if r_real_failed < r_dry_success:
        result.ok(f"失败 < 成功 ({r_real_failed:.3f} < {r_dry_success:.3f})")
    else:
        result.fail("失败reward过高", f"{r_real_failed:.3f} >= {r_dry_success:.3f}")

    # reward 在 [-1, 1] 范围内
    if -1.0 <= r_real_improved <= 1.0:
        result.ok(f"reward 在 [-1,1] 范围内")
    else:
        result.fail("reward 越界", f"={r_real_improved}")


# =============================================================================
# 测试2: 指标改善方向正确（CPU下降=正分，CPU上升=负分）
# =============================================================================

def test_reward_improvement_direction(result: TestResult):
    print(f"\n  --- 测试2: 指标改善方向 ---")
    rc = RewardComputer()

    before = MetricsSnapshot(cpu_percent=90, mem_percent=50, disk_percent=50)

    # CPU下降20%（改善）
    after_down = MetricsSnapshot(cpu_percent=70, mem_percent=50, disk_percent=50)
    r_down = rc.compute(True, True, before, after_down, "test")

    # CPU上升20%（恶化）
    after_up = MetricsSnapshot(cpu_percent=100, mem_percent=50, disk_percent=50)
    r_up = rc.compute(True, True, before, after_up, "test")

    print(f"    CPU下降 reward={r_down:.3f}, CPU上升 reward={r_up:.3f}")

    if r_down > r_up:
        result.ok(f"指标改善 reward > 指标恶化 ({r_down:.3f} > {r_up:.3f})")
    else:
        result.fail("改善方向错误", f"下降={r_down:.3f} 上升={r_up:.3f}")


# =============================================================================
# 测试3: StrategyLibrary 故障分类
# =============================================================================

def test_fault_classification(result: TestResult):
    print(f"\n  --- 测试3: 故障分类 ---")
    lib = StrategyLibrary()

    cases = [
        (MetricsSnapshot(cpu_percent=95, mem_percent=50, disk_percent=50), "cpu_critical"),
        (MetricsSnapshot(cpu_percent=50, mem_percent=95, disk_percent=50), "mem_critical"),
        (MetricsSnapshot(cpu_percent=50, mem_percent=50, disk_percent=98), "disk_critical"),
        (MetricsSnapshot(cpu_percent=75, mem_percent=50, disk_percent=50), "resource_high"),
        (MetricsSnapshot(cpu_percent=30, mem_percent=40, disk_percent=50), "normal"),
    ]

    for metrics, expected in cases:
        actual = lib.classify_fault(metrics)
        if actual == expected:
            result.ok(f"分类正确 {expected}")
        else:
            result.fail("分类错误", f"期望{expected} 实际{actual}")


# =============================================================================
# 测试4: StrategyLibrary 记录与统计
# =============================================================================

def test_strategy_record_and_stats(result: TestResult):
    print(f"\n  --- 测试4: 策略记录与统计 ---")
    lib = StrategyLibrary()

    # 记录多次执行
    lib.record("cpu_critical", "reduce_cpu_load", success=True, reward=0.5)
    lib.record("cpu_critical", "reduce_cpu_load", success=True, reward=0.6)
    lib.record("cpu_critical", "reduce_cpu_load", success=False, reward=-0.3)
    lib.record("mem_critical", "free_memory", success=True, reward=0.4)

    stats = lib.get_stats()
    print(f"    stats={stats}")

    if stats["total_attempts"] == 4:
        result.ok(f"total_attempts=4")
    else:
        result.fail("total_attempts错误", f"={stats['total_attempts']}")

    if stats["total_strategies"] == 2:
        result.ok(f"total_strategies=2 (cpu_critical+reduce_cpu_load, mem_critical+free_memory)")
    else:
        result.fail("total_strategies错误", f"={stats['total_strategies']}")

    # top_strategies 应有内容
    if len(stats["top_strategies"]) > 0:
        top = stats["top_strategies"][0]
        result.ok(f"top_strategy: {top['fault_type']}/{top['action']} avg_reward={top['avg_reward']:.3f}")
    else:
        result.fail("top_strategies为空", "")


# =============================================================================
# 测试5: UCB 推荐 — 多次后倾向高reward动作
# =============================================================================

def test_ucb_recommendation(result: TestResult):
    print(f"\n  --- 测试5: UCB 推荐 ---")
    lib = StrategyLibrary(exploration_constant=0.5)

    # action_A 历史表现好
    for _ in range(10):
        lib.record("cpu_critical", "action_A", success=True, reward=0.5)

    # action_B 历史表现差
    for _ in range(10):
        lib.record("cpu_critical", "action_B", success=False, reward=-0.3)

    # 推荐 action_A（avg_reward更高）
    rec = lib.recommend("cpu_critical", ["action_A", "action_B"])
    print(f"    recommend={rec}")

    if rec == "action_A":
        result.ok(f"UCB 推荐高reward动作 action_A")
    else:
        result.fail("UCB 推荐错误", f"推荐了{rec}而非action_A")


# =============================================================================
# 测试6: UCB 探索 — 未尝试动作优先
# =============================================================================

def test_ucb_exploration(result: TestResult):
    print(f"\n  --- 测试6: UCB 探索 ---")
    lib = StrategyLibrary(exploration_constant=1.0)

    # 只记录过 action_A
    for _ in range(5):
        lib.record("cpu_critical", "action_A", success=True, reward=0.3)

    # action_B 未尝试过，UCB 应给最高探索分
    rec = lib.recommend("cpu_critical", ["action_A", "action_B"])
    print(f"    recommend={rec} (action_B未尝试过)")

    if rec == "action_B":
        result.ok(f"UCB 探索未尝试动作 action_B")
    else:
        result.fail("UCB 未探索", f"推荐了{rec}而非未尝试的action_B")


# =============================================================================
# 测试7: Agent 闭环 — reward 写入 Experience 和 replay_buffer
# =============================================================================

def test_agent_closed_loop(result: TestResult):
    print(f"\n  --- 测试7: Agent 闭环 ---")
    from agent import SelfEvolvingAgent
    from memory import ShortTermMemory

    tmp_dir = tempfile.mkdtemp(prefix="p2_loop_")
    try:
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        config.execution_dry_run = True
        mem = ShortTermMemory(max_size=100, db_path=os.path.join(tmp_dir, "loop.db"))
        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[])

        # 执行3个任务
        for action in ["reduce_cpu_load", "free_memory", "optimize_resources"]:
            task = make_task(action, action)
            agent.current_state = np.zeros(STATE_VECTOR_DIM, dtype=np.float32)
            agent.current_state[STATE_IDX_CPU_OVERALL] = 0.95
            agent.current_state[STATE_IDX_MEM_USED] = 0.95
            agent._execute_task(task)

        # replay_buffer 应有3条带真实reward的Experience
        if len(agent.replay_buffer) >= 3:
            result.ok(f"replay_buffer 有记录 (len={len(agent.replay_buffer)})")
        else:
            result.fail("replay_buffer 不足", f"len={len(agent.replay_buffer)}")

        # 检查 Experience 的 reward 不是固定0.1
        experiences = list(agent.replay_buffer._buffer)
        rewards = [e.reward for e in experiences[-3:]]
        print(f"    recent rewards={rewards}")
        if all(r != 0.1 for r in rewards):
            result.ok(f"Experience reward 非固定0.1")
        else:
            result.fail("reward 仍固定0.1", f"rewards={rewards}")

        # strategy_library 应有记录
        sstats = agent.strategy_library.get_stats()
        if sstats["total_attempts"] >= 3:
            result.ok(f"strategy_library 有记录 (attempts={sstats['total_attempts']})")
        else:
            result.fail("strategy_library 无记录", f"attempts={sstats['total_attempts']}")

        agent.stop()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =============================================================================
# 测试8: Agent 闭环 — task.reward 反映真实执行结果
# =============================================================================

def test_task_reward_reflects_outcome(result: TestResult):
    print(f"\n  --- 测试8: task.reward 反映执行结果 ---")
    from agent import SelfEvolvingAgent
    from memory import ShortTermMemory

    tmp_dir = tempfile.mkdtemp(prefix="p2_reward_")
    try:
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        config.execution_dry_run = True
        mem = ShortTermMemory(max_size=50, db_path=os.path.join(tmp_dir, "reward.db"))
        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[])

        # 成功的任务（log_only action 总是 success=True）
        task_success = make_task("sampling", "increase_sampling_rate")
        agent.current_state = np.zeros(STATE_VECTOR_DIM, dtype=np.float32)
        agent._execute_task(task_success)

        if task_success.reward > 0:
            result.ok(f"成功任务 reward > 0 ({task_success.reward:.3f})")
        else:
            result.fail("成功任务reward异常", f"={task_success.reward}")

        # task.actual_outcome 应含 reward 信息
        if "reward=" in task_success.actual_outcome:
            result.ok(f"actual_outcome 含 reward 信息")
        else:
            result.fail("actual_outcome 缺reward", task_success.actual_outcome)

        # task.metadata 应有 execution_outcome
        if "execution_outcome" in task_success.metadata:
            eo = task_success.metadata["execution_outcome"]
            if "reward" in eo and "fault_type" in eo:
                result.ok(f"metadata 含 reward 和 fault_type")
            else:
                result.fail("metadata 字段不全", str(eo.keys()))
        else:
            result.fail("metadata 缺 execution_outcome", "")

        agent.stop()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =============================================================================
# 测试9: 多次同类故障后策略库积累
# =============================================================================

def test_strategy_accumulation(result: TestResult):
    print(f"\n  --- 测试9: 策略积累 ---")
    from agent import SelfEvolvingAgent
    from memory import ShortTermMemory

    tmp_dir = tempfile.mkdtemp(prefix="p2_accum_")
    try:
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        config.execution_dry_run = True
        mem = ShortTermMemory(max_size=100, db_path=os.path.join(tmp_dir, "accum.db"))
        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[])

        # 模拟10次CPU故障
        for i in range(10):
            task = make_task(f"cpu_{i}", "reduce_cpu_load")
            agent.current_state = np.zeros(STATE_VECTOR_DIM, dtype=np.float32)
            agent.current_state[STATE_IDX_CPU_OVERALL] = 0.95
            agent._execute_task(task)

        sstats = agent.strategy_library.get_stats()
        print(f"    strategy_stats={sstats}")

        # cpu_critical 故障应有10次记录
        by_fault = sstats["by_fault_type"]
        if by_fault.get("cpu_critical", 0) >= 10:
            result.ok(f"cpu_critical 积累10次 (={by_fault['cpu_critical']})")
        else:
            result.fail("积累不足", f"={by_fault}")

        # top_strategies 应有 reduce_cpu_load
        top_actions = [s["action"] for s in sstats["top_strategies"]]
        if "reduce_cpu_load" in top_actions:
            result.ok(f"reduce_cpu_load 在 top_strategies")
        else:
            result.fail("reduce_cpu_load 不在 top", str(top_actions))

        agent.stop()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =============================================================================
# 测试10: get_status 暴露策略统计
# =============================================================================

def test_status_exposes_strategy(result: TestResult):
    print(f"\n  --- 测试10: get_status 暴露策略统计 ---")
    from agent import SelfEvolvingAgent
    from memory import ShortTermMemory

    tmp_dir = tempfile.mkdtemp(prefix="p2_status_")
    try:
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        config.execution_dry_run = True
        mem = ShortTermMemory(max_size=50, db_path=os.path.join(tmp_dir, "st.db"))
        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[])

        task = make_task("test", "reduce_cpu_load")
        agent.current_state = np.zeros(STATE_VECTOR_DIM, dtype=np.float32)
        agent.current_state[STATE_IDX_CPU_OVERALL] = 0.95
        agent._execute_task(task)

        status = agent.get_status()
        if "strategy_stats" in status:
            result.ok(f"get_status 含 strategy_stats")
        else:
            result.fail("strategy_stats 缺失", "")

        if status["strategy_stats"]["total_attempts"] >= 1:
            result.ok(f"strategy_stats.total_attempts={status['strategy_stats']['total_attempts']}")
        else:
            result.fail("total_attempts=0", "")

        agent.stop()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _cleanup_persistent_state():
    """清理测试产生的持久化状态（秩序化阶段1：测试数据隔离）"""
    import glob
    for f in ["./data/memory.db", "./data/goals_state.json"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    for pattern in ["./data/skills/*.py", "./data/checkpoints/*.json"]:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except OSError:
                pass


def main():
    _cleanup_persistent_state()
    print("\n" + "=" * 60)
    print("  阶段2闭环反馈测试 — Agent 从结果中学习")
    print("=" * 60)

    result = TestResult()
    test_reward_basic(result)
    test_reward_improvement_direction(result)
    test_fault_classification(result)
    test_strategy_record_and_stats(result)
    test_ucb_recommendation(result)
    test_ucb_exploration(result)
    test_agent_closed_loop(result)
    test_task_reward_reflects_outcome(result)
    test_strategy_accumulation(result)
    test_status_exposes_strategy(result)

    _cleanup_persistent_state()
    print("\n" + "=" * 60)
    result.summary()
    print("=" * 60)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
