"""
测试验证器

第一性原理：生物进化有"自然选择"——变异必须经过环境检验才能留存。
代码自我进化必须有等价的"测试门禁"：
1. 修改前基线测试 → 记录通过率
2. 修改后回归测试 → 对比通过率不下降
3. 性能基准对比 → 退化则回滚
4. 自动回滚 → 测试失败/性能退化时恢复 .bak

设计原则：
- 真实运行 pytest（不再只 compile）
- 基线对比：修改后通过率必须 >= 修改前
- 性能基准：关键函数执行时间退化 >10% 则回滚
- 安全回滚：任何失败都自动恢复原文件
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TestRunResult:
    """测试运行结果"""
    passed: bool
    total: int = 0
    passed_count: int = 0
    failed_count: int = 0
    error_count: int = 0
    duration_seconds: float = 0.0
    output: str = ""
    errors: List[str] = field(default_factory=list)


@dataclass
class BenchmarkResult:
    """性能基准结果"""
    function_name: str
    iterations: int
    total_time_seconds: float
    avg_time_ms: float
    min_time_ms: float
    max_time_ms: float


@dataclass
class ValidationReport:
    """验证报告"""
    file_path: str
    baseline_tests: Optional[TestRunResult] = None
    post_change_tests: Optional[TestRunResult] = None
    baseline_benchmark: Optional[BenchmarkResult] = None
    post_change_benchmark: Optional[BenchmarkResult] = None
    tests_regression: bool = False      # 测试通过率下降
    performance_regression: bool = False  # 性能退化 >10%
    rolled_back: bool = False
    rollback_reason: str = ""
    verdict: str = ""  # approved/rejected/rolled_back


class TestValidator:
    """
    测试验证器

    真实运行 pytest + 性能基准，确保代码修改不引入回归。
    """

    def __init__(self,
                 test_command: Optional[str] = None,
                 benchmark_iterations: int = 100,
                 performance_regression_threshold: float = 0.10):
        """
        Args:
            test_command: 测试命令（默认用 pytest）
            benchmark_iterations: 性能基准迭代次数
            performance_regression_threshold: 性能退化阈值（10%=0.10）
        """
        self.test_command = test_command or f"{sys.executable} -m pytest"
        self.benchmark_iterations = benchmark_iterations
        self.regression_threshold = performance_regression_threshold

    def run_test_suite(self, test_path: Optional[str] = None) -> TestRunResult:
        """
        真实运行测试套件

        Args:
            test_path: 测试文件/目录路径（None=运行全部）

        Returns:
            TestRunResult: 含通过/失败计数
        """
        cmd = self.test_command
        if test_path:
            cmd = f"{cmd} {test_path}"
        cmd += " -v --tb=short 2>&1"

        start = time.time()
        try:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=120
            )
            duration = time.time() - start
            output = proc.stdout + proc.stderr

            # 解析 pytest 输出：通常最后一行类似 "=== 30 passed, 2 failed in 5.3s ==="
            passed_count, failed_count, error_count = self._parse_pytest_output(output)
            total = passed_count + failed_count + error_count

            return TestRunResult(
                passed=(failed_count == 0 and error_count == 0 and proc.returncode == 0),
                total=total,
                passed_count=passed_count,
                failed_count=failed_count,
                error_count=error_count,
                duration_seconds=duration,
                output=output[-2000:],  # 保留最后2000字符
            )
        except subprocess.TimeoutExpired:
            return TestRunResult(
                passed=False, duration_seconds=120,
                errors=["测试超时（120秒）"],
            )
        except Exception as e:
            return TestRunResult(
                passed=False, errors=[f"{type(e).__name__}: {e}"],
            )

    def _parse_pytest_output(self, output: str) -> Tuple[int, int, int]:
        """解析 pytest 输出，提取 passed/failed/error 计数"""
        passed = failed = errors = 0
        for line in output.split("\n"):
            line_lower = line.lower()
            if "passed" in line_lower and ("=" in line or "summary" in line_lower):
                # "=== 30 passed ===" or "=== 30 passed, 2 failed in 5.3s ==="
                import re
                p_match = re.search(r'(\d+)\s+passed', line_lower)
                f_match = re.search(r'(\d+)\s+failed', line_lower)
                e_match = re.search(r'(\d+)\s+error', line_lower)
                if p_match:
                    passed = int(p_match.group(1))
                if f_match:
                    failed = int(f_match.group(1))
                if e_match:
                    errors = int(e_match.group(1))
        return passed, failed, errors

    def run_benchmark(self, func, *args, **kwargs) -> BenchmarkResult:
        """
        运行性能基准

        Args:
            func: 要基准的函数
            *args, **kwargs: 函数参数

        Returns:
            BenchmarkResult: 含平均/最小/最大执行时间
        """
        times = []
        for _ in range(self.benchmark_iterations):
            start = time.perf_counter()
            try:
                func(*args, **kwargs)
            except Exception:
                pass  # 基准测试忽略功能错误，只测性能
            elapsed = time.perf_counter() - start
            times.append(elapsed)

        total = sum(times)
        avg = total / len(times) if times else 0
        return BenchmarkResult(
            function_name=getattr(func, "__name__", "unknown"),
            iterations=len(times),
            total_time_seconds=total,
            avg_time_ms=avg * 1000,
            min_time_ms=min(times) * 1000 if times else 0,
            max_time_ms=max(times) * 1000 if times else 0,
        )

    def validate_change(self,
                        file_path: Path,
                        patched_source: str,
                        test_path: Optional[str] = None,
                        benchmark_func=None) -> ValidationReport:
        """
        完整验证流程：基线测试 → 应用修改 → 回归测试 → 性能对比 → 决策

        流程：
            1. 运行基线测试（修改前）
            2. 运行基线性能基准（修改前）
            3. 应用修改（备份原文件）
            4. 运行回归测试（修改后）
            5. 运行回归性能基准（修改后）
            6. 对比：测试通过率下降 OR 性能退化 >10% → 回滚
            7. 通过则保留修改，否则恢复原文件

        Returns:
            ValidationReport: 含完整验证报告
        """
        report = ValidationReport(file_path=str(file_path))

        if not file_path.exists():
            report.verdict = "rejected"
            report.rollback_reason = "文件不存在"
            return report

        original_source = file_path.read_text(encoding="utf-8")

        # 1. 基线测试（修改前）
        print(f"  [TestValidator] 运行基线测试...")
        report.baseline_tests = self.run_test_suite(test_path)
        print(f"  [TestValidator] 基线: passed={report.baseline_tests.passed_count} "
              f"failed={report.baseline_tests.failed_count}")

        # 2. 基线性能基准（修改前）
        if benchmark_func is not None:
            print(f"  [TestValidator] 运行基线性能基准...")
            report.baseline_benchmark = self.run_benchmark(benchmark_func)
            print(f"  [TestValidator] 基线性能: avg={report.baseline_benchmark.avg_time_ms:.3f}ms")

        # 3. 应用修改（先备份）
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        backup_path.write_text(original_source, encoding="utf-8")
        file_path.write_text(patched_source, encoding="utf-8")
        print(f"  [TestValidator] 已应用修改，备份在 {backup_path.name}")

        # 4. 回归测试（修改后）
        print(f"  [TestValidator] 运行回归测试...")
        report.post_change_tests = self.run_test_suite(test_path)
        print(f"  [TestValidator] 回归: passed={report.post_change_tests.passed_count} "
              f"failed={report.post_change_tests.failed_count}")

        # 5. 回归性能基准（修改后）
        if benchmark_func is not None:
            print(f"  [TestValidator] 运行回归性能基准...")
            report.post_change_benchmark = self.run_benchmark(benchmark_func)
            print(f"  [TestValidator] 回归性能: avg={report.post_change_benchmark.avg_time_ms:.3f}ms")

        # 6. 对比决策
        # 测试回归：修改后通过率 < 修改前
        if report.baseline_tests and report.post_change_tests:
            baseline_pass_rate = (report.baseline_tests.passed_count /
                                  max(report.baseline_tests.total, 1))
            post_pass_rate = (report.post_change_tests.passed_count /
                              max(report.post_change_tests.total, 1))
            if post_pass_rate < baseline_pass_rate:
                report.tests_regression = True
                report.rollback_reason = (
                    f"测试通过率下降: {baseline_pass_rate:.1%} → {post_pass_rate:.1%}"
                )

        # 性能回归：修改后比修改前慢 >10%
        if report.baseline_benchmark and report.post_change_benchmark:
            baseline_avg = report.baseline_benchmark.avg_time_ms
            post_avg = report.post_change_benchmark.avg_time_ms
            if baseline_avg > 0:
                degradation = (post_avg - baseline_avg) / baseline_avg
                if degradation > self.regression_threshold:
                    report.performance_regression = True
                    reason = f"性能退化 {degradation:.1%} > {self.regression_threshold:.0%}"
                    report.rollback_reason = (
                        f"{report.rollback_reason}; {reason}" if report.rollback_reason else reason
                    )

        # 7. 决策：有回归则回滚
        if report.tests_regression or report.performance_regression:
            print(f"  [TestValidator] 检测到回归，回滚: {report.rollback_reason}")
            file_path.write_text(original_source, encoding="utf-8")
            report.rolled_back = True
            report.verdict = "rolled_back"
        else:
            print(f"  [TestValidator] 验证通过，保留修改")
            report.verdict = "approved"

        # 清理备份（验证通过后保留备份供人工复查，验证失败已恢复原文件）
        return report

    def quick_validate(self, source: str) -> TestRunResult:
        """
        快速语法验证（只 compile，不运行测试）

        用于修改前的快速预检。
        """
        try:
            compile(source, "<quick_validate>", "exec")
            return TestRunResult(passed=True, total=1, passed_count=1)
        except SyntaxError as e:
            return TestRunResult(
                passed=False, errors=[f"Line {e.lineno}: {e.msg}"]
            )
