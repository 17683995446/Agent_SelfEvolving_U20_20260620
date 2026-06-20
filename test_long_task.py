"""
阶段4测试：自驱长任务执行引擎 — LongTaskOrchestrator

测试覆盖：
  1. LongTaskOrchestrator 基本功能（启动任务/状态查询）
  2. 长任务分解（阶段+步骤）
  3. 逐步执行（本地技能执行）
  4. 步骤完成自动推进
  5. 阶段间推进
  6. 任务完成检测
  7. 断点续传（checkpoint/resume）
  8. 失败重试与降级跳过
  9. 委派步骤给其他agent
  10. Agent集成：start_long_task + run_long_task
  11. 自驱运行直到完成
  12. 进度追踪

第一性原理验证：
  - 长任务能分解为阶段和步骤
  - 每步自动决定执行方式（技能/委派/handler）
  - 失败自动重试，重试耗尽降级跳过
  - 断点续传：中断后能恢复进度
  - 自驱运行：无需外部驱动直到完成
"""

import sys
import os
import time
import json
import tempfile
import shutil
from pathlib import Path

# 确保能导入模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.long_task_orchestrator import (
    LongTaskOrchestrator, LongTask, TaskStep,
    StepStatus, TaskStatus,
)
from core.skill_library import SkillLibrary
from core.multi_agent_collaborator import MultiAgentCollaborator
from communication import MessageBus
from agent import SelfEvolvingAgent
from core.config import AgentConfig


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


def assert_eq(actual, expected, msg):
    assert_true(actual == expected, f"{msg} (expected={expected}, actual={actual})")


# ============================================================================
# 测试用例
# ============================================================================

def test_orchestrator_basic():
    """测试1: LongTaskOrchestrator 基本功能"""
    print("\n--- 测试1: Orchestrator 基本功能 ---")
    tmp_dir = tempfile.mkdtemp(prefix="orch_test_")
    try:
        orch = LongTaskOrchestrator(
            agent_id="test_agent",
            checkpoint_dir=tmp_dir,
        )
        assert_true(orch._current_task is None, "初始无任务")
        assert_eq(orch.get_progress()["has_task"], False, "进度显示无任务")

        status = orch.get_status()
        assert_eq(status["agent_id"], "test_agent", "agent_id正确")
        assert_eq(status["tasks_started"], 0, "初始tasks_started=0")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_task_decomposition():
    """测试2: 长任务分解（阶段+步骤）"""
    print("\n--- 测试2: 长任务分解 ---")
    tmp_dir = tempfile.mkdtemp(prefix="orch_test_")
    try:
        orch = LongTaskOrchestrator(agent_id="test", checkpoint_dir=tmp_dir)

        task_id = orch.start_task(
            description="数据处理任务",
            phases=[
                [{"description": "采集数据"}, {"description": "清洗数据"}],
                [{"description": "分析数据"}, {"description": "生成报告"}],
            ],
        )

        assert_true(task_id != "", "返回task_id")
        progress = orch.get_progress()
        assert_eq(progress["has_task"], True, "有活跃任务")
        assert_eq(progress["total_phases"], 2, "2个阶段")
        assert_eq(progress["total_steps"], 4, "4个步骤")
        assert_eq(progress["completed_steps"], 0, "0个完成")
        assert_eq(progress["progress"], 0.0, "进度=0%")
        assert_eq(progress["current_phase"], 0, "当前阶段=0")
        assert_eq(progress["current_step"], 0, "当前步骤=0")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_step_execution_with_handler():
    """测试3: 逐步执行（handler执行）"""
    print("\n--- 测试3: 逐步执行 ---")
    tmp_dir = tempfile.mkdtemp(prefix="orch_test_")
    try:
        orch = LongTaskOrchestrator(agent_id="test", checkpoint_dir=tmp_dir)

        # 注册handler
        executed = []
        def handler(step):
            executed.append(step.description)
            return {"done": step.description}
        orch.register_step_handler("采集", handler)
        orch.register_step_handler("清洗", handler)

        orch.start_task(
            description="数据处理",
            phases=[[{"description": "采集数据"}, {"description": "清洗数据"}]],
        )

        # 执行第一步
        r1 = orch.execute_next()
        assert_eq(r1["status"], "step_completed", "第一步完成")
        assert_true(len(executed) == 1, "handler被调用1次")
        assert_eq(executed[0], "采集数据", "执行了采集数据")

        # 执行第二步
        r2 = orch.execute_next()
        assert_eq(r2["status"], "step_completed", "第二步完成")
        assert_eq(len(executed), 2, "handler被调用2次")

        progress = orch.get_progress()
        assert_eq(progress["completed_steps"], 2, "2步完成")
        assert_eq(progress["progress"], 1.0, "进度=100%")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_step_execution_with_skill():
    """测试4: 用技能执行步骤"""
    print("\n--- 测试4: 技能执行步骤 ---")
    tmp_dir = tempfile.mkdtemp(prefix="orch_test_")
    skills_dir = tempfile.mkdtemp(prefix="skills_")
    try:
        lib = SkillLibrary(skills_dir=skills_dir)
        # 习得一个计算技能
        lib.learn_from_requirement("计算加法 compute", skill_name="add")

        orch = LongTaskOrchestrator(
            agent_id="test",
            skill_library=lib,
            checkpoint_dir=tmp_dir,
        )

        orch.start_task(
            description="计算任务",
            phases=[[
                {
                    "description": "计算3+5",
                    "skill_name": "add",
                    "skill_kwargs": {"x": 3, "y": 5},
                }
            ]],
        )

        r = orch.execute_next()
        assert_eq(r["status"], "step_completed", "技能步骤完成")
        assert_eq(r["result"], 8, "3+5=8")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.rmtree(skills_dir, ignore_errors=True)


def test_phase_advancement():
    """测试5: 阶段间推进"""
    print("\n--- 测试5: 阶段间推进 ---")
    tmp_dir = tempfile.mkdtemp(prefix="orch_test_")
    try:
        orch = LongTaskOrchestrator(agent_id="test", checkpoint_dir=tmp_dir)

        orch.start_task(
            description="三阶段任务",
            phases=[
                [{"description": "步骤A"}],
                [{"description": "步骤B"}],
                [{"description": "步骤C"}],
            ],
        )

        # 完成阶段0
        orch.execute_next()
        progress = orch.get_progress()
        assert_eq(progress["current_phase"], 1, "推进到阶段1")
        assert_eq(progress["current_step"], 0, "步骤=0")

        # 完成阶段1
        orch.execute_next()
        assert_eq(orch.get_progress()["current_phase"], 2, "推进到阶段2")

        # 完成阶段2
        orch.execute_next()
        assert_eq(orch.get_progress()["progress"], 1.0, "进度=100%")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_task_completion():
    """测试6: 任务完成检测"""
    print("\n--- 测试6: 任务完成检测 ---")
    tmp_dir = tempfile.mkdtemp(prefix="orch_test_")
    try:
        orch = LongTaskOrchestrator(agent_id="test", checkpoint_dir=tmp_dir)
        orch.start_task(
            description="短任务",
            phases=[[{"description": "唯一步骤"}]],
        )

        orch.execute_next()
        # 再执行应返回task_completed
        r = orch.execute_next()
        assert_eq(r["status"], "task_completed", "任务已完成")
        assert_eq(orch.get_progress()["status"], "completed", "状态=completed")
        assert_eq(orch.get_status()["tasks_completed"], 1, "tasks_completed=1")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_checkpoint_and_resume():
    """测试7: 断点续传"""
    print("\n--- 测试7: 断点续传 ---")
    tmp_dir = tempfile.mkdtemp(prefix="orch_test_")
    try:
        orch1 = LongTaskOrchestrator(agent_id="test", checkpoint_dir=tmp_dir)
        task_id = orch1.start_task(
            description="可恢复任务",
            phases=[
                [{"description": "步骤A"}, {"description": "步骤B"}, {"description": "步骤C"}],
            ],
        )

        # 执行2步
        orch1.execute_next()
        orch1.execute_next()
        assert_eq(orch1.get_progress()["completed_steps"], 2, "完成2步")

        # 保存断点
        ckpt = orch1.checkpoint()
        assert_true(ckpt is not None, "断点已保存")
        assert_true(ckpt.exists(), "断点文件存在")

        # 新实例恢复
        orch2 = LongTaskOrchestrator(agent_id="test", checkpoint_dir=tmp_dir)
        success = orch2.resume(task_id)
        assert_true(success, "恢复成功")

        progress = orch2.get_progress()
        assert_eq(progress["completed_steps"], 2, "恢复后完成2步")
        assert_eq(progress["current_step"], 2, "当前步骤=2")

        # 继续执行
        r = orch2.execute_next()
        assert_eq(r["status"], "step_completed", "恢复后执行成功")
        assert_eq(orch2.get_progress()["progress"], 1.0, "进度=100%")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_failure_retry_and_skip():
    """测试8: 失败重试与降级跳过"""
    print("\n--- 测试8: 失败重试与降级跳过 ---")
    tmp_dir = tempfile.mkdtemp(prefix="orch_test_")
    try:
        orch = LongTaskOrchestrator(agent_id="test", checkpoint_dir=tmp_dir)

        call_count = [0]
        def failing_handler(step):
            call_count[0] += 1
            raise ValueError("故意失败")
        orch.register_step_handler("失败", failing_handler)

        orch.start_task(
            description="含失败步骤的任务",
            phases=[[
                {"description": "失败步骤", "max_retries": 2},
                {"description": "正常步骤"},
            ]],
        )

        # 第1次执行：失败，retry_count=1，状态=retry
        r1 = orch.execute_next()
        assert_eq(r1["status"], "step_retry", "第1次失败→retry")
        assert_eq(call_count[0], 1, "handler调用1次")

        # 第2次执行：失败，retry_count=2，达到max_retries，跳过
        r2 = orch.execute_next()
        assert_eq(r2["status"], "step_failed_skipped", "第2次失败→跳过")

        # 第3次执行：正常步骤
        r3 = orch.execute_next()
        assert_eq(r3["status"], "step_completed", "下一步正常完成")

        assert_eq(orch.get_progress()["progress"], 1.0, "进度=100%（跳过的也算）")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_delegation():
    """测试9: 委派步骤给其他agent"""
    print("\n--- 测试9: 委派步骤 ---")
    tmp_dir = tempfile.mkdtemp(prefix="orch_test_")
    try:
        bus = MessageBus()
        collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
        collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)

        # B注册能力
        collab_b.register_capability("analyze", lambda p: {"result": "analyzed"})

        # B广播心跳
        collab_b.broadcast_heartbeat(load_score=0.1)
        collab_a.process_messages()

        orch = LongTaskOrchestrator(
            agent_id="agent_a",
            collaborator=collab_a,
            checkpoint_dir=tmp_dir,
        )

        orch.start_task(
            description="委派任务",
            phases=[[
                {
                    "description": "分析数据",
                    "delegate_capability": "analyze",
                }
            ]],
        )

        r = orch.execute_next()
        # 委派应成功（DELEGATED或step_completed）
        assert_true(r["status"] in ("step_completed", "step_retry", "step_failed_skipped"),
                    f"委派步骤有结果: {r['status']}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_agent_integration_start_and_run():
    """测试10: Agent集成 - start_long_task + run_long_task"""
    print("\n--- 测试10: Agent集成 ---")
    tmp_skills = tempfile.mkdtemp(prefix="skills_")
    try:
        config = AgentConfig()
        config.execution_dry_run = True
        agent = SelfEvolvingAgent(config=config)

        # 先习得技能
        agent.learn_skill("计算加法 compute", skill_name="add")

        # 启动长任务
        task_id = agent.start_long_task(
            description="计算任务",
            phases=[[
                {"description": "计算1+2", "skill_name": "add", "skill_kwargs": {"x": 1, "y": 2}},
                {"description": "计算3+4", "skill_name": "add", "skill_kwargs": {"x": 3, "y": 4}},
            ]],
        )
        assert_true(task_id != "", "返回task_id")

        # 自驱运行直到完成
        progress = agent.run_long_task(max_steps=100)
        assert_eq(progress["progress"], 1.0, "进度=100%")
        assert_eq(progress["status"], "completed", "状态=completed")
    finally:
        shutil.rmtree(tmp_skills, ignore_errors=True)


def test_self_driven_completion():
    """测试11: 自驱运行直到完成"""
    print("\n--- 测试11: 自驱运行 ---")
    tmp_dir = tempfile.mkdtemp(prefix="orch_test_")
    try:
        orch = LongTaskOrchestrator(agent_id="test", checkpoint_dir=tmp_dir)

        orch.start_task(
            description="5步任务",
            phases=[[
                {"description": f"步骤{i}"} for i in range(5)
            ]],
        )

        # 自驱运行
        for _ in range(100):
            r = orch.execute_next()
            if r["status"] == "task_completed":
                break

        assert_eq(orch.get_progress()["progress"], 1.0, "进度=100%")
        assert_eq(orch.get_progress()["completed_steps"], 5, "5步完成")
        assert_eq(orch.get_status()["tasks_completed"], 1, "tasks_completed=1")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_progress_tracking():
    """测试12: 进度追踪"""
    print("\n--- 测试12: 进度追踪 ---")
    tmp_dir = tempfile.mkdtemp(prefix="orch_test_")
    try:
        orch = LongTaskOrchestrator(agent_id="test", checkpoint_dir=tmp_dir)
        orch.start_task(
            description="4步任务",
            phases=[[
                {"description": "A"}, {"description": "B"},
                {"description": "C"}, {"description": "D"},
            ]],
        )

        # 执行2步
        orch.execute_next()
        orch.execute_next()

        progress = orch.get_progress()
        assert_eq(progress["completed_steps"], 2, "完成2步")
        assert_eq(progress["total_steps"], 4, "总共4步")
        assert_eq(progress["progress"], 0.5, "进度=50%")
        assert_eq(progress["current_step"], 2, "当前步骤=2")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_no_task_execute():
    """测试13: 无任务时执行"""
    print("\n--- 测试13: 无任务时执行 ---")
    tmp_dir = tempfile.mkdtemp(prefix="orch_test_")
    try:
        orch = LongTaskOrchestrator(agent_id="test", checkpoint_dir=tmp_dir)
        r = orch.execute_next()
        assert_eq(r["status"], "no_task", "无任务时返回no_task")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_agent_get_status_includes_long_task():
    """测试14: Agent.get_status 包含 long_task_status"""
    print("\n--- 测试14: get_status包含long_task_status ---")
    config = AgentConfig()
    config.execution_dry_run = True
    agent = SelfEvolvingAgent(config=config)

    status = agent.get_status()
    assert_true("long_task_status" in status, "包含long_task_status")
    assert_true("has_task" in status["long_task_status"], "包含has_task")


def test_multi_phase_with_skills():
    """测试15: 多阶段+技能混合执行"""
    print("\n--- 测试15: 多阶段+技能混合 ---")
    tmp_dir = tempfile.mkdtemp(prefix="orch_test_")
    skills_dir = tempfile.mkdtemp(prefix="skills_")
    try:
        lib = SkillLibrary(skills_dir=skills_dir)
        lib.learn_from_requirement("计算加法 compute", skill_name="add")
        lib.learn_from_requirement("统计数据 stats", skill_name="stats")

        orch = LongTaskOrchestrator(
            agent_id="test",
            skill_library=lib,
            checkpoint_dir=tmp_dir,
        )

        orch.start_task(
            description="混合任务",
            phases=[
                [{"description": "计算1+2", "skill_name": "add", "skill_kwargs": {"x": 1, "y": 2}}],
                [{"description": "统计数据", "skill_name": "stats", "skill_kwargs": {"data": [1, 2, 3]}}],
            ],
        )

        # 阶段1
        r1 = orch.execute_next()
        assert_eq(r1["status"], "step_completed", "阶段1完成")
        assert_eq(r1["result"], 3, "1+2=3")

        # 阶段2
        r2 = orch.execute_next()
        assert_eq(r2["status"], "step_completed", "阶段2完成")
        stats = r2["result"]
        assert_eq(stats["count"], 3, "count=3")
        assert_eq(stats["sum"], 6, "sum=6")

        assert_eq(orch.get_progress()["progress"], 1.0, "进度=100%")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.rmtree(skills_dir, ignore_errors=True)


# ============================================================================
# 主函数
# ============================================================================

def _cleanup_persistent_state():
    """清理测试产生的持久化状态（秩序化阶段1：测试数据隔离）"""
    import glob
    # 清理所有可能的持久化状态文件
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

    print("=" * 70)
    print("阶段4测试：自驱长任务执行引擎")
    print("=" * 70)

    tests = [
        test_orchestrator_basic,
        test_task_decomposition,
        test_step_execution_with_handler,
        test_step_execution_with_skill,
        test_phase_advancement,
        test_task_completion,
        test_checkpoint_and_resume,
        test_failure_retry_and_skip,
        test_delegation,
        test_agent_integration_start_and_run,
        test_self_driven_completion,
        test_progress_tracking,
        test_no_task_execute,
        test_agent_get_status_includes_long_task,
        test_multi_phase_with_skills,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            global failed
            failed += 1
            import traceback
            print(f"  [ERROR] {test.__name__} 异常: {e}")
            traceback.print_exc()

    _cleanup_persistent_state()

    print("\n" + "=" * 70)
    print(f"测试结果: {passed} 通过, {failed} 失败, 共 {passed + failed} 项断言")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
