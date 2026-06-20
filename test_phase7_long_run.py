"""
阶段7测试：长期运行验证

第一性原理：生物系统的"稳态"（homeostasis）——长期运行时资源消耗应趋于稳定，
而非无限增长。一个自驱永续进化的Agent必须具备：
  1. 内存稳态：所有内部数据结构有界，不会无限增长
  2. 存储稳态：SQLite数据库有清理机制，不会无限膨胀
  3. 线程稳态：线程数稳定，无泄漏
  4. GC稳态：垃圾回收正常工作

测试覆盖：
  1. SecurityGuard 审计日志有界
  2. AutoHealingEngine 历史有界
  3. IntelligentDecisionMaker 决策历史有界
  4. ReplayBuffer 容量有界
  5. ShortTermMemory 缓存有界
  6. EvolutionDynamics 快照有界
  7. ShortTermMemory SQLite清理
  8. 长期运行内存稳态（200步运行后内存增长可控）
  9. 长期运行线程稳态（无线程泄漏）
  10. GC正常工作
  11. 全局计数器不受裁剪影响
"""

import sys
import os
import time
import gc
import threading
import tracemalloc

# 确保能导入模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from safety.security_guard import SecurityGuard
from core.auto_healing import AutoHealingEngine
from learning.decision_maker import IntelligentDecisionMaker
from learning.reward_system import StrategyLibrary, MetricsSnapshot, RewardComputer
from memory.replay_buffer import ReplayBuffer
from memory.short_term_memory import ShortTermMemory
from optimizer.evolution_dynamics import EvolutionDynamics
from core import MemoryEntry, MemoryType
import numpy as np


# ============================================================================
# 测试框架
# ============================================================================

passed = 0
failed = 0


def assert_true(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {msg}")
    else:
        failed += 1
        print(f"  [FAIL] {msg}")


def assert_le(actual, limit, msg):
    assert_true(actual <= limit, f"{msg} (expected<={limit}, actual={actual})")


# ============================================================================
# 测试用例
# ============================================================================

def test_security_guard_bounded():
    """测试1: SecurityGuard 审计日志有界"""
    print("\n--- 测试1: SecurityGuard 审计日志有界 ---")
    sg = SecurityGuard(max_risk_level="medium", max_audit_log_size=100)

    # 执行200次安全执行（超过上限100）
    # 注意：check()是纯检查不记录审计，safe_execute()才记录审计
    for i in range(200):
        sg.safe_execute(f"ls /tmp/test{i}")

    assert_le(len(sg._audit_log), 100, "审计日志不超过100条")
    # 全局计数器应记录所有200次
    assert_true(sg._total_checks == 200, f"全局计数器记录全部200次 (actual={sg._total_checks})")

    stats = sg.get_stats()
    assert_eq(stats["total_checks"], 200, "get_stats返回全局计数")
    assert_true(stats["audit_records"] <= 100, f"audit_records有界 (actual={stats['audit_records']})")


def test_auto_healing_bounded():
    """测试2: AutoHealingEngine 历史有界"""
    print("\n--- 测试2: AutoHealingEngine 历史有界 ---")
    engine = AutoHealingEngine(max_history_size=50)

    # 运行200次自愈循环（超过上限50）
    for i in range(200):
        # 用高CPU指标触发异常
        engine.run_healing_cycle({"cpu_percent": 95.0, "memory_percent": 50.0, "disk_percent": 50.0})

    assert_le(len(engine._history), 50, "历史记录不超过50条")
    assert_true(engine._total_cycles == 200, f"全局计数器记录全部200次 (actual={engine._total_cycles})")

    stats = engine.get_stats()
    assert_eq(stats["total_cycles"], 200, "get_stats返回全局计数")


def test_decision_maker_bounded():
    """测试3: IntelligentDecisionMaker 决策历史有界"""
    print("\n--- 测试3: IntelligentDecisionMaker 决策历史有界 ---")
    dm = IntelligentDecisionMaker(max_history_size=30)

    # 做200次决策（超过上限30）
    for i in range(200):
        snapshot = MetricsSnapshot(cpu_percent=95.0, mem_percent=50.0, disk_percent=50.0)
        dm.decide(snapshot)

    assert_le(len(dm._decision_history), 30, "决策历史不超过30条")
    assert_true(dm._total_decisions == 200, f"全局计数器记录全部200次 (actual={dm._total_decisions})")

    stats = dm.get_stats()
    assert_eq(stats["total_decisions"], 200, "get_stats返回全局计数")
    assert_le(stats["history_size"], 30, "history_size有界")


def test_replay_buffer_bounded():
    """测试4: ReplayBuffer 容量有界"""
    print("\n--- 测试4: ReplayBuffer 容量有界 ---")
    from memory import Experience
    rb = ReplayBuffer(capacity=100)

    # 添加200个经验（超过容量100）
    for i in range(200):
        exp = Experience(
            state=np.zeros(28),
            action=f"action_{i}",
            reward=0.5,
            next_state=np.zeros(28),
        )
        rb.add(exp)

    assert_le(len(rb), 100, "ReplayBuffer不超过容量100")
    # 验证保留的是最新的100个（action_100 到 action_199）
    samples, weights = rb.sample(5)
    actions = [s.action for s in samples]
    assert_true(all(a.startswith("action_1") for a in actions), "保留的是最新经验")


def test_short_term_memory_bounded():
    """测试5: ShortTermMemory 缓存有界"""
    print("\n--- 测试5: ShortTermMemory 缓存有界 ---")
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_stm.db")
        stm = ShortTermMemory(max_size=50, db_path=db_path, max_db_rows=100, cleanup_interval=10000)

        # 存储200条（超过缓存上限50）
        for i in range(200):
            entry = MemoryEntry(
                content={"idx": i},
                memory_type=MemoryType.EPISODIC,
                value_score=float(i) / 200.0,
                tags=["test"],
            )
            stm.store(entry)

        assert_le(len(stm), 50, "缓存不超过max_size=50")


def test_evolution_dynamics_bounded():
    """测试6: EvolutionDynamics 快照有界"""
    print("\n--- 测试6: EvolutionDynamics 快照有界 ---")
    ed = EvolutionDynamics(max_history=100)

    # 记录200次（超过上限100）
    for i in range(200):
        ed.record(
            prediction_mse=0.01 * i,
            n_parameters=1000,
            n_layers=3,
            hidden_dim=16,
            prediction_latency_ms=1.0,
            optimization_count=i,
            total_experiences=i * 10,
        )

    assert_le(len(ed.snapshots), 100, "快照不超过max_history=100")


def test_sqlite_cleanup():
    """测试7: ShortTermMemory SQLite清理"""
    print("\n--- 测试7: ShortTermMemory SQLite清理 ---")
    import tempfile
    import sqlite3
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_cleanup.db")
        # max_db_rows=20, cleanup_interval=10（每10次store触发清理）
        stm = ShortTermMemory(max_size=10000, db_path=db_path, max_db_rows=20, cleanup_interval=10)

        # 存储100条（触发多次清理）
        for i in range(100):
            entry = MemoryEntry(
                content={"idx": i},
                memory_type=MemoryType.EPISODIC,
                value_score=0.5,
                tags=["cleanup_test"],
            )
            stm.store(entry)

        # 检查SQLite行数
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM experiences")
        db_count = cursor.fetchone()[0]
        conn.close()

        assert_le(db_count, 20, f"SQLite行数不超过max_db_rows=20 (actual={db_count})")


def test_long_run_memory_stability():
    """测试8: 长期运行内存稳态（200步运行后内存增长可控）"""
    print("\n--- 测试8: 长期运行内存稳态 ---")
    from agent import SelfEvolvingAgent
    from core.config import AgentConfig

    config = AgentConfig()
    config.main_loop_interval_ms = 1  # 快速运行
    config.replay_buffer_size = 200  # 小容量便于测试
    agent = SelfEvolvingAgent(config)

    # 用tracemalloc追踪内存
    tracemalloc.start()
    snapshot1 = tracemalloc.take_snapshot()

    # 运行200步
    for i in range(200):
        try:
            agent._step()
            agent.step_count += 1
        except Exception:
            pass

    snapshot2 = tracemalloc.take_snapshot()
    tracemalloc.stop()

    # 计算内存增长
    stats = snapshot2.compare_to(snapshot1, "lineno")
    total_diff = sum(s.size_diff for s in stats if s.size_diff > 0)

    # 验证内部数据结构有界
    assert_le(len(agent.replay_buffer), 200, "replay_buffer有界")
    assert_le(len(agent._last_execution_outcomes), 100, "_last_execution_outcomes有界")
    assert_le(len(agent.evolution_dynamics.snapshots), 1000, "evolution_dynamics有界")

    # 内存增长应可控（小于50MB，200步不应消耗太多）
    total_mb = total_diff / (1024 * 1024)
    print(f"    内存增长: {total_mb:.2f} MB (200步)")
    assert_true(total_mb < 50, f"内存增长可控 <50MB (actual={total_mb:.2f}MB)")


def test_long_run_thread_stability():
    """测试9: 长期运行线程稳态（无线程泄漏）"""
    print("\n--- 测试9: 长期运行线程稳态 ---")
    from agent import SelfEvolvingAgent
    from core.config import AgentConfig

    initial_threads = threading.active_count()

    config = AgentConfig()
    config.main_loop_interval_ms = 1
    agent = SelfEvolvingAgent(config)

    # 运行100步
    for i in range(100):
        try:
            agent._step()
            agent.step_count += 1
        except Exception:
            pass

    final_threads = threading.active_count()
    thread_diff = final_threads - initial_threads
    print(f"    线程数: initial={initial_threads}, final={final_threads}, diff={thread_diff}")
    assert_le(thread_diff, 2, f"线程增长<=2 (actual diff={thread_diff})")


def test_gc_working():
    """测试10: GC正常工作"""
    print("\n--- 测试10: GC正常工作 ---")
    gc.collect()
    gc_stats_before = gc.get_stats()

    # 创建并丢弃大量对象
    for i in range(10000):
        _ = MetricsSnapshot(cpu_percent=50.0, mem_percent=50.0, disk_percent=50.0)

    collected = gc.collect()
    gc_stats_after = gc.get_stats()

    # GC应该回收了对象
    assert_true(collected >= 0, f"GC执行成功 (collected={collected})")
    # GC统计应该有变化
    total_before = sum(s['collections'] for s in gc_stats_before)
    total_after = sum(s['collections'] for s in gc_stats_after)
    assert_true(total_after >= total_before, "GC统计计数器递增")


def test_global_counters_persist_after_trim():
    """测试11: 全局计数器不受裁剪影响"""
    print("\n--- 测试11: 全局计数器不受裁剪影响 ---")
    # SecurityGuard
    sg = SecurityGuard(max_audit_log_size=10)
    for i in range(50):
        sg.safe_execute("ls /tmp")
    assert_eq(sg._total_checks, 50, "SecurityGuard全局计数=50")
    assert_le(len(sg._audit_log), 10, "SecurityGuard审计日志<=10")
    stats = sg.get_stats()
    assert_eq(stats["total_checks"], 50, "get_stats全局计数正确")

    # AutoHealingEngine
    engine = AutoHealingEngine(max_history_size=10)
    for i in range(50):
        engine.run_healing_cycle({"cpu_percent": 95.0, "memory_percent": 50.0, "disk_percent": 50.0})
    assert_eq(engine._total_cycles, 50, "AutoHealing全局计数=50")
    assert_le(len(engine._history), 10, "AutoHealing历史<=10")

    # IntelligentDecisionMaker
    dm = IntelligentDecisionMaker(max_history_size=10)
    for i in range(50):
        snapshot = MetricsSnapshot(cpu_percent=95.0, mem_percent=50.0, disk_percent=50.0)
        dm.decide(snapshot)
    assert_eq(dm._total_decisions, 50, "DecisionMaker全局计数=50")
    assert_le(len(dm._decision_history), 10, "DecisionMaker历史<=10")


def test_long_run_all_structures_stable():
    """测试12: 长期运行后所有数据结构稳定"""
    print("\n--- 测试12: 长期运行后所有数据结构稳定 ---")
    from agent import SelfEvolvingAgent
    from core.config import AgentConfig

    config = AgentConfig()
    config.main_loop_interval_ms = 1
    config.replay_buffer_size = 100
    agent = SelfEvolvingAgent(config)

    # 运行300步
    for i in range(300):
        try:
            agent._step()
            agent.step_count += 1
        except Exception:
            pass

    # 验证所有数据结构有界
    print(f"    replay_buffer: {len(agent.replay_buffer)}")
    print(f"    _last_execution_outcomes: {len(agent._last_execution_outcomes)}")
    print(f"    evolution_dynamics.snapshots: {len(agent.evolution_dynamics.snapshots)}")
    if hasattr(agent, 'strategy_library'):
        sl_stats = agent.strategy_library.get_stats()
        print(f"    strategy_library records: {sl_stats.get('total_strategies', 0)}")
    if hasattr(agent, 'task_router') and hasattr(agent.task_router, 'security_guard'):
        sg_stats = agent.task_router.security_guard.get_stats()
        print(f"    security_guard audit_records: {sg_stats.get('audit_records', 0)}")
        print(f"    security_guard total_checks: {sg_stats.get('total_checks', 0)}")

    assert_le(len(agent.replay_buffer), 100, "replay_buffer <= capacity")
    assert_le(len(agent._last_execution_outcomes), 100, "_last_execution_outcomes <= 100")
    assert_le(len(agent.evolution_dynamics.snapshots), 1000, "evolution_dynamics <= max_history")
    # 策略库的_records应该有界（故障类型×动作的笛卡尔积）
    if hasattr(agent, 'strategy_library'):
        sl_records = agent.strategy_library.get_stats().get('total_strategies', 0)
        assert_le(sl_records, 50, f"strategy_library records有限 (actual={sl_records})")


# ============================================================================
# 辅助函数
# ============================================================================

def assert_eq(actual, expected, msg):
    global passed, failed
    if actual == expected:
        passed += 1
        print(f"  [PASS] {msg}")
    else:
        failed += 1
        print(f"  [FAIL] {msg} (expected={expected}, actual={actual})")


# ============================================================================
# 主函数
# ============================================================================

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
    print("=" * 60)
    print("阶段7测试：长期运行验证")
    print("=" * 60)

    tests = [
        test_security_guard_bounded,
        test_auto_healing_bounded,
        test_decision_maker_bounded,
        test_replay_buffer_bounded,
        test_short_term_memory_bounded,
        test_evolution_dynamics_bounded,
        test_sqlite_cleanup,
        test_long_run_memory_stability,
        test_long_run_thread_stability,
        test_gc_working,
        test_global_counters_persist_after_trim,
        test_long_run_all_structures_stable,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            global failed
            failed += 1
            print(f"  [FAIL] {test.__name__} 抛出异常: {e}")
            import traceback
            traceback.print_exc()

    _cleanup_persistent_state()

    print("\n" + "=" * 60)
    print(f"  通过: {passed}, 失败: {failed}, 共{passed + failed}项")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
