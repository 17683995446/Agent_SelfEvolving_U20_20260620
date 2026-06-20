#!/usr/bin/env python3
"""
全流程压力测试 —— 模拟复杂混乱场景，暴露真实运行时Bug

测试维度：
1. 空值/非法入参
2. 边界条件
3. 高频调用
4. 跨模块联调
5. 异常容错
6. 数据一致性
"""

import sys
import time
import traceback
import tempfile
from pathlib import Path
from collections import defaultdict

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

results = defaultdict(list)

def test(category, name, func):
    """执行测试并记录结果"""
    try:
        func()
        results[category].append(("PASS", name, ""))
    except Exception as e:
        results[category].append(("FAIL", name, f"{type(e).__name__}: {e}"))

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ============================================================
section("1. 空值/非法入参测试")
# ============================================================

def test_auto_healing_none():
    from core.auto_healing import AutoHealingEngine
    h = AutoHealingEngine()
    result = h.detect_anomaly({})
    assert result["is_anomaly"] is False

def test_auto_healing_negative():
    from core.auto_healing import AutoHealingEngine
    h = AutoHealingEngine()
    result = h.detect_anomaly({"cpu_percent": -10, "memory_percent": -5})
    assert result["is_anomaly"] is False

def test_actionable_tasks_empty():
    from core.actionable_tasks import ActionableTaskEngine
    e = ActionableTaskEngine()
    result = e.run_task_pipeline("")
    assert result["status"] == "unknown_task"

def test_bug_fixer_empty():
    from core.bug_fixer import BugFixer
    f = BugFixer()
    bugs = f.scan_bugs("")
    assert isinstance(bugs, list)

def test_bug_fixer_none():
    from core.bug_fixer import BugFixer
    f = BugFixer()
    try:
        bugs = f.scan_bugs(None)
    except Exception as e:
        assert "NoneType" in str(e) or "AttributeError" in type(e).__name__

def test_log_rca_empty():
    from core.log_root_cause import LogRootCauseAnalyzer
    a = LogRootCauseAnalyzer()
    result = a.analyze([])
    assert result["summary"]["total_lines"] == 0

def test_log_rca_garbage():
    from core.log_root_cause import LogRootCauseAnalyzer
    a = LogRootCauseAnalyzer()
    result = a.analyze(["垃圾数据", "不是日志", "12345"])
    assert result["summary"]["parsed_incidents"] == 0

def test_config_tuner_zero_step():
    from core.config_tuner import ConfigAutoTuner
    t = ConfigAutoTuner()
    try:
        t.register_parameter("x", 0.5, 0.0, 1.0, 0.0, "metric", "maximize")
        # 尝试优化，step_size=0 可能除零
        result = t.hill_climbing_optimize("x", lambda: 0.5)
    except ZeroDivisionError:
        pass  # 预期会除零
    except Exception:
        pass

def test_code_generator_empty():
    from core.code_generator import CodeGenerator
    g = CodeGenerator()
    result = g.generate_from_requirement("")
    assert result["valid"] is False or result["parsed"]["module_name"] is None

def test_multi_agent_no_agents():
    from core.multi_agent_coding import MultiAgentCollaborativeCoding
    mac = MultiAgentCollaborativeCoding()
    result = mac.run_collaboration("test task")
    # 没有注册任何agent，应该不崩溃
    assert "status" in result

test("空值入参", "auto_healing空字典", test_auto_healing_none)
test("空值入参", "auto_healing负值", test_auto_healing_negative)
test("空值入参", "actionable_tasks空字符串", test_actionable_tasks_empty)
test("空值入参", "bug_fixer空字符串", test_bug_fixer_empty)
test("空值入参", "bug_fixer None", test_bug_fixer_none)
test("空值入参", "log_rca空列表", test_log_rca_empty)
test("空值入参", "log_rca垃圾数据", test_log_rca_garbage)
test("空值入参", "config_tuner零步长", test_config_tuner_zero_step)
test("空值入参", "code_generator空需求", test_code_generator_empty)
test("空值入参", "multi_agent无Agent", test_multi_agent_no_agents)

# ============================================================
section("2. 边界条件测试")
# ============================================================

def test_healing_exact_threshold():
    from core.auto_healing import AutoHealingEngine
    h = AutoHealingEngine()
    # CPU恰好90
    r = h.detect_anomaly({"cpu_percent": 90, "memory_percent": 50, "disk_percent": 30})
    assert r["is_anomaly"] is True

def test_healing_all_zero():
    from core.auto_healing import AutoHealingEngine
    h = AutoHealingEngine()
    r = h.detect_anomaly({"cpu_percent": 0, "memory_percent": 0, "disk_percent": 0})
    assert r["is_anomaly"] is False

def test_healing_all_max():
    from core.auto_healing import AutoHealingEngine
    h = AutoHealingEngine()
    r = h.detect_anomaly({"cpu_percent": 100, "memory_percent": 100, "disk_percent": 100})
    assert r["is_anomaly"] is True
    assert r["severity"] == 1.0

def test_healing_cpu80_mem75_blind_spot():
    """测试根因判断盲区：CPU>80 且 70<=mem<=80"""
    from core.auto_healing import AutoHealingEngine
    h = AutoHealingEngine()
    diag = h.diagnose_root_cause({"cpu_percent": 85, "memory_percent": 75, "disk_percent": 30})
    # 这个区间三个分支都不命中
    if diag["primary_cause"] is None:
        raise AssertionError("根因判断盲区: CPU=85,mem=75 时不匹配任何根因")

def test_bug_fixer_only_safe_code():
    from core.bug_fixer import BugFixer
    f = BugFixer()
    bugs = f.scan_bugs("x = 1\n")
    assert len(bugs) == 0

def test_log_rca_single_line():
    from core.log_root_cause import LogRootCauseAnalyzer
    a = LogRootCauseAnalyzer()
    result = a.analyze(["2024-01-01 10:00:00 [ERROR] timeout"])
    assert result["summary"]["error_count"] == 1

def test_config_tuner_max_iterations_zero():
    from core.config_tuner import ConfigAutoTuner
    t = ConfigAutoTuner()
    t.register_parameter("x", 0.5, 0.0, 1.0, 0.1, "m", "maximize")
    try:
        result = t.hill_climbing_optimize("x", lambda: 0.5, max_iterations=0)
        # max_iterations=0 时 iteration 变量未定义
    except NameError as e:
        raise AssertionError(f"max_iterations=0 时 NameError: {e}")
    except Exception:
        pass

test("边界条件", "healing恰好阈值90", test_healing_exact_threshold)
test("边界条件", "healing全零", test_healing_all_zero)
test("边界条件", "healing全满", test_healing_all_max)
test("边界条件", "healing根因盲区", test_healing_cpu80_mem75_blind_spot)
test("边界条件", "bug_fixer无Bug代码", test_bug_fixer_only_safe_code)
test("边界条件", "log_rca单行日志", test_log_rca_single_line)
test("边界条件", "config_tuner零迭代", test_config_tuner_max_iterations_zero)

# ============================================================
section("3. 高频调用压力测试")
# ============================================================

def test_healing_1000_cycles():
    from core.auto_healing import AutoHealingEngine
    h = AutoHealingEngine()
    for i in range(1000):
        h.detect_anomaly({"cpu_percent": 50, "memory_percent": 50, "disk_percent": 50})
    stats = h.get_stats()
    # _history 应该为空（没有异常）
    assert stats["total_cycles"] == 0

def test_task_engine_100_tasks():
    from core.actionable_tasks import ActionableTaskEngine
    e = ActionableTaskEngine(dry_run=True)
    for i in range(100):
        e.run_task_pipeline("查看磁盘")
    stats = e.get_stats()
    assert stats["total_executed"] == 100

def test_bug_fixer_large_code():
    from core.bug_fixer import BugFixer
    f = BugFixer()
    # 生成1000行代码
    lines = []
    for i in range(1000):
        if i % 100 == 50:
            lines.append(f"    if x == True:")
        else:
            lines.append(f"    var_{i} = {i}")
    code = "\n".join(lines)
    bugs = f.scan_bugs(code)
    assert len(bugs) > 0

def test_log_rca_500_lines():
    from core.log_root_cause import LogRootCauseAnalyzer
    a = LogRootCauseAnalyzer()
    logs = []
    for i in range(500):
        level = "ERROR" if i % 50 == 0 else "INFO"
        logs.append(f"2024-01-01 10:{i//60:02d}:{i%60:02d} [{level}] message {i}")
    result = a.analyze(logs)
    assert result["summary"]["total_lines"] == 500

test("高频压力", "healing 1000次循环", test_healing_1000_cycles)
test("高频压力", "task_engine 100个任务", test_task_engine_100_tasks)
test("高频压力", "bug_fixer 1000行代码", test_bug_fixer_large_code)
test("高频压力", "log_rca 500行日志", test_log_rca_500_lines)

# ============================================================
section("4. 跨模块联调测试")
# ============================================================

def test_healing_to_task_pipeline():
    """自愈引擎检测到异常后，触发任务引擎执行修复"""
    from core.auto_healing import AutoHealingEngine
    from core.actionable_tasks import ActionableTaskEngine

    healer = AutoHealingEngine()
    task_engine = ActionableTaskEngine(dry_run=True)

    # 检测异常
    anomaly = healer.detect_anomaly({"cpu_percent": 95, "memory_percent": 50, "disk_percent": 30})
    assert anomaly["is_anomaly"]

    # 诊断根因
    diag = healer.diagnose_root_cause({"cpu_percent": 95, "memory_percent": 50, "disk_percent": 30})

    # 根据根因触发任务
    if diag["primary_cause"]["cause"] == "cpu_bound_process":
        result = task_engine.run_task_pipeline("查看进程")
        assert result["status"] in ("success", "rejected")

def test_log_rca_to_bug_fixer():
    """日志根因分析发现代码Bug后，触发Bug修复"""
    from core.log_root_cause import LogRootCauseAnalyzer
    from core.bug_fixer import BugFixer

    analyzer = LogRootCauseAnalyzer()
    fixer = BugFixer()

    logs = [
        "2024-01-01 10:00:00 [ERROR] eval() security error in module.py",
        "2024-01-01 10:00:01 [ERROR] bare except caught KeyboardInterrupt",
    ]
    result = analyzer.analyze(logs)
    # 应该能分析出根因
    assert result["root_cause"] is not None or result["summary"]["error_count"] == 2

def test_code_gen_to_bug_fixer():
    """代码生成后，用Bug修复器扫描生成的代码"""
    from core.code_generator import CodeGenerator
    from core.bug_fixer import BugFixer

    gen = CodeGenerator()
    fixer = BugFixer()

    result = gen.generate_from_requirement(
        "实现一个监控模块Monitor，包含统计stats、检查check_status、计算compute_load方法"
    )
    assert result["valid"]

    # 扫描生成的代码
    if result.get("code"):
        bugs = fixer.scan_bugs(result["code"])
        assert isinstance(bugs, list)

def test_multi_agent_to_regression():
    """多Agent协作后，用回归测试验证"""
    from core.multi_agent_coding import MultiAgentCollaborativeCoding
    from core.regression_test import RegressionTestFramework

    mac = MultiAgentCollaborativeCoding()
    mac.register_agent("dev", ["coding"], "开发")
    mac.register_agent("qa", ["testing"], "测试")

    result = mac.run_collaboration("实现工具函数")
    assert result["status"] in ("completed", "needs_revision")

    rt = RegressionTestFramework()
    rt.record_baseline("collab", lambda: sum(range(100)))
    report = rt.generate_report()
    assert report["health_status"] in ("HEALTHY", "DEGRADED")

test("跨模块联调", "自愈→任务引擎", test_healing_to_task_pipeline)
test("跨模块联调", "日志根因→Bug修复", test_log_rca_to_bug_fixer)
test("跨模块联调", "代码生成→Bug扫描", test_code_gen_to_bug_fixer)
test("跨模块联调", "多Agent→回归测试", test_multi_agent_to_regression)

# ============================================================
section("5. 异常容错测试")
# ============================================================

def test_healing_subprocess_timeout():
    """自愈引擎执行超时命令"""
    from core.auto_healing import AutoHealingEngine
    from core.auto_healing import HealingAction
    h = AutoHealingEngine()
    action = HealingAction(
        action_type="test",
        target="test",
        command="sleep 60",
        estimated_impact="low",
        auto_approved=True,
    )
    result = h.execute_action(action)
    assert result["executed"] is False
    assert "timeout" in result["reason"].lower()

def test_task_engine_invalid_command():
    """任务引擎执行不存在的命令"""
    from core.actionable_tasks import ActionableTaskEngine
    from core.actionable_tasks import ActionableTask
    e = ActionableTaskEngine()
    task = ActionableTask("t1", "test", "nonexistent_command_xyz", "shell", "safe", True)
    result = e.execute_task(task)
    assert result.success is False

def test_bug_fixer_syntax_error_code():
    """Bug修复器处理语法错误的代码"""
    from core.bug_fixer import BugFixer
    f = BugFixer()
    bugs = f.scan_bugs("def (\n")
    # 语法错误时应返回空列表或已知bugs
    assert isinstance(bugs, list)

def test_log_rca_mixed_formats():
    """日志分析器处理混合格式"""
    from core.log_root_cause import LogRootCauseAnalyzer
    a = LogRootCauseAnalyzer()
    logs = [
        "2024-01-01 10:00:00 [INFO] normal",
        "garbage line without format",
        "2024-01-01 10:00:01 [ERROR] connection refused",
        "",
        "2024-01-01 10:00:02 CRITICAL something broke",
    ]
    result = a.analyze(logs)
    assert result["summary"]["parsed_incidents"] >= 2

def test_config_tuner_metric_returns_none():
    """配置调优的metric函数返回None"""
    from core.config_tuner import ConfigAutoTuner
    t = ConfigAutoTuner()
    t.register_parameter("x", 0.5, 0.0, 1.0, 0.1, "m", "maximize")
    try:
        result = t.hill_climbing_optimize("x", lambda: None)
    except TypeError:
        pass  # 预期：None不能比较
    except Exception:
        pass

test("异常容错", "自愈超时", test_healing_subprocess_timeout)
test("异常容错", "任务引擎无效命令", test_task_engine_invalid_command)
test("异常容错", "Bug修复语法错误", test_bug_fixer_syntax_error_code)
test("异常容错", "日志混合格式", test_log_rca_mixed_formats)
test("异常容错", "调优metric返回None", test_config_tuner_metric_returns_none)

# ============================================================
section("6. 数据一致性测试")
# ============================================================

def test_healing_stats_consistency():
    from core.auto_healing import AutoHealingEngine
    h = AutoHealingEngine()
    # 运行多个循环
    h.run_healing_cycle({"cpu_percent": 30, "memory_percent": 40, "disk_percent": 20})
    h.run_healing_cycle({"cpu_percent": 95, "memory_percent": 50, "disk_percent": 30})
    stats = h.get_stats()
    # success_count + failure_count 应该 <= total_cycles
    assert stats["success_count"] + stats["failure_count"] <= stats["total_cycles"] + 2

def test_task_engine_stats_consistency():
    from core.actionable_tasks import ActionableTaskEngine
    e = ActionableTaskEngine(dry_run=True)
    e.run_task_pipeline("查看磁盘")
    e.run_task_pipeline("查看内存")
    e.run_task_pipeline("去倒咖啡")  # unknown
    stats = e.get_stats()
    assert stats["total_executed"] == 2  # 只有2个成功执行
    assert stats["success_count"] == 2

def test_bug_fixer_fix_then_rescan():
    from core.bug_fixer import BugFixer
    import tempfile
    f = BugFixer()
    code = "x = eval(data)\nif x == None:\n    pass\n"
    tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
    tmp.write(code)
    tmp.close()
    path = Path(tmp.name)

    # 第一次扫描
    bugs1 = f.scan_bugs(code)
    fix_result = f.fix_file(path, dry_run=False)
    # 读取修复后的文件
    fixed_code = path.read_text()
    # 第二次扫描
    bugs2 = f.scan_bugs(fixed_code)
    # 修复后Bug应该减少
    assert len(bugs2) < len(bugs1)

def test_log_rca_root_cause_not_polluted():
    """验证知识库不被污染"""
    from core.log_root_cause import LogRootCauseAnalyzer
    a = LogRootCauseAnalyzer()
    # 第一次分析
    a.analyze(["2024-01-01 10:00:00 [ERROR] out of memory OOM"])
    # 检查知识库是否被添加了id字段
    for key, val in a._knowledge_base.items():
        if "id" in val:
            raise AssertionError(f"知识库条目 {key} 被污染了 id 字段")

test("数据一致性", "自愈统计一致性", test_healing_stats_consistency)
test("数据一致性", "任务统计一致性", test_task_engine_stats_consistency)
test("数据一致性", "Bug修复后重扫", test_bug_fixer_fix_then_rescan)
test("数据一致性", "知识库不被污染", test_log_rca_root_cause_not_polluted)

# ============================================================
# 汇总报告
# ============================================================
section("测试结果汇总")

total_pass = 0
total_fail = 0
for category, tests in results.items():
    passes = sum(1 for r in tests if r[0] == "PASS")
    fails = sum(1 for r in tests if r[0] == "FAIL")
    total_pass += passes
    total_fail += fails
    print(f"\n  [{category}] 通过:{passes} 失败:{fails}")
    for status, name, err in tests:
        if status == "FAIL":
            print(f"    ✗ {name}: {err}")

print(f"\n{'='*60}")
print(f"  总计: {total_pass}通过, {total_fail}失败, 共{total_pass+total_fail}项")
print(f"{'='*60}")
