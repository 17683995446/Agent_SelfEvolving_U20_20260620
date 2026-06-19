"""
自动测试生成模块。

基于代码分析自动生成测试用例，覆盖正常、边界、异常情况。

第一性原理：
- 测试是质量的唯一客观证明
- 自动生成减少人工遗漏
- 基于代码结构而非随机生成
"""

import ast
import inspect
from typing import Any, Dict, List, Optional

from agent_core.common.interfaces import ModuleInterface
from agent_core.common.logger import get_logger
from agent_core.llm.siliconflow_client import SiliconFlowClient


class TestGenerator(ModuleInterface):
    """
    测试生成器。

    分析Python源码结构，结合LLM生成完整测试文件。
    """

    def __init__(self, llm: SiliconFlowClient) -> None:
        self._llm = llm
        self._logger = get_logger()

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "TestGenerator"

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化测试生成器。"""
        self._logger.info("[TestGenerator] Initialized")
        return True

    async def health_check(self) -> Dict[str, Any]:
        """健康检查。"""
        return {"status": "healthy", "metrics": {}}

    async def shutdown(self) -> None:
        """优雅关闭。"""
        pass

    def analyze_code(self, code: str) -> Dict[str, Any]:
        """
        分析代码结构。

        Args:
            code: Python源码。

        Returns:
            包含类列表、函数列表、参数信息的字典。
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {"classes": [], "functions": []}
        classes: List[Dict[str, Any]] = []
        functions: List[Dict[str, Any]] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                methods = [
                    n.name for n in node.body
                    if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")
                ]
                classes.append({"name": node.name, "methods": methods})
            elif isinstance(node, ast.FunctionDef):
                args = [
                    arg.arg for arg in node.args.args
                    if arg.arg != "self"
                ]
                functions.append({"name": node.name, "args": args})
        return {"classes": classes, "functions": functions}

    async def generate_tests(
        self, code: str, framework: str = "pytest"
    ) -> Optional[str]:
        """
        生成单元测试。

        Args:
            code: 被测代码。
            framework: 测试框架。

        Returns:
            生成的测试代码。
        """
        analysis = self.analyze_code(code)
        context = self._format_analysis(analysis)
        return await self._llm.generate_tests(code, framework)

    def _format_analysis(self, analysis: Dict[str, Any]) -> str:
        """格式化分析结果为文本。"""
        lines = []
        for cls in analysis["classes"]:
            lines.append(f"Class: {cls['name']}")
            for m in cls["methods"]:
                lines.append(f"  - {m}()")
        for func in analysis["functions"]:
            lines.append(f"Function: {func['name']}({', '.join(func['args'])})")
        return "\n".join(lines)

    async def generate_test_file(
        self, source_path: str, output_path: str
    ) -> bool:
        """
        为源码文件生成测试文件。

        Args:
            source_path: 源码路径。
            output_path: 测试文件输出路径。

        Returns:
            成功返回True。
        """
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                code = f.read()
        except OSError as exc:
            self._logger.error(f"[TestGenerator] Cannot read {source_path}: {exc}")
            return False
        tests = await self.generate_tests(code)
        if tests is None:
            return False
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(tests)
            return True
        except OSError as exc:
            self._logger.error(f"[TestGenerator] Cannot write {output_path}: {exc}")
            return False
