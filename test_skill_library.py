"""
阶段2测试：技能库与技能习得 — 从固定动作到可扩展技能

测试覆盖：
  1. SkillLibrary 基本功能（注册/查询/列表/统计）
  2. 技能验证（语法检查/模块加载/execute函数/试运行）
  3. 技能调用（成功/失败/统计更新）
  4. 从需求生成技能（关键词匹配/模板选择）
  5. 技能持久化（保存到磁盘/重启后加载）
  6. 技能淘汰（容量上限/成功率最低优先淘汰）
  7. 版本管理（同名技能版本递增）
  8. Agent集成：learn_skill + use_skill + get_skill_status
  9. 技能代码模板（compute/check/stats/convert/generic）
  10. 错误处理（无效代码/缺失execute/调用异常）

第一性原理验证：
  - Agent能从自然语言需求生成可执行技能代码
  - 技能通过验证后入库，可重复调用
  - 调用统计驱动技能淘汰与版本演进
"""

import sys
import os
import time
import shutil
import tempfile
from pathlib import Path

# 确保能导入模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.skill_library import Skill, SkillLibrary
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
# 测试辅助
# ============================================================================

def make_temp_skills_dir():
    """创建临时技能目录"""
    tmp_dir = tempfile.mkdtemp(prefix="skills_test_")
    return tmp_dir


def cleanup_dir(path):
    """清理目录"""
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


# ============================================================================
# 测试用例
# ============================================================================

def test_skill_library_basic():
    """测试1: SkillLibrary 基本功能"""
    print("\n--- 测试1: SkillLibrary 基本功能 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        lib = SkillLibrary(skills_dir=tmp_dir, max_skills=100)

        assert_eq(lib.get_stats()["total_skills"], 0, "初始无技能")
        assert_eq(len(lib.list_skills()), 0, "列表为空")

        # 注册一个简单技能
        code = '''def execute(**kwargs):
    return "hello"
'''
        result = lib.register(
            name="hello_skill",
            description="打招呼技能",
            code=code,
        )
        assert_true(result["success"], "注册成功")
        assert_true(result["validated"], "已验证")

        # 查询
        skill = lib.get_skill("hello_skill")
        assert_true(skill is not None, "查询到技能")
        assert_eq(skill.name, "hello_skill", "技能名正确")
        assert_eq(skill.version, 1, "版本=1")
        assert_true(skill.validated, "已验证")

        # 列表
        skills = lib.list_skills()
        assert_eq(len(skills), 1, "列表有1个技能")
        assert_eq(skills[0]["name"], "hello_skill", "列表项正确")

        # 统计
        stats = lib.get_stats()
        assert_eq(stats["total_skills"], 1, "统计total_skills=1")
        assert_eq(stats["validated_skills"], 1, "统计validated_skills=1")
    finally:
        cleanup_dir(tmp_dir)


def test_skill_validation_syntax_error():
    """测试2: 技能验证 - 语法错误"""
    print("\n--- 测试2: 技能验证 - 语法错误 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        # 语法错误代码
        bad_code = '''def execute(:
    return
'''
        result = lib.register(name="bad_skill", description="语法错误", code=bad_code)
        assert_true(not result["success"], "注册失败")
        assert_true("验证失败" in result["reason"], "原因包含验证失败")

        # 不应入库
        assert_true(lib.get_skill("bad_skill") is None, "未入库")
    finally:
        cleanup_dir(tmp_dir)


def test_skill_validation_missing_execute():
    """测试3: 技能验证 - 缺少execute函数"""
    print("\n--- 测试3: 技能验证 - 缺少execute函数 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        # 缺少 execute 函数
        code = '''def foo():
    return 42
'''
        result = lib.register(name="no_execute", description="无execute", code=code)
        assert_true(not result["success"], "注册失败")
        assert_true("execute" in result["reason"], "原因提到execute")
    finally:
        cleanup_dir(tmp_dir)


def test_skill_invoke_success():
    """测试4: 技能调用 - 成功"""
    print("\n--- 测试4: 技能调用 - 成功 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        code = '''def execute(x=0, y=0, **kwargs):
    return x + y
'''
        lib.register(name="add", description="加法", code=code)

        # 调用
        result = lib.invoke("add", x=3, y=5)
        assert_true(result["success"], "调用成功")
        assert_eq(result["result"], 8, "结果=8")
        assert_true(result["duration_ms"] >= 0, "耗时>=0")

        # 统计更新
        skill = lib.get_skill("add")
        assert_eq(skill.invoke_count, 1, "invoke_count=1")
        assert_eq(skill.success_count, 1, "success_count=1")
        assert_eq(skill.failure_count, 0, "failure_count=0")
        assert_true(skill.success_rate() == 1.0, "成功率=1.0")
        assert_true(skill.last_used > 0, "last_used已更新")
    finally:
        cleanup_dir(tmp_dir)


def test_skill_invoke_failure():
    """测试5: 技能调用 - 失败（运行时异常）"""
    print("\n--- 测试5: 技能调用 - 失败 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        code = '''def execute(**kwargs):
    raise ValueError("故意失败")
'''
        # 注意：试运行 execute() 也会抛 ValueError，但 validate 用 try/except 捕获
        # 这里需要让试运行通过但实际调用失败
        # 改用条件抛异常
        code = '''def execute(fail=False, **kwargs):
    if fail:
        raise ValueError("故意失败")
    return "ok"
'''
        lib.register(name="flaky", description="不稳定技能", code=code)

        # 成功调用
        r1 = lib.invoke("flaky", fail=False)
        assert_true(r1["success"], "不fail时成功")

        # 失败调用
        r2 = lib.invoke("flaky", fail=True)
        assert_true(not r2["success"], "fail时失败")
        assert_true(r2["error"] is not None, "有错误信息")

        # 统计
        skill = lib.get_skill("flaky")
        assert_eq(skill.invoke_count, 2, "invoke_count=2")
        assert_eq(skill.success_count, 1, "success_count=1")
        assert_eq(skill.failure_count, 1, "failure_count=1")
    finally:
        cleanup_dir(tmp_dir)


def test_skill_invoke_nonexistent():
    """测试6: 调用不存在的技能"""
    print("\n--- 测试6: 调用不存在的技能 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)
        result = lib.invoke("nonexistent")
        assert_true(not result["success"], "调用失败")
        assert_true("不存在" in result["error"], "错误信息提到不存在")
    finally:
        cleanup_dir(tmp_dir)


def test_learn_from_requirement_compute():
    """测试7: 从需求生成技能 - 计算类"""
    print("\n--- 测试7: 从需求生成技能 - 计算类 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        result = lib.learn_from_requirement(
            requirement="计算两个数的和 compute sum",
        )
        assert_true(result["success"], "习得成功")
        assert_true(result["validated"], "已验证")
        assert_true(result["skill_name"] != "", "技能名非空")

        # 调用生成的计算技能
        skill_name = result["skill_name"]
        r = lib.invoke(skill_name, x=10, y=20)
        assert_true(r["success"], "调用成功")
        assert_eq(r["result"], 30, "10+20=30")
    finally:
        cleanup_dir(tmp_dir)


def test_learn_from_requirement_check():
    """测试8: 从需求生成技能 - 检查类"""
    print("\n--- 测试8: 从需求生成技能 - 检查类 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        result = lib.learn_from_requirement(
            requirement="检查阈值 check threshold",
            skill_name="threshold_check",
        )
        assert_true(result["success"], "习得成功")
        assert_eq(result["skill_name"], "threshold_check", "技能名正确")

        # 调用
        r = lib.invoke("threshold_check", value=10, threshold=5)
        assert_true(r["success"], "调用成功")
        assert_eq(r["result"], True, "10>5=True")

        r2 = lib.invoke("threshold_check", value=3, threshold=5)
        assert_eq(r2["result"], False, "3>5=False")
    finally:
        cleanup_dir(tmp_dir)


def test_learn_from_requirement_stats():
    """测试9: 从需求生成技能 - 统计类"""
    print("\n--- 测试9: 从需求生成技能 - 统计类 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        result = lib.learn_from_requirement(
            requirement="统计数据统计 stats",
            skill_name="data_stats",
        )
        assert_true(result["success"], "习得成功")

        r = lib.invoke("data_stats", data=[1, 2, 3, 4, 5])
        assert_true(r["success"], "调用成功")
        stats = r["result"]
        assert_eq(stats["count"], 5, "count=5")
        assert_eq(stats["sum"], 15, "sum=15")
        assert_eq(stats["avg"], 3, "avg=3")
        assert_eq(stats["min"], 1, "min=1")
        assert_eq(stats["max"], 5, "max=5")
    finally:
        cleanup_dir(tmp_dir)


def test_learn_from_requirement_convert():
    """测试10: 从需求生成技能 - 转换类"""
    print("\n--- 测试10: 从需求生成技能 - 转换类 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        result = lib.learn_from_requirement(
            requirement="转换数据类型 convert transform",
            skill_name="type_convert",
        )
        assert_true(result["success"], "习得成功")

        r = lib.invoke("type_convert", value="123", target_type="int")
        assert_true(r["success"], "调用成功")
        assert_eq(r["result"], 123, "'123'->123")

        r2 = lib.invoke("type_convert", value=456, target_type="str")
        assert_eq(r2["result"], "456", "456->'456'")
    finally:
        cleanup_dir(tmp_dir)


def test_learn_from_requirement_generic():
    """测试11: 从需求生成技能 - 通用类"""
    print("\n--- 测试11: 从需求生成技能 - 通用类 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        result = lib.learn_from_requirement(
            requirement="执行某项操作",
            skill_name="generic_op",
        )
        assert_true(result["success"], "习得成功")

        r = lib.invoke("generic_op", foo="bar")
        assert_true(r["success"], "调用成功")
        assert_eq(r["result"]["status"], "ok", "status=ok")
        assert_eq(r["result"]["skill"], "generic_op", "skill名正确")
    finally:
        cleanup_dir(tmp_dir)


def test_skill_persistence():
    """测试12: 技能持久化（保存到磁盘/重启后加载）"""
    print("\n--- 测试12: 技能持久化 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        # 第一个实例：注册技能
        lib1 = SkillLibrary(skills_dir=tmp_dir)
        lib1.learn_from_requirement(
            requirement="计算加法 compute",
            skill_name="persist_add",
        )
        assert_eq(len(lib1.list_skills()), 1, "lib1有1个技能")

        # 验证文件已写入
        skill_file = Path(tmp_dir) / "persist_add.py"
        assert_true(skill_file.exists(), "技能文件已写入磁盘")

        # 第二个实例：从同一目录加载
        lib2 = SkillLibrary(skills_dir=tmp_dir)
        skills = lib2.list_skills()
        assert_eq(len(skills), 1, "lib2加载到1个技能")
        assert_eq(skills[0]["name"], "persist_add", "技能名正确")

        # 应能调用
        r = lib2.invoke("persist_add", x=1, y=2)
        assert_true(r["success"], "加载后可调用")
        assert_eq(r["result"], 3, "1+2=3")
    finally:
        cleanup_dir(tmp_dir)


def test_skill_eviction():
    """测试13: 技能淘汰（容量上限）"""
    print("\n--- 测试13: 技能淘汰 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        lib = SkillLibrary(skills_dir=tmp_dir, max_skills=3)

        # 注册3个技能
        for i in range(3):
            lib.register(
                name=f"skill_{i}",
                description=f"技能{i}",
                code='def execute(**kwargs):\n    return 0\n',
            )
        assert_eq(len(lib.list_skills()), 3, "注册3个技能")

        # 调用 skill_0 多次（高成功率+高使用）
        for _ in range(5):
            lib.invoke("skill_0")

        # 注册第4个，应淘汰最差的（skill_1 或 skill_2，调用次数=0）
        lib.register(
            name="skill_3",
            description="技能3",
            code='def execute(**kwargs):\n    return 0\n',
        )
        assert_eq(len(lib.list_skills()), 3, "仍为3个技能（淘汰1个）")
        # skill_0 应保留（使用最多）
        assert_true(lib.get_skill("skill_0") is not None, "skill_0保留")
    finally:
        cleanup_dir(tmp_dir)


def test_skill_version_management():
    """测试14: 版本管理（同名技能版本递增）"""
    print("\n--- 测试14: 版本管理 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        # 第一次注册
        r1 = lib.register(
            name="versioned",
            description="v1",
            code='def execute(**kwargs):\n    return 1\n',
        )
        assert_eq(r1["version"], 1, "第一次version=1")

        # 第二次注册同名（升级）
        r2 = lib.register(
            name="versioned",
            description="v2",
            code='def execute(**kwargs):\n    return 2\n',
        )
        assert_eq(r2["version"], 2, "第二次version=2")

        # 应只有1个技能
        assert_eq(len(lib.list_skills()), 1, "仍为1个技能")

        # 调用应返回新版本结果
        r = lib.invoke("versioned")
        assert_eq(r["result"], 2, "返回v2结果")
    finally:
        cleanup_dir(tmp_dir)


def test_agent_integration_learn_skill():
    """测试15: Agent集成 - learn_skill"""
    print("\n--- 测试15: Agent集成 - learn_skill ---")
    # 使用临时目录避免污染
    tmp_goals = tempfile.mktemp(suffix=".json")
    tmp_skills = tempfile.mkdtemp(prefix="agent_skills_")
    try:
        config = AgentConfig()
        config.execution_dry_run = True
        agent = SelfEvolvingAgent(config=config)

        # 重新指定技能目录
        from core.skill_library import SkillLibrary
        agent.skill_library = SkillLibrary(skills_dir=tmp_skills, logger=agent.logger)

        # 习得技能
        result = agent.learn_skill("计算加法 compute sum")
        assert_true(result["success"], "Agent习得技能成功")
        assert_true(result["skill_name"] != "", "技能名非空")

        # 查询状态
        status = agent.get_skill_status()
        assert_true(status["total_skills"] >= 1, "total_skills>=1")
        assert_true(status["total_validations"] >= 1, "total_validations>=1")
    finally:
        cleanup_dir(tmp_skills)
        try:
            os.unlink(tmp_goals)
        except Exception:
            pass


def test_agent_integration_use_skill():
    """测试16: Agent集成 - use_skill"""
    print("\n--- 测试16: Agent集成 - use_skill ---")
    tmp_skills = tempfile.mkdtemp(prefix="agent_skills_")
    try:
        config = AgentConfig()
        config.execution_dry_run = True
        agent = SelfEvolvingAgent(config=config)
        from core.skill_library import SkillLibrary
        agent.skill_library = SkillLibrary(skills_dir=tmp_skills, logger=agent.logger)

        # 习得并调用
        agent.learn_skill("计算加法 compute", skill_name="agent_add")
        r = agent.use_skill("agent_add", x=100, y=200)
        assert_true(r["success"], "Agent调用技能成功")
        assert_eq(r["result"], 300, "100+200=300")

        # 状态查询
        status = agent.get_skill_status()
        assert_true(status["total_invocations"] >= 1, "total_invocations>=1")
    finally:
        cleanup_dir(tmp_skills)


def test_agent_get_status_includes_skill():
    """测试17: Agent.get_status 包含 skill_stats"""
    print("\n--- 测试17: Agent.get_status 包含 skill_stats ---")
    config = AgentConfig()
    config.execution_dry_run = True
    agent = SelfEvolvingAgent(config=config)

    status = agent.get_status()
    assert_true("skill_stats" in status, "status包含skill_stats")
    assert_true("total_skills" in status["skill_stats"], "skill_stats包含total_skills")


def test_invalid_skill_name():
    """测试18: 无效技能名"""
    print("\n--- 测试18: 无效技能名 ---")
    tmp_dir = make_temp_skills_dir()
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)

        # 包含特殊字符
        result = lib.register(
            name="invalid-name!",
            description="无效名",
            code='def execute(**kwargs):\n    return 0\n',
        )
        assert_true(not result["success"], "注册失败")
        assert_true("snake_case" in result["reason"], "原因提到snake_case")
    finally:
        cleanup_dir(tmp_dir)


def test_skill_to_dict():
    """测试19: Skill.to_dict 完整性"""
    print("\n--- 测试19: Skill.to_dict 完整性 ---")
    skill = Skill(
        name="test",
        description="测试",
        code='def execute(**kwargs):\n    return 0\n',
    )
    d = skill.to_dict()
    expected_keys = {
        "name", "description", "version", "validated",
        "created_at", "last_used", "invoke_count",
        "success_count", "failure_count", "success_rate",
        "avg_duration_ms",
    }
    assert_true(expected_keys.issubset(d.keys()), "to_dict包含所有必需字段")


def test_skill_success_rate():
    """测试20: 成功率计算"""
    print("\n--- 测试20: 成功率计算 ---")
    skill = Skill(name="t", description="t", code="")
    assert_eq(skill.success_rate(), 0.0, "无调用时成功率=0")

    skill.invoke_count = 10
    skill.success_count = 7
    assert_eq(skill.success_rate(), 0.7, "7/10=0.7")


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
    print("阶段2测试：技能库与技能习得")
    print("=" * 70)

    tests = [
        test_skill_library_basic,
        test_skill_validation_syntax_error,
        test_skill_validation_missing_execute,
        test_skill_invoke_success,
        test_skill_invoke_failure,
        test_skill_invoke_nonexistent,
        test_learn_from_requirement_compute,
        test_learn_from_requirement_check,
        test_learn_from_requirement_stats,
        test_learn_from_requirement_convert,
        test_learn_from_requirement_generic,
        test_skill_persistence,
        test_skill_eviction,
        test_skill_version_management,
        test_agent_integration_learn_skill,
        test_agent_integration_use_skill,
        test_agent_get_status_includes_skill,
        test_invalid_skill_name,
        test_skill_to_dict,
        test_skill_success_rate,
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
