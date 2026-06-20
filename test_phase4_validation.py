"""
阶段4真实测试验证测试 — 验证代码自我进化可信

测试目标（第一性原理验证）：
1. TestValidator 真实运行 pytest（不再只 compile）
2. 基线测试 → 修改 → 回归测试 对比机制
3. 测试通过率下降时自动回滚
4. 性能基准对比（退化 >10% 回滚）
5. BugFixer 集成 TestValidator
6. 语法错误被检测
7. 验证报告结构完整
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.test_validator import TestValidator, TestRunResult, BenchmarkResult, ValidationReport


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
# 测试1: TestValidator 真实运行 pytest
# =============================================================================

def test_real_pytest_execution(result: TestResult):
    print(f"\n  --- 测试1: 真实运行 pytest ---")
    validator = TestValidator()

    # 创建一个 pytest 兼容的临时测试文件（无 fixture 参数）
    tmp_dir = tempfile.mkdtemp(prefix="p4_pytest_")
    try:
        test_file = Path(tmp_dir) / "test_sample.py"
        test_file.write_text("""
def test_add():
    assert 1 + 1 == 2

def test_multiply():
    assert 2 * 3 == 6

def test_string():
    assert "hello".upper() == "HELLO"
""", encoding="utf-8")

        test_result = validator.run_test_suite(str(test_file))
        print(f"    total={test_result.total} passed={test_result.passed_count} "
              f"failed={test_result.failed_count} duration={test_result.duration_seconds:.1f}s")

        if test_result.total > 0:
            result.ok(f"pytest 运行成功 (total={test_result.total})")
        else:
            result.fail("pytest 未运行", f"total={test_result.total} output={test_result.output[-200:]}")

        if test_result.passed_count >= 3:
            result.ok(f"有通过的测试 ({test_result.passed_count}个)")
        else:
            result.fail("通过测试不足", f"passed={test_result.passed_count} output={test_result.output[-200:]}")
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =============================================================================
# 测试2: 基线 vs 回归 对比机制
# =============================================================================

def test_baseline_vs_regression(result: TestResult):
    print(f"\n  --- 测试2: 基线 vs 回归对比 ---")
    tmp_dir = tempfile.mkdtemp(prefix="p4_baseline_")
    try:
        # 创建一个简单的被测模块
        module_path = Path(tmp_dir) / "target.py"
        module_path.write_text("""
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
""", encoding="utf-8")

        # 创建测试文件
        test_path = Path(tmp_dir) / "test_target.py"
        test_path.write_text("""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from target import add, multiply

def test_add():
    assert add(2, 3) == 5

def test_multiply():
    assert multiply(2, 3) == 6
""", encoding="utf-8")

        validator = TestValidator()
        validator.test_command = f"{sys.executable} -m pytest"

        # 基线测试
        baseline = validator.run_test_suite(str(test_path))
        print(f"    基线: passed={baseline.passed_count} failed={baseline.failed_count}")

        if baseline.passed_count == 2:
            result.ok(f"基线测试通过 (2/2)")
        else:
            result.fail("基线测试失败", f"passed={baseline.passed_count}")

        # 修改模块（引入bug）
        module_path.write_text("""
def add(a, b):
    return a - b  # BUG: 改成减法

def multiply(a, b):
    return a * b
""", encoding="utf-8")

        # 回归测试
        regression = validator.run_test_suite(str(test_path))
        print(f"    回归: passed={regression.passed_count} failed={regression.failed_count}")

        if regression.failed_count > 0:
            result.ok(f"回归测试检测到失败 ({regression.failed_count}个)")
        else:
            result.fail("回归未检测到失败", "修改引入bug但测试仍通过")

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =============================================================================
# 测试3: 测试通过率下降时自动回滚
# =============================================================================

def test_auto_rollback_on_regression(result: TestResult):
    print(f"\n  --- 测试3: 回归自动回滚 ---")
    tmp_dir = tempfile.mkdtemp(prefix="p4_rollback_")
    try:
        module_path = Path(tmp_dir) / "target.py"
        original_source = """
def compute(x):
    return x * 2
"""
        module_path.write_text(original_source, encoding="utf-8")

        test_path = Path(tmp_dir) / "test_target.py"
        test_path.write_text("""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from target import compute

def test_compute():
    assert compute(5) == 10
""", encoding="utf-8")

        validator = TestValidator()
        validator.test_command = f"{sys.executable} -m pytest"

        # 引入bug的修改
        buggy_source = """
def compute(x):
    return x * 3  # BUG: 改成乘3
"""

        report = validator.validate_change(
            file_path=module_path,
            patched_source=buggy_source,
            test_path=str(test_path),
        )

        print(f"    verdict={report.verdict} rolled_back={report.rolled_back}")
        print(f"    reason={report.rollback_reason}")

        if report.rolled_back:
            result.ok(f"检测到回归并回滚")
        else:
            result.fail("未回滚", f"verdict={report.verdict}")

        # 验证文件已恢复
        restored = module_path.read_text(encoding="utf-8")
        if "return x * 2" in restored:
            result.ok(f"文件已恢复原内容")
        else:
            result.fail("文件未恢复", f"内容={restored[:50]}")

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =============================================================================
# 测试4: 性能基准对比
# =============================================================================

def test_performance_benchmark(result: TestResult):
    print(f"\n  --- 测试4: 性能基准 ---")
    validator = TestValidator(benchmark_iterations=50)

    def fast_func():
        return sum(range(100))

    def slow_func():
        return sum(range(1000))

    bench_fast = validator.run_benchmark(fast_func)
    bench_slow = validator.run_benchmark(slow_func)

    print(f"    fast: avg={bench_fast.avg_time_ms:.4f}ms")
    print(f"    slow: avg={bench_slow.avg_time_ms:.4f}ms")

    if bench_fast.avg_time_ms < bench_slow.avg_time_ms:
        result.ok(f"性能基准能区分快慢 (fast < slow)")
    else:
        result.fail("性能基准失效", f"fast={bench_fast.avg_time_ms} slow={bench_slow.avg_time_ms}")

    if bench_fast.iterations == 50:
        result.ok(f"迭代次数正确 (50)")
    else:
        result.fail("迭代次数错误", f"={bench_fast.iterations}")


# =============================================================================
# 测试5: 性能退化检测
# =============================================================================

def test_performance_regression_detection(result: TestResult):
    print(f"\n  --- 测试5: 性能退化检测 ---")
    tmp_dir = tempfile.mkdtemp(prefix="p4_perf_")
    try:
        module_path = Path(tmp_dir) / "target.py"
        original_source = """
def compute():
    return sum(range(100))
"""
        module_path.write_text(original_source, encoding="utf-8")

        validator = TestValidator(
            benchmark_iterations=20,
            performance_regression_threshold=0.10,
        )

        # 基准函数：直接读文件+exec（避免import缓存问题）
        def benchmark_func():
            source = module_path.read_text(encoding="utf-8")
            ns = {}
            exec(source, ns)
            ns["compute"]()

        # 引入性能退化（修改后：慢很多倍）
        slow_source = """
def compute():
    result = 0
    for _ in range(100):
        result += sum(range(100))
    return result
"""
        # 创建测试文件
        test_path = Path(tmp_dir) / "test_target.py"
        test_path.write_text("""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from target import compute

def test_compute():
    assert compute() is not None
""", encoding="utf-8")

        report = validator.validate_change(
            file_path=module_path,
            patched_source=slow_source,
            test_path=str(test_path),
            benchmark_func=benchmark_func,
        )

        print(f"    verdict={report.verdict} perf_regression={report.performance_regression}")
        if report.baseline_benchmark and report.post_change_benchmark:
            print(f"    baseline avg={report.baseline_benchmark.avg_time_ms:.4f}ms")
            print(f"    post avg={report.post_change_benchmark.avg_time_ms:.4f}ms")

        if report.performance_regression:
            result.ok(f"检测到性能退化")
        else:
            result.fail("未检测到性能退化",
                        f"baseline={report.baseline_benchmark.avg_time_ms if report.baseline_benchmark else 0} "
                        f"post={report.post_change_benchmark.avg_time_ms if report.post_change_benchmark else 0}")

        if report.rolled_back:
            result.ok(f"性能退化触发回滚")
        else:
            result.fail("性能退化未回滚", f"verdict={report.verdict}")

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =============================================================================
# 测试6: 语法错误检测
# =============================================================================

def test_syntax_error_detection(result: TestResult):
    print(f"\n  --- 测试6: 语法错误检测 ---")
    validator = TestValidator()

    # 正确代码
    valid_source = "def foo():\n    return 1\n"
    r1 = validator.quick_validate(valid_source)
    if r1.passed:
        result.ok(f"正确代码通过验证")
    else:
        result.fail("正确代码误报", str(r1.errors))

    # 语法错误代码
    invalid_source = "def foo(\n    return 1\n"  # 缺少冒号
    r2 = validator.quick_validate(invalid_source)
    if not r2.passed:
        result.ok(f"语法错误被检测")
    else:
        result.fail("语法错误未检测", "invalid code passed")


# =============================================================================
# 测试7: 验证报告结构完整
# =============================================================================

def test_validation_report_structure(result: TestResult):
    print(f"\n  --- 测试7: 验证报告结构 ---")
    tmp_dir = tempfile.mkdtemp(prefix="p4_report_")
    try:
        module_path = Path(tmp_dir) / "target.py"
        module_path.write_text("def foo():\n    return 1\n", encoding="utf-8")

        validator = TestValidator()
        report = validator.validate_change(
            file_path=module_path,
            patched_source="def foo():\n    return 2\n",
        )

        required_fields = ["file_path", "baseline_tests", "post_change_tests",
                           "tests_regression", "performance_regression",
                           "rolled_back", "rollback_reason", "verdict"]
        missing = [f for f in required_fields if not hasattr(report, f)]
        if not missing:
            result.ok(f"报告字段完整 ({len(required_fields)}个)")
        else:
            result.fail("字段缺失", str(missing))

        if report.verdict in ["approved", "rejected", "rolled_back"]:
            result.ok(f"verdict 合法 ({report.verdict})")
        else:
            result.fail("verdict 非法", report.verdict)

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =============================================================================
# 测试8: BugFixer 集成 TestValidator
# =============================================================================

def test_bugfixer_integration(result: TestResult):
    print(f"\n  --- 测试8: BugFixer 集成 TestValidator ---")
    from core.bug_fixer import BugFixer

    # 不带 validator（兼容旧接口）
    fixer1 = BugFixer()
    if not hasattr(fixer1, "_test_validator") or fixer1._test_validator is None:
        result.ok(f"BugFixer 无 validator 时兼容旧接口")
    else:
        result.fail("兼容性破坏", "不应有 validator")

    # 带 validator
    validator = TestValidator()
    fixer2 = BugFixer(test_validator=validator)
    if fixer2._test_validator is validator:
        result.ok(f"BugFixer 集成 TestValidator")
    else:
        result.fail("集成失败", "validator 未注入")

    # run_tests 应使用 validator
    test_result = fixer2.run_tests("def foo():\n    return 1\n")
    if test_result["passed"]:
        result.ok(f"run_tests 正确验证代码")
    else:
        result.fail("run_tests 失败", str(test_result))


# =============================================================================
# 测试9: 修改通过验证时保留
# =============================================================================

def test_approved_change_kept(result: TestResult):
    print(f"\n  --- 测试9: 通过验证的修改保留 ---")
    tmp_dir = tempfile.mkdtemp(prefix="p4_approve_")
    try:
        module_path = Path(tmp_dir) / "target.py"
        original = "def foo():\n    return 1\n"
        module_path.write_text(original, encoding="utf-8")

        validator = TestValidator()
        # 安全的修改（不引入回归）
        safe_change = "def foo():\n    return 2\n"
        report = validator.validate_change(
            file_path=module_path,
            patched_source=safe_change,
        )

        if report.verdict == "approved":
            result.ok(f"安全修改被批准")
        else:
            result.fail("安全修改被拒", f"verdict={report.verdict}")

        if not report.rolled_back:
            result.ok(f"未回滚（保留修改）")
        else:
            result.fail("误回滚", "安全修改不应回滚")

        # 文件应是修改后的内容
        content = module_path.read_text(encoding="utf-8")
        if "return 2" in content:
            result.ok(f"文件保留修改后内容")
        else:
            result.fail("文件未保留修改", content[:50])

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# =============================================================================
# 测试10: pytest 输出解析
# =============================================================================

def test_pytest_output_parsing(result: TestResult):
    print(f"\n  --- 测试10: pytest 输出解析 ---")
    validator = TestValidator()

    # 模拟 pytest 输出
    fake_output = """
test_phase1_integration.py::test_basic_routing PASSED
test_phase1_integration.py::test_cpu_critical_triggers_healing PASSED
test_phase1_integration.py::test_dry_run_safety FAILED
=== 2 passed, 1 failed in 3.5s ===
"""
    passed, failed, errors = validator._parse_pytest_output(fake_output)
    if passed == 2 and failed == 1:
        result.ok(f"解析正确 (passed=2 failed=1)")
    else:
        result.fail("解析错误", f"passed={passed} failed={failed}")

    # 测试 errors 解析
    fake_output2 = "=== 5 passed, 2 failed, 1 error in 4.0s ==="
    passed2, failed2, errors2 = validator._parse_pytest_output(fake_output2)
    if passed2 == 5 and failed2 == 2 and errors2 == 1:
        result.ok(f"解析含errors (passed=5 failed=2 error=1)")
    else:
        result.fail("errors解析错误", f"passed={passed2} failed={failed2} error={errors2}")


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
    print("  阶段4真实测试验证测试 — 代码自我进化可信")
    print("=" * 60)

    result = TestResult()
    test_real_pytest_execution(result)
    test_baseline_vs_regression(result)
    test_auto_rollback_on_regression(result)
    test_performance_benchmark(result)
    test_performance_regression_detection(result)
    test_syntax_error_detection(result)
    test_validation_report_structure(result)
    test_bugfixer_integration(result)
    test_approved_change_kept(result)
    test_pytest_output_parsing(result)

    _cleanup_persistent_state()
    print("\n" + "=" * 60)
    result.summary()
    print("=" * 60)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
