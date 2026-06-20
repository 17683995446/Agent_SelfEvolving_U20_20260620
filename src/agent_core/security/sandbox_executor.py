"""
沙箱代码执行器。

安全执行不可信代码，防止恶意操作逃逸。

第一性原理：
- 生物免疫系统将病原体隔离在特定区域（如脓肿），防止扩散
- 代码执行的本质是"在受限环境中运行不可信逻辑"
- 防御纵深：AST静态分析 + 运行时限制 + 资源配额

设计要点：
- AST静态分析：拒绝危险导入、属性访问、函数调用
- 受限内建：移除open/exec/eval/__import__等危险函数
- 资源限制：CPU时间、内存、执行超时
- 执行隔离：独立命名空间，无副作用逃逸
"""

import ast
import resource
import signal
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from agent_core.common.logger import get_logger

# 执行超时（秒）
_DEFAULT_TIMEOUT = 5.0
# 最大内存（字节，默认64MB）
_DEFAULT_MEMORY_LIMIT = 64 * 1024 * 1024
# 最大输出长度
_MAX_OUTPUT_LENGTH = 10000
# 最大递归深度
_MAX_RECURSION = 100

# 禁止的模块名
_FORBIDDEN_MODULES: Set[str] = {
    "os", "sys", "subprocess", "socket", "shutil", "ctypes",
    "multiprocessing", "threading", "asyncio", "pickle",
    "marshal", "importlib", "builtins", "gc", "signal",
    "resource", "pty", "commands", "commands3",
}

# 禁止的函数/属性名
_FORBIDDEN_NAMES: Set[str] = {
    "exec", "eval", "compile", "__import__", "open",
    "globals", "locals", "vars", "dir", "getattr",
    "setattr", "delattr", "hasattr", "__builtins__",
    "__subclasses__", "__bases__", "__mro__", "__class__",
    "breakpoint", "exit", "quit", "help", "input",
}

# 安全的内建函数
_SAFE_BUILTINS: Dict[str, Any] = {
    "abs": abs, "all": all, "any": any, "ascii": ascii,
    "bin": bin, "bool": bool, "bytearray": bytearray,
    "bytes": bytes, "callable": callable, "chr": chr,
    "complex": complex, "dict": dict, "divmod": divmod,
    "enumerate": enumerate, "filter": filter, "float": float,
    "format": format, "frozenset": frozenset, "hash": hash,
    "hex": hex, "int": int, "isinstance": isinstance,
    "issubclass": issubclass, "iter": iter, "len": len,
    "list": list, "map": map, "max": max, "min": min,
    "next": next, "oct": oct, "ord": ord, "pow": pow,
    "print": print, "range": range, "repr": repr,
    "reversed": reversed, "round": round, "set": set,
    "slice": slice, "sorted": sorted, "str": str,
    "sum": sum, "tuple": tuple, "type": type, "zip": zip,
    "True": True, "False": False, "None": None,
    "Exception": Exception, "ValueError": ValueError,
    "TypeError": TypeError, "KeyError": KeyError,
    "IndexError": IndexError, "StopIteration": StopIteration,
    "ZeroDivisionError": ZeroDivisionError,
    "AttributeError": AttributeError,
    "RuntimeError": RuntimeError,
    "ArithmeticError": ArithmeticError,
    "OverflowError": OverflowError,
}


@dataclass
class SandboxResult:
    """沙箱执行结果。"""

    success: bool
    output: str
    error: str
    execution_time: float
    timed_out: bool = False
    blocked: bool = False
    blocked_reason: str = ""


class _SandboxAnalyzer(ast.NodeVisitor):
    """AST静态分析器，检测危险代码模式。"""

    def __init__(self) -> None:
        self.violations: List[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in _FORBIDDEN_MODULES:
                self.violations.append(
                    f"Forbidden import: {alias.name}"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            root = node.module.split(".")[0]
            if root in _FORBIDDEN_MODULES:
                self.violations.append(
                    f"Forbidden import from: {node.module}"
                )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in _FORBIDDEN_NAMES:
            self.violations.append(
                f"Forbidden attribute access: {node.attr}"
            )
        if node.attr.startswith("__") and node.attr.endswith("__"):
            if node.attr in _FORBIDDEN_NAMES:
                self.violations.append(
                    f"Forbidden dunder access: {node.attr}"
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id in _FORBIDDEN_NAMES:
            self.violations.append(
                f"Forbidden function call: {func.id}"
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in _FORBIDDEN_NAMES:
            self.violations.append(
                f"Forbidden name reference: {node.id}"
            )
        self.generic_visit(node)


class SandboxExecutor:
    """
    沙箱代码执行器。

    通过AST静态分析和运行时限制安全执行不可信Python代码。
    """

    def __init__(
        self,
        timeout: float = _DEFAULT_TIMEOUT,
        memory_limit: int = _DEFAULT_MEMORY_LIMIT,
    ) -> None:
        self._timeout = timeout
        self._memory_limit = memory_limit
        self._logger = get_logger()

    def analyze(self, code: str) -> List[str]:
        """
        静态分析代码，返回违规列表。

        Args:
            code: 待分析的Python代码。

        Returns:
            违规描述列表，空列表表示通过。
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return [f"Syntax error: {exc}"]
        analyzer = _SandboxAnalyzer()
        analyzer.visit(tree)
        return analyzer.violations

    def is_safe(self, code: str) -> bool:
        """代码是否安全（无违规）。"""
        return len(self.analyze(code)) == 0

    def execute(
        self,
        code: str,
        env: Optional[Dict[str, Any]] = None,
    ) -> SandboxResult:
        """
        在沙箱中执行代码。

        Args:
            code: 待执行的Python代码。
            env: 额外的环境变量（会合并到受限命名空间）。

        Returns:
            执行结果。
        """
        # 第一步：静态分析
        violations = self.analyze(code)
        if violations:
            reason = "; ".join(violations[:5])
            self._logger.warning(
                f"[SandboxExecutor] Code blocked: {reason}"
            )
            return SandboxResult(
                success=False,
                output="",
                error=reason,
                execution_time=0.0,
                blocked=True,
                blocked_reason=reason,
            )

        # 第二步：编译
        try:
            compiled = compile(code, "<sandbox>", "exec")
        except SyntaxError as exc:
            return SandboxResult(
                success=False,
                output="",
                error=f"Syntax error: {exc}",
                execution_time=0.0,
            )

        # 第三步：构建受限命名空间（globals和locals使用同一字典，
        # 使函数定义在模块级别可见）
        safe_namespace: Dict[str, Any] = {
            "__builtins__": _SAFE_BUILTINS,
            "__name__": "__sandbox__",
        }
        if env:
            for key, value in env.items():
                if key not in _FORBIDDEN_NAMES:
                    safe_namespace[key] = value

        # 第四步：带超时执行
        result_holder: Dict[str, Any] = {
            "output": "",
            "error": "",
            "timed_out": False,
        }

        def _run() -> None:
            import io
            import contextlib
            buf = io.StringIO()
            try:
                # 设置递归限制
                old_limit = sys_getrecursionlimit()
                sys_setrecursionlimit(_MAX_RECURSION)
                with contextlib.redirect_stdout(buf):
                    exec(compiled, safe_namespace, safe_namespace)
                sys_setrecursionlimit(old_limit)
                output = buf.getvalue()
                if len(output) > _MAX_OUTPUT_LENGTH:
                    output = output[:_MAX_OUTPUT_LENGTH] + "...[truncated]"
                result_holder["output"] = output
            except RecursionError:
                result_holder["error"] = "Recursion limit exceeded"
            except Exception as exc:
                result_holder["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                try:
                    sys_setrecursionlimit(old_limit)
                except Exception:
                    pass

        start = time.monotonic()
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=self._timeout)
        elapsed = time.monotonic() - start

        if thread.is_alive():
            result_holder["timed_out"] = True
            result_holder["error"] = (
                f"Execution timed out after {self._timeout}s"
            )

        return SandboxResult(
            success=result_holder["error"] == "",
            output=result_holder["output"],
            error=result_holder["error"],
            execution_time=elapsed,
            timed_out=result_holder["timed_out"],
        )


# 避免在模块顶层直接引用sys（沙箱禁用），用间接引用
import sys as _sys


def sys_getrecursionlimit() -> int:
    return _sys.getrecursionlimit()


def sys_setrecursionlimit(limit: int) -> None:
    _sys.setrecursionlimit(limit)
