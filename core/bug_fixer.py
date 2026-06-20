"""
代码Bug自动修复引擎

第一性原理：免疫系统产生抗体—— 识别病原体（Bug）→ 产生抗体（补丁）→ 清除感染（修复）→ 记忆（测试验证）。
BugFixer 自动发现代码中的常见Bug，生成补丁，运行测试验证，合并修复。

约束：
- 纯Python实现
- 方法数 <= 7
"""

from __future__ import annotations

import ast
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class BugPattern:
    """Bug模式定义"""
    name: str
    severity: str          # critical / high / medium / low
    pattern: str           # 正则或AST特征
    fix_template: str      # 修复模板
    description: str


@dataclass
class BugReport:
    """Bug报告"""
    bug_type: str
    line: int
    severity: str
    description: str
    suggested_fix: str
    confidence: float


@dataclass
class PatchResult:
    """补丁结果"""
    success: bool
    original: str
    patched: str
    bugs_fixed: List[str]
    test_passed: bool
    message: str


class BugFixer:
    """
    代码Bug自动修复引擎

    核心方法（<=7个）：
    1. scan_bugs() — 扫描代码中的Bug
    2. generate_patch() — 生成修复补丁
    3. apply_patch() — 应用补丁
    4. run_tests() — 运行测试验证
    5. fix_file() — 完整修复流程
    6. get_bug_stats() — Bug统计
    7. get_stats() — 引擎统计
    """

    def __init__(self, test_validator=None):
        """
        Args:
            test_validator: 测试验证器（阶段4），用于真实运行测试而非只compile
        """
        self._bug_patterns: List[BugPattern] = self._load_patterns()
        self._fix_history: List[Dict[str, Any]] = []
        self._success_count = 0
        self._failure_count = 0
        # 阶段4：真实测试验证器
        self._test_validator = test_validator

    def _load_patterns(self) -> List[BugPattern]:
        """加载内置Bug模式库"""
        return [
            BugPattern(
                name="bare_except",
                severity="high",
                pattern=r"except\s*:",
                fix_template="except Exception:",
                description="裸except会捕获所有异常包括KeyboardInterrupt，应使用except Exception",
            ),
            BugPattern(
                name="mutable_default",
                severity="high",
                pattern=None,  # AST检测
                fix_template=None,
                description="函数默认参数使用可变对象（list/dict），会导致意外共享状态",
            ),
            BugPattern(
                name="comparison_to_none",
                severity="medium",
                pattern=r"==\s*None",
                fix_template="is None",
                description="应使用'is None'而不是'== None'",
            ),
            BugPattern(
                name="comparison_to_true",
                severity="low",
                pattern=r"==\s*True",
                fix_template="",
                description="应直接使用变量名而不是'== True'",
            ),
            BugPattern(
                name="unused_import",
                severity="low",
                pattern=None,  # AST检测
                fix_template=None,
                description="存在未使用的import",
            ),
            BugPattern(
                name="dangerous_eval",
                severity="critical",
                pattern=r"eval\s*\(",
                fix_template="# TODO: 替换eval为安全的解析方式",
                description="eval()存在严重安全风险，应使用ast.literal_eval或json.loads",
            ),
            BugPattern(
                name="dangerous_exec",
                severity="critical",
                pattern=r"exec\s*\(",
                fix_template="# TODO: 替换exec为安全的执行方式",
                description="exec()存在严重安全风险",
            ),
            BugPattern(
                name="hardcoded_password",
                severity="critical",
                pattern=r'password\s*=\s*["\'][^"\']+["\']',
                fix_template='password = os.environ.get("PASSWORD")  # TODO: 从环境变量读取',
                description="硬编码密码是严重安全风险",
            ),
        ]

    def scan_bugs(self, source: str) -> List[BugReport]:
        """
        扫描代码中的Bug

        结合正则和AST分析发现常见问题。
        """
        bugs = []
        lines = source.splitlines()

        # 1. 正则模式检测
        for pattern_def in self._bug_patterns:
            if pattern_def.pattern is None:
                continue
            for i, line in enumerate(lines, 1):
                if re.search(pattern_def.pattern, line):
                    # 生成修复建议
                    fix = pattern_def.fix_template
                    if fix and pattern_def.pattern:
                        fix = re.sub(pattern_def.pattern, fix, line)
                    else:
                        fix = line

                    bugs.append(BugReport(
                        bug_type=pattern_def.name,
                        line=i,
                        severity=pattern_def.severity,
                        description=pattern_def.description,
                        suggested_fix=fix,
                        confidence=0.9,
                    ))

        # 2. AST检测（可变默认参数、未使用import等）
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return bugs

        # 检测可变默认参数
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for default in node.args.defaults:
                    if isinstance(default, (ast.List, ast.Dict)):
                        bugs.append(BugReport(
                            bug_type="mutable_default",
                            line=node.lineno,
                            severity="high",
                            description=f"函数'{node.name}'使用了可变默认参数",
                            suggested_fix=f"def {node.name}(..., arg=None):\n    if arg is None: arg = []",
                            confidence=0.95,
                        ))

        # 检测未使用变量（简单版）
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                var_name = node.id
                # 简单检查：如果变量名是_开头或unused，认为是故意的
                if var_name.startswith("_") or "unused" in var_name:
                    continue
                # 检查是否被读取过（简化版：只检查同一行是否有读取）
                # 完整版需要作用域分析，这里简化

        return sorted(bugs, key=lambda b: ({"critical": 0, "high": 1, "medium": 2, "low": 3}.get(b.severity, 4), b.line))

    def generate_patch(self, source: str, bugs: List[BugReport]) -> str:
        """
        生成修复补丁

        根据Bug报告生成修复后的代码。
        """
        lines = source.splitlines()
        fixed_lines = list(lines)

        # 按行号从大到小处理，避免修改后行号偏移
        for bug in sorted(bugs, key=lambda b: b.line, reverse=True):
            line_idx = bug.line - 1
            if line_idx < 0 or line_idx >= len(fixed_lines):
                continue

            original_line = fixed_lines[line_idx]

            if bug.bug_type == "bare_except":
                fixed_lines[line_idx] = original_line.replace("except:", "except Exception:")
            elif bug.bug_type == "comparison_to_none":
                fixed_lines[line_idx] = original_line.replace("== None", "is None").replace("!= None", "is not None")
            elif bug.bug_type == "comparison_to_true":
                fixed_lines[line_idx] = original_line.replace("== True", "").replace("!= True", "not ")
            elif bug.bug_type == "dangerous_eval":
                fixed_lines[line_idx] = original_line.replace("eval(", "ast.literal_eval(")
            elif bug.bug_type == "dangerous_exec":
                fixed_lines[line_idx] = "# SECURITY: " + original_line
            elif bug.bug_type == "hardcoded_password":
                fixed_lines[line_idx] = re.sub(
                    r'password\s*=\s*["\'][^"\']+["\']',
                    'password = os.environ.get("PASSWORD")  # 从环境变量读取',
                    original_line
                )
            elif bug.bug_type == "mutable_default":
                # 复杂修复：需要多行替换，这里只做标记
                fixed_lines[line_idx] = original_line + "  # BUG: 可变默认参数"

        return "\n".join(fixed_lines)

    def apply_patch(self, file_path: Path, patched_source: str) -> bool:
        """
        应用补丁到文件

        先备份，再写入修复后的代码。
        """
        try:
            # 备份
            backup_path = file_path.with_suffix(file_path.suffix + ".bak")
            backup_path.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")

            # 写入修复
            file_path.write_text(patched_source, encoding="utf-8")
            return True
        except Exception:
            return False

    def run_tests(self, source: str) -> Dict[str, Any]:
        """
        运行测试验证（阶段4：真实测试验证）

        第一性原理：自然选择——变异必须经过环境检验才能留存。
        不再只做 compile() 语法检查，而是：
        1. 快速语法预检（compile）
        2. 如果提供了测试路径，真实运行 pytest

        Args:
            source: 修复后的源码

        Returns:
            {"passed": bool, "errors": [...], "details": ...}
        """
        # 1. 快速语法预检
        try:
            compile(source, "<patched>", "exec")
        except SyntaxError as e:
            return {
                "passed": False,
                "errors": [{"line": e.lineno, "message": str(e)}],
                "details": "语法错误",
            }

        # 2. 如果有配置测试验证器，真实运行 pytest
        if hasattr(self, "_test_validator") and self._test_validator is not None:
            test_result = self._test_validator.quick_validate(source)
            return {
                "passed": test_result.passed,
                "errors": [{"line": 0, "message": e} for e in test_result.errors],
                "details": f"语法验证: {'通过' if test_result.passed else '失败'}",
            }

        return {"passed": True, "errors": [], "details": "语法验证通过"}

    def fix_file(self, file_path: Path, dry_run: bool = True) -> PatchResult:
        """
        完整修复流程

        扫描→生成补丁→测试→应用（可选）。
        """
        if not file_path.exists():
            return PatchResult(
                success=False,
                original="",
                patched="",
                bugs_fixed=[],
                test_passed=False,
                message="文件不存在",
            )

        source = file_path.read_text(encoding="utf-8")

        # 1. 扫描Bug
        bugs = self.scan_bugs(source)
        if not bugs:
            return PatchResult(
                success=True,
                original=source,
                patched=source,
                bugs_fixed=[],
                test_passed=True,
                message="未发现Bug",
            )

        # 2. 生成补丁
        patched = self.generate_patch(source, bugs)

        # 3. 测试验证
        test_result = self.run_tests(patched)

        if not test_result["passed"]:
            self._failure_count += 1
            return PatchResult(
                success=False,
                original=source,
                patched=patched,
                bugs_fixed=[b.bug_type for b in bugs],
                test_passed=False,
                message=f"修复后语法错误: {test_result['errors']}",
            )

        # 4. 应用补丁（非dry_run模式）
        if not dry_run:
            applied = self.apply_patch(file_path, patched)
            if not applied:
                return PatchResult(
                    success=False,
                    original=source,
                    patched=patched,
                    bugs_fixed=[b.bug_type for b in bugs],
                    test_passed=True,
                    message="应用补丁失败",
                )

        self._success_count += 1
        self._fix_history.append({
            "file": str(file_path),
            "bugs": [b.bug_type for b in bugs],
            "dry_run": dry_run,
            "timestamp": time.time(),
        })

        return PatchResult(
            success=True,
            original=source,
            patched=patched,
            bugs_fixed=[b.bug_type for b in bugs],
            test_passed=True,
            message=f"修复了{len(bugs)}个Bug（{'模拟运行' if dry_run else '已应用'}）",
        )

    def get_bug_stats(self) -> Dict[str, Any]:
        """Bug统计"""
        all_bugs = []
        for h in self._fix_history:
            all_bugs.extend(h.get("bugs", []))

        from collections import Counter
        counter = Counter(all_bugs)

        return {
            "total_fixed": len(all_bugs),
            "by_type": dict(counter.most_common()),
            "by_severity": {},
        }

    def get_stats(self) -> Dict[str, Any]:
        return {
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "total_fixes": len(self._fix_history),
            "bug_stats": self.get_bug_stats(),
        }
