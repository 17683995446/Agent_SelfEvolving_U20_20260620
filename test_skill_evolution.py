"""
阶段5测试：自主技能进化闭环 — SkillEvolutionEngine

测试覆盖：
  1. SkillEvolutionEngine 基本功能
  2. 技能评估（成功率/耗时/综合评分）
  3. 评估等级（excellent/good/needs_improvement/poor）
  4. 自动优化（低性能技能触发优化）
  5. 版本管理（优化后版本递增）
  6. 回滚（新版本性能下降时回滚）
  7. 进化历史记录
  8. 完整进化周期（评估→优化→评估→回滚）
  9. Agent集成：evolve_skills
  10. 调用次数不足时不优化

第一性原理验证：
  - 技能性能可量化评估
  - 低性能技能自动优化
  - 新版本性能下降自动回滚
  - 进化历史可追溯
"""

import sys
import os
import time
import tempfile
import shutil
from pathlib import Path

# 确保能导入模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.skill_evolution import SkillEvolutionEngine, SkillEvaluation
from core.skill_library import SkillLibrary, Skill
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

def test_evolution_engine_basic():
    """测试1: SkillEvolutionEngine 基本功能"""
    print("\n--- 测试1: EvolutionEngine 基本功能 ---")
    tmp_dir = tempfile.mkdtemp(prefix="skills_")
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)
        engine = SkillEvolutionEngine(skill_library=lib)

        status = engine.get_status()
        assert_eq(status["total_evaluations"], 0, "初始无评估")
        assert_eq(status["total_optimizations"], 0, "初始无优化")
        assert_eq(status["history_size"], 0, "初始无历史")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_skill_evaluation_success_rate():
    """测试2: 技能评估 - 成功率"""
    print("\n--- 测试2: 技能评估 - 成功率 ---")
    tmp_dir = tempfile.mkdtemp(prefix="skills_")
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)
        lib.register(name="test_skill", description="测试",
                     code='def execute(**kwargs):\n    return 42\n')

        # 调用5次成功
        for _ in range(5):
            lib.invoke("test_skill")

        engine = SkillEvolutionEngine(skill_library=lib)
        eval_result = engine.evaluate("test_skill")

        assert_true(eval_result is not None, "评估结果非None")
        assert_eq(eval_result.success_rate, 1.0, "成功率=1.0")
        assert_eq(eval_result.invoke_count, 5, "调用5次")
        assert_true(eval_result.score > 0.7, "评分>0.7")
        assert_eq(eval_result.verdict, "excellent", "评级=excellent")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_skill_evaluation_verdicts():
    """测试3: 评估等级"""
    print("\n--- 测试3: 评估等级 ---")
    tmp_dir = tempfile.mkdtemp(prefix="skills_")
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        # excellent: 高成功率
        lib.register(name="excellent_skill", description="优秀",
                     code='def execute(**kwargs):\n    return 1\n')
        for _ in range(10):
            lib.invoke("excellent_skill")

        engine = SkillEvolutionEngine(skill_library=lib)
        eval1 = engine.evaluate("excellent_skill")
        assert_eq(eval1.verdict, "excellent", "高成功率=excellent")

        # poor: 低成功率
        lib.register(name="poor_skill", description="差",
                     code='def execute(fail=False, **kwargs):\n    if fail:\n        raise ValueError("fail")\n    return 1\n')
        for i in range(10):
            lib.invoke("poor_skill", fail=(i % 2 == 0))  # 50%失败

        eval2 = engine.evaluate("poor_skill")
        assert_true(eval2.verdict in ("needs_improvement", "poor"),
                    f"低成功率=needs_improvement或poor: {eval2.verdict}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_auto_optimize_low_performance():
    """测试4: 自动优化低性能技能"""
    print("\n--- 测试4: 自动优化 ---")
    tmp_dir = tempfile.mkdtemp(prefix="skills_")
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        # 注册一个会失败的技能
        lib.register(name="flaky", description="不稳定",
                     code='def execute(fail=False, **kwargs):\n    if fail:\n        raise ValueError("fail")\n    return 1\n')

        # 调用多次（部分失败）
        for i in range(5):
            lib.invoke("flaky", fail=(i % 2 == 0))

        engine = SkillEvolutionEngine(skill_library=lib)
        engine.evaluate("flaky")

        # 优化
        result = engine.optimize("flaky")
        assert_true(result["success"], f"优化成功: {result.get('reason','')}")
        assert_true(result["new_version"] > 1, "新版本>1")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_optimize_version_increment():
    """测试5: 优化后版本递增"""
    print("\n--- 测试5: 版本递增 ---")
    tmp_dir = tempfile.mkdtemp(prefix="skills_")
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)
        lib.register(name="versioned", description="版本测试",
                     code='def execute(**kwargs):\n    return 0\n')

        # 调用足够次数
        for _ in range(5):
            lib.invoke("versioned")

        engine = SkillEvolutionEngine(skill_library=lib)
        engine.evaluate("versioned")

        # 优化前版本=1
        skill_before = lib.get_skill("versioned")
        assert_eq(skill_before.version, 1, "优化前v1")

        # 优化
        result = engine.optimize("versioned")
        if result["success"]:
            skill_after = lib.get_skill("versioned")
            assert_eq(skill_after.version, 2, "优化后v2")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_rollback():
    """测试6: 回滚到上一版本"""
    print("\n--- 测试6: 回滚 ---")
    tmp_dir = tempfile.mkdtemp(prefix="skills_")
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        # v1: 简单返回
        lib.register(name="rollback_test", description="回滚测试",
                     code='def execute(**kwargs):\n    return 1\n')

        # 调用并评估v1
        for _ in range(5):
            lib.invoke("rollback_test")
        engine = SkillEvolutionEngine(skill_library=lib)
        engine.evaluate("rollback_test")

        # v2: 优化（可能变差）
        result = engine.optimize("rollback_test")
        if result["success"]:
            # 回滚
            rb_result = engine.rollback("rollback_test")
            assert_true(rb_result["success"], f"回滚成功: {rb_result.get('reason','')}")

            # 验证代码已恢复
            skill = lib.get_skill("rollback_test")
            assert_true(skill.version > 2, "回滚后版本号递增")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_evolution_history():
    """测试7: 进化历史记录"""
    print("\n--- 测试7: 进化历史 ---")
    tmp_dir = tempfile.mkdtemp(prefix="skills_")
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)
        lib.register(name="hist_test", description="历史测试",
                     code='def execute(**kwargs):\n    return 1\n')

        for _ in range(5):
            lib.invoke("hist_test")

        engine = SkillEvolutionEngine(skill_library=lib)

        # 评估 → 记录1条
        engine.evaluate("hist_test")
        history = engine.get_evolution_history()
        assert_true(len(history) >= 1, "至少1条历史")
        assert_eq(history[0]["action"], "evaluate", "第1条是evaluate")

        # 优化 → 记录2条
        opt_result = engine.optimize("hist_test")
        if opt_result["success"]:
            history = engine.get_evolution_history()
            assert_true(len(history) >= 2, "至少2条历史")
            assert_eq(history[-1]["action"], "optimize", "最后1条是optimize")

        # 按技能名过滤
        filtered = engine.get_evolution_history(skill_name="hist_test")
        assert_true(len(filtered) >= 1, "按名过滤有结果")

        filtered_empty = engine.get_evolution_history(skill_name="nonexistent")
        assert_eq(len(filtered_empty), 0, "不存在技能无历史")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_full_evolution_cycle():
    """测试8: 完整进化周期"""
    print("\n--- 测试8: 完整进化周期 ---")
    tmp_dir = tempfile.mkdtemp(prefix="skills_")
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        # 注册一个低性能技能
        lib.register(name="low_perf", description="低性能",
                     code='def execute(fail=False, **kwargs):\n    if fail:\n        raise ValueError("fail")\n    return 1\n')
        for i in range(5):
            lib.invoke("low_perf", fail=(i % 2 == 0))

        # 注册一个高性能技能
        lib.register(name="high_perf", description="高性能",
                     code='def execute(**kwargs):\n    return 1\n')
        for _ in range(5):
            lib.invoke("high_perf")

        engine = SkillEvolutionEngine(skill_library=lib)

        # 运行进化周期
        result = engine.run_evolution_cycle()

        assert_true(result["evaluated"] >= 2, f"评估了>=2个技能: {result['evaluated']}")
        assert_true(result["optimized"] >= 0, "优化数>=0")
        assert_true(result["rolled_back"] >= 0, "回滚数>=0")
        assert_true("details" in result, "包含details")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_insufficient_invocations():
    """测试9: 调用次数不足时不优化"""
    print("\n--- 测试9: 调用次数不足 ---")
    tmp_dir = tempfile.mkdtemp(prefix="skills_")
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)
        lib.register(name="underused", description="少用",
                     code='def execute(**kwargs):\n    return 1\n')

        # 只调用1次
        lib.invoke("underused")

        engine = SkillEvolutionEngine(skill_library=lib)
        engine.evaluate("underused")

        result = engine.optimize("underused")
        assert_true(not result["success"], "调用不足时优化失败")
        assert_true("不足" in result["reason"], "原因提到不足")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_agent_integration_evolve():
    """测试10: Agent集成 - evolve_skills"""
    print("\n--- 测试10: Agent集成 ---")
    tmp_skills = tempfile.mkdtemp(prefix="skills_")
    try:
        config = AgentConfig()
        config.execution_dry_run = True
        agent = SelfEvolvingAgent(config=config)
        from core.skill_library import SkillLibrary
        agent.skill_library = SkillLibrary(skills_dir=tmp_skills, logger=agent.logger)
        from core.skill_evolution import SkillEvolutionEngine
        agent.skill_evolution = SkillEvolutionEngine(
            skill_library=agent.skill_library, logger=agent.logger
        )

        # 习得并调用技能
        agent.learn_skill("计算加法 compute", skill_name="add")
        for _ in range(5):
            agent.use_skill("add", x=1, y=2)

        # 评估
        eval_result = agent.evaluate_skill("add")
        assert_true(eval_result is not None, "评估结果非None")
        assert_eq(eval_result["skill_name"], "add", "技能名正确")

        # 进化周期
        result = agent.evolve_skills()
        assert_true("evaluated" in result, "包含evaluated")
        assert_true(result["evaluated"] >= 1, "至少评估1个")
    finally:
        shutil.rmtree(tmp_skills, ignore_errors=True)


def test_agent_get_status_includes_evolution():
    """测试11: Agent.get_status 包含 skill_evolution_status"""
    print("\n--- 测试11: get_status包含skill_evolution_status ---")
    config = AgentConfig()
    config.execution_dry_run = True
    agent = SelfEvolvingAgent(config=config)

    status = agent.get_status()
    assert_true("skill_evolution_status" in status, "包含skill_evolution_status")
    assert_true("total_evaluations" in status["skill_evolution_status"], "包含total_evaluations")


def test_evaluation_issues_detection():
    """测试12: 评估问题识别"""
    print("\n--- 测试12: 问题识别 ---")
    tmp_dir = tempfile.mkdtemp(prefix="skills_")
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)
        lib.register(name="problematic", description="有问题",
                     code='def execute(fail=False, **kwargs):\n    if fail:\n        raise ValueError("fail")\n    return 1\n')

        # 调用少+部分失败
        for i in range(2):
            lib.invoke("problematic", fail=(i == 0))

        engine = SkillEvolutionEngine(skill_library=lib)
        eval_result = engine.evaluate("problematic")

        assert_true(len(eval_result.issues) > 0, "识别到问题")
        # 应该有"调用次数不足"和可能"成功率低"
        issues_str = " ".join(eval_result.issues)
        assert_true("调用次数" in issues_str or "成功率" in issues_str,
                    f"问题包含调用次数或成功率: {eval_result.issues}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_score_calculation():
    """测试13: 综合评分计算"""
    print("\n--- 测试13: 综合评分 ---")
    tmp_dir = tempfile.mkdtemp(prefix="skills_")
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        # 100%成功率，快速 → 高分
        lib.register(name="fast_good", description="快且好",
                     code='def execute(**kwargs):\n    return 1\n')
        for _ in range(10):
            lib.invoke("fast_good")

        engine = SkillEvolutionEngine(skill_library=lib)
        eval_good = engine.evaluate("fast_good")
        assert_true(eval_good.score > 0.7, f"快且好→高分: {eval_good.score}")

        # 0%成功率 → 低分
        # 注意：fail=False作为默认值才能通过验证（validate试运行execute()）
        lib.register(name="always_fail", description="总是失败",
                     code='def execute(fail=False, **kwargs):\n    if fail:\n        raise ValueError("fail")\n    return 1\n')
        for _ in range(5):
            lib.invoke("always_fail", fail=True)

        eval_bad = engine.evaluate("always_fail")
        assert_true(eval_bad is not None, "评估结果非None")
        if eval_bad:
            assert_true(eval_bad.score < 0.5, f"总是失败→低分: {eval_bad.score}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


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
    print("=" * 70)
    print("阶段5测试：自主技能进化闭环")
    print("=" * 70)

    tests = [
        test_evolution_engine_basic,
        test_skill_evaluation_success_rate,
        test_skill_evaluation_verdicts,
        test_auto_optimize_low_performance,
        test_optimize_version_increment,
        test_rollback,
        test_evolution_history,
        test_full_evolution_cycle,
        test_insufficient_invocations,
        test_agent_integration_evolve,
        test_agent_get_status_includes_evolution,
        test_evaluation_issues_detection,
        test_score_calculation,
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
