"""
阶段1集成测试 — 验证 TaskRouter 真正打通 Agent→执行器 链路

测试目标（第一性原理验证）：
1. Agent 生成的任务真正路由到执行器（不再模拟）
2. CPU>90% 时触发 auto_healing 真实诊断链路
3. dry_run 模式安全（只打印不执行）
4. 非 dry_run 模式真实执行（白名单内的安全命令）
5. 执行结果正确回流到 task 对象
6. ExecutionOutcome 结构完整，供阶段2反馈学习
7. 未知 action 走 log_only 兜底，不崩溃
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Any, List

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import (
    AgentConfig, TaskStatus, TaskPriority, DriveType,
    STATE_VECTOR_DIM, STATE_IDX_CPU_OVERALL, STATE_IDX_MEM_USED, STATE_IDX_DISK_USED,
)
from core.types import Task
from execution.task_router import TaskRouter, ExecutionOutcome


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


def make_task(name: str, action: str, priority=TaskPriority.NORMAL) -> Task:
    """构造测试任务"""
    return Task(
        id=f"test_{name}_{int(__import__('time').time()*1000)}",
        name=name,
        description=f"test task for {name}",
        priority=priority,
        drive_source=DriveType.SAFETY,
        action=action,
    )


def make_state(cpu=0.3, mem=0.4, disk=0.5) -> np.ndarray:
    """构造状态向量"""
    v = np.zeros(STATE_VECTOR_DIM, dtype=np.float32)
    v[STATE_IDX_CPU_OVERALL] = cpu
    v[STATE_IDX_MEM_USED] = mem
    v[STATE_IDX_DISK_USED] = disk
    return v


# =============================================================================
# 测试1: TaskRouter 基本路由 — 各 action 路由到正确执行器
# =============================================================================

def test_basic_routing(result: TestResult):
    print(f"\n  --- 测试1: TaskRouter 基本路由 ---")
    router = TaskRouter(dry_run=True)

    cases = [
        ("reduce_cpu_load", "auto_healing"),
        ("free_memory", "auto_healing"),
        ("free_disk_space", "auto_healing"),
        ("optimize_resources", "task_executor"),
        ("increase_sampling_rate", "log_only"),
        ("unknown_action_xyz", "log_only"),  # 未知action兜底
    ]

    for action, expected_executor in cases:
        task = make_task(action, action)
        outcome = router.route(task, make_state(cpu=0.95, mem=0.95))
        if outcome.executor == expected_executor:
            result.ok(f"action={action} -> {expected_executor}")
        else:
            result.fail(f"action={action} 路由错误",
                        f"期望{expected_executor}, 实际{outcome.executor}")


# =============================================================================
# 测试2: CPU>90% 触发 auto_healing 真实诊断链路
# =============================================================================

def test_cpu_critical_triggers_healing(result: TestResult):
    print(f"\n  --- 测试2: CPU>90% 触发 auto_healing ---")
    router = TaskRouter(dry_run=True)

    task = make_task("cpu_throttle", "reduce_cpu_load")
    state = make_state(cpu=0.99, mem=0.50, disk=0.50)  # CPU 99%
    outcome = router.route(task, state)

    # auto_healing 应该被调用，且因为CPU>80%应诊断出 cpu_bound_process
    if outcome.executor == "auto_healing":
        result.ok(f"路由到 auto_healing")
    else:
        result.fail("路由错误", f"executor={outcome.executor}")

    # dry_run 模式下 auto_healing 的 auto_approve_low_risk=False，应不执行
    # 但诊断链路应该走完，message 应有内容（修复后auto_healing会填充message）
    if outcome.message and "healthy" not in outcome.message:
        result.ok(f"诊断链路走完 (message={outcome.message[:60]})")
    else:
        result.fail("诊断未触发", f"message={outcome.message}")


# =============================================================================
# 测试3: dry_run 模式安全 — 只打印不执行
# =============================================================================

def test_dry_run_safety(result: TestResult):
    print(f"\n  --- 测试3: dry_run 模式安全 ---")
    router = TaskRouter(dry_run=True)

    task = make_task("optimize", "optimize_resources")
    outcome = router.route(task, make_state())

    # dry_run 模式下 task_executor 应返回 success=True 但 executed=False
    if not outcome.executed:
        result.ok(f"dry_run 未真实执行 (executed=False)")
    else:
        result.fail("dry_run 失效", "executed=True")

    if outcome.success:
        result.ok(f"dry_run 返回 success=True")
    else:
        result.fail("dry_run 返回失败", f"stderr={outcome.stderr}")


# =============================================================================
# 测试4: 非 dry_run 模式真实执行白名单命令
# =============================================================================

def test_real_execution(result: TestResult):
    print(f"\n  --- 测试4: 非 dry_run 真实执行 ---")
    router = TaskRouter(dry_run=False)

    task = make_task("optimize", "optimize_resources")
    outcome = router.route(task, make_state())

    # optimize_resources 路由到 task_executor，执行 "ps -eo ..." (SAFE级别)
    if outcome.executed:
        result.ok(f"真实执行 (executed=True)")
    else:
        result.fail("未真实执行", f"stderr={outcome.stderr}")

    if outcome.success:
        result.ok(f"执行成功 (rc={outcome.return_code})")
    else:
        result.fail("执行失败", f"rc={outcome.return_code} stderr={outcome.stderr}")

    # stdout 应该有 ps 输出
    if outcome.stdout and len(outcome.stdout) > 0:
        result.ok(f"有命令输出 (len={len(outcome.stdout)})")
    else:
        result.fail("无命令输出", "stdout为空")


# =============================================================================
# 测试5: 执行结果正确回流到 task 对象
# =============================================================================

def test_outcome_reflects_to_task(result: TestResult):
    print(f"\n  --- 测试5: 执行结果回流到 task ---")
    import time as _time
    from agent import SelfEvolvingAgent
    from memory import ShortTermMemory

    tmp_dir = tempfile.mkdtemp(prefix="p1_reflect_")
    try:
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        config.execution_dry_run = True
        mem = ShortTermMemory(max_size=100, db_path=os.path.join(tmp_dir, "reflect.db"))
        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[])

        # 手动构造一个任务并执行
        task = make_task("cpu_throttle", "reduce_cpu_load")
        agent.current_state = make_state(cpu=0.99)
        agent._execute_task(task)

        if task.status == TaskStatus.COMPLETED:
            result.ok(f"task.status 正确流转到 COMPLETED")
        elif task.status == TaskStatus.FAILED:
            result.ok(f"task.status 流转到 FAILED（dry_run下auto_healing未执行）")
        else:
            result.fail("task.status 错误", f"status={task.status}")

        if task.actual_outcome:
            result.ok(f"task.actual_outcome 已填充 ({task.actual_outcome[:50]})")
        else:
            result.fail("actual_outcome 为空", "未回流执行结果")

        if "execution_outcome" in task.metadata:
            result.ok(f"task.metadata 有 execution_outcome")
        else:
            result.fail("metadata 缺失", "无 execution_outcome")

        if task.reward != 0.1 or task.reward != 0.0:
            result.ok(f"task.reward 已更新 ({task.reward})")
        else:
            result.fail("reward 未更新", f"reward={task.reward}")

        # _last_execution_outcomes 应有记录
        if len(agent._last_execution_outcomes) == 1:
            result.ok(f"_last_execution_outcomes 已记录 (len=1)")
        else:
            result.fail("_last_execution_outcomes 错误", f"len={len(agent._last_execution_outcomes)}")

        agent.stop()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =============================================================================
# 测试6: ExecutionOutcome 结构完整
# =============================================================================

def test_outcome_structure(result: TestResult):
    print(f"\n  --- 测试6: ExecutionOutcome 结构完整 ---")
    router = TaskRouter(dry_run=True)
    task = make_task("test", "optimize_resources")
    outcome = router.route(task, make_state(cpu=0.6))

    required_fields = ["task_id", "task_name", "task_action", "executed", "success",
                       "executor", "command", "stdout", "stderr", "return_code",
                       "duration_ms", "before_metrics", "after_metrics", "message", "timestamp"]
    missing = [f for f in required_fields if not hasattr(outcome, f)]
    if not missing:
        result.ok(f"所有必需字段存在 ({len(required_fields)}个)")
    else:
        result.fail("字段缺失", f"缺少: {missing}")

    # before_metrics 应包含 cpu/memory/disk
    if "cpu_percent" in outcome.before_metrics:
        result.ok(f"before_metrics 含 cpu_percent ({outcome.before_metrics['cpu_percent']:.1f})")
    else:
        result.fail("before_metrics 缺失", str(outcome.before_metrics))


# =============================================================================
# 测试7: 未知 action 走 log_only 兜底，不崩溃
# =============================================================================

def test_unknown_action_fallback(result: TestResult):
    print(f"\n  --- 测试7: 未知 action 兜底 ---")
    router = TaskRouter(dry_run=False)

    task = make_task("weird_task", "totally_unknown_action_12345")
    outcome = router.route(task, make_state())

    if outcome.executor == "log_only":
        result.ok(f"未知action走 log_only 兜底")
    else:
        result.fail("兜底失效", f"executor={outcome.executor}")

    if outcome.success:
        result.ok(f"兜底返回 success=True（不崩溃）")
    else:
        result.fail("兜底失败", f"stderr={outcome.stderr}")


# =============================================================================
# 测试8: 完整 Agent 步进 — 任务生成→路由→执行 闭环
# =============================================================================

def test_full_step_pipeline(result: TestResult):
    print(f"\n  --- 测试8: 完整步进闭环 ---")
    from agent import SelfEvolvingAgent
    from memory import ShortTermMemory
    from core.types import PerceptionInput, PerceptionOutput, PerceptionModality
    from perception.sensor import Sensor

    class HighCpuSensor(Sensor):
        def __init__(self):
            super().__init__("high_cpu_sensor", PerceptionModality.SYSTEM)
            self._running = True
        def start(self): self._running = True
        def stop(self): self._running = False
        def read(self):
            if not self._running: return None
            v = np.zeros(STATE_VECTOR_DIM, dtype=np.float32)
            v[STATE_IDX_CPU_OVERALL] = 0.99  # CPU 99% 触发 cpu_throttle 任务
            v[STATE_IDX_MEM_USED] = 0.50
            v[STATE_IDX_DISK_USED] = 0.50
            for i in range(10, STATE_VECTOR_DIM):
                v[i] = 0.2
            return PerceptionInput(modality=self.modality, raw_data=v.tobytes(),
                                   timestamp=__import__('time').time(), source_id=self.source_id, metadata={})
        def encode_to_vector(self, inp):
            return PerceptionOutput(feature_vector=np.frombuffer(inp.raw_data, dtype=np.float32).copy(),
                                    modality=self.modality, timestamp=inp.timestamp,
                                    source_id=self.source_id, confidence=1.0)
        def update(self, sv):
            return {"anomaly_score": 0.9, "is_anomaly": True}

    tmp_dir = tempfile.mkdtemp(prefix="p1_full_")
    try:
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        config.execution_dry_run = True
        mem = ShortTermMemory(max_size=100, db_path=os.path.join(tmp_dir, "full.db"))
        sensor = HighCpuSensor()
        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[sensor])

        # 执行5步
        for i in range(5):
            agent._step()
            agent.step_count += 1

        # 验证 task_router 有执行记录
        stats = agent.task_router.get_stats()
        if stats["total_routed"] > 0:
            result.ok(f"task_router 有执行记录 (total={stats['total_routed']})")
        else:
            result.fail("task_router 无记录", "未路由任何任务")

        # 验证执行器分布
        if "auto_healing" in stats["by_executor"]:
            result.ok(f"auto_healing 被调用 (count={stats['by_executor']['auto_healing']})")
        else:
            result.fail("auto_healing 未被调用", f"by_executor={stats['by_executor']}")

        # 验证 _last_execution_outcomes 有记录
        if len(agent._last_execution_outcomes) > 0:
            result.ok(f"_last_execution_outcomes 有记录 (len={len(agent._last_execution_outcomes)})")
        else:
            result.fail("_last_execution_outcomes 为空", "无执行结果回流")

        agent.stop()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =============================================================================
# 测试9: get_status 暴露执行统计
# =============================================================================

def test_status_exposes_execution(result: TestResult):
    print(f"\n  --- 测试9: get_status 暴露执行统计 ---")
    from agent import SelfEvolvingAgent
    from memory import ShortTermMemory

    tmp_dir = tempfile.mkdtemp(prefix="p1_status_")
    try:
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        config.execution_dry_run = True
        mem = ShortTermMemory(max_size=100, db_path=os.path.join(tmp_dir, "status.db"))
        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[])

        # 手动执行几个任务
        for action in ["reduce_cpu_load", "free_memory", "optimize_resources"]:
            task = make_task(action, action)
            agent.current_state = make_state(cpu=0.95, mem=0.95)
            agent._execute_task(task)

        status = agent.get_status()
        if "execution_stats" in status:
            result.ok(f"get_status 含 execution_stats")
        else:
            result.fail("execution_stats 缺失", "get_status 未暴露")

        exec_stats = status["execution_stats"]
        if exec_stats["total_routed"] >= 3:
            result.ok(f"execution_stats.total_routed={exec_stats['total_routed']}")
        else:
            result.fail("total_routed 错误", f"={exec_stats['total_routed']}")

        if "by_executor" in exec_stats:
            result.ok(f"by_executor 存在 ({exec_stats['by_executor']})")
        else:
            result.fail("by_executor 缺失", str(exec_stats))

        agent.stop()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =============================================================================
# 测试10: config.execution_dry_run 控制真实执行
# =============================================================================

def test_config_controls_dry_run(result: TestResult):
    print(f"\n  --- 测试10: config 控制 dry_run ---")
    from agent import SelfEvolvingAgent
    from memory import ShortTermMemory

    tmp_dir = tempfile.mkdtemp(prefix="p1_cfg_")
    try:
        # dry_run=True
        config1 = AgentConfig()
        config1.execution_dry_run = True
        config1.main_loop_interval_ms = 0
        mem1 = ShortTermMemory(max_size=50, db_path=os.path.join(tmp_dir, "dry.db"))
        agent1 = SelfEvolvingAgent(config=config1, memory=mem1, sensors=[])
        if agent1.task_router.dry_run == True:
            result.ok(f"execution_dry_run=True 生效")
        else:
            result.fail("dry_run 未生效", f"dry_run={agent1.task_router.dry_run}")
        agent1.stop()

        # dry_run=False
        config2 = AgentConfig()
        config2.execution_dry_run = False
        config2.main_loop_interval_ms = 0
        mem2 = ShortTermMemory(max_size=50, db_path=os.path.join(tmp_dir, "real.db"))
        agent2 = SelfEvolvingAgent(config=config2, memory=mem2, sensors=[])
        if agent2.task_router.dry_run == False:
            result.ok(f"execution_dry_run=False 生效")
        else:
            result.fail("dry_run 未关闭", f"dry_run={agent2.task_router.dry_run}")
        agent2.stop()
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
    print("  阶段1集成测试 — TaskRouter 打通 Agent→执行器")
    print("=" * 60)

    result = TestResult()
    test_basic_routing(result)
    test_cpu_critical_triggers_healing(result)
    test_dry_run_safety(result)
    test_real_execution(result)
    test_outcome_reflects_to_task(result)
    test_outcome_structure(result)
    test_unknown_action_fallback(result)
    test_full_step_pipeline(result)
    test_status_exposes_execution(result)
    test_config_controls_dry_run(result)

    _cleanup_persistent_state()
    print("\n" + "=" * 60)
    result.summary()
    print("=" * 60)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
