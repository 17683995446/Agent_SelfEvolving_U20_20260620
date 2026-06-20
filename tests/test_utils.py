"""
共享测试工具（秩序化阶段3：测试框架统一）

第一性原理：DRY（Don't Repeat Yourself）。9个测试文件重复定义相同的
assert_true/assert_eq，5个文件重复定义 TestResult 类。提取到共享模块：
1. 统一断言 API（assert_true / assert_eq / assert_ne / assert_gt）
2. 统一 TestResult 类（替代各文件重复定义）
3. 统一 cleanup_persistent_state（替代各文件重复定义）

使用方式：
    from tests.test_utils import assert_true, assert_eq, init_counter, get_counter
    init_counter()  # 每个测试文件 main() 开头调用
    assert_true(cond, "msg")
    print(get_counter())  # 获取 passed/failed
"""

from __future__ import annotations

import glob
import os
from typing import Any, List


# =============================================================================
# 全局计数器（替代各文件的 global passed/failed）
# =============================================================================

_passed = 0
_failed = 0


def init_counter() -> None:
    """初始化测试计数器（每个测试文件 main() 开头调用）"""
    global _passed, _failed
    _passed = 0
    _failed = 0


def get_counter() -> tuple:
    """返回 (passed, failed)"""
    return _passed, _failed


# =============================================================================
# 统一断言函数
# =============================================================================

def assert_true(cond: bool, msg: str) -> None:
    """断言条件为真"""
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  [PASS] {msg}")
    else:
        _failed += 1
        print(f"  [FAIL] {msg}")


def assert_eq(actual: Any, expected: Any, msg: str) -> None:
    """断言相等"""
    assert_true(actual == expected, f"{msg} (expected={expected}, actual={actual})")


def assert_ne(actual: Any, unexpected: Any, msg: str) -> None:
    """断言不相等"""
    assert_true(actual != unexpected, f"{msg} (actual={actual})")


def assert_gt(actual: Any, threshold: Any, msg: str) -> None:
    """断言大于"""
    assert_true(actual > threshold, f"{msg} (expected>{threshold}, actual={actual})")


def assert_ge(actual: Any, threshold: Any, msg: str) -> None:
    """断言大于等于"""
    assert_true(actual >= threshold, f"{msg} (expected>={threshold}, actual={actual})")


def assert_le(actual: Any, threshold: Any, msg: str) -> None:
    """断言小于等于"""
    assert_true(actual <= threshold, f"{msg} (expected<={threshold}, actual={actual})")


# =============================================================================
# 统一 TestResult 类（替代各文件重复定义）
# =============================================================================

class TestResult:
    """测试结果收集器（用于参数化传递风格的测试）"""

    def __init__(self):
        self.passed: int = 0
        self.failed: int = 0
        self.errors: List[str] = []

    def ok(self, name: str) -> None:
        self.passed += 1
        print(f"  [PASS] {name}")

    def fail(self, name: str, reason: str) -> None:
        self.failed += 1
        msg = f"{name}: {reason}"
        self.errors.append(msg)
        print(f"  [FAIL] {msg}")

    def assert_true(self, cond: bool, name: str) -> None:
        if cond:
            self.ok(name)
        else:
            self.fail(name, "条件为假")

    def assert_eq(self, actual: Any, expected: Any, name: str) -> None:
        if actual == expected:
            self.ok(name)
        else:
            self.fail(name, f"expected={expected}, actual={actual}")

    def summary(self) -> None:
        total = self.passed + self.failed
        print(f"\n  通过: {self.passed}, 失败: {self.failed}, 共{total}项")
        for e in self.errors:
            print(f"    - {e}")


# =============================================================================
# 统一持久化状态清理（替代各文件重复定义的 _cleanup_persistent_state）
# =============================================================================

def cleanup_persistent_state() -> None:
    """清理测试产生的持久化状态（秩序化阶段1：测试数据隔离）

    清理范围：
    - data/memory.db（Agent 长期记忆数据库）
    - data/goals_state.json（目标驱动循环状态）
    - data/skills/*.py（习得的技能文件）
    - data/checkpoints/*.json（长任务断点）
    """
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
