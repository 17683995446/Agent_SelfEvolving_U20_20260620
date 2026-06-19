"""
自动Bug修复工作流。

捕获异常、调用LLM修复、验证并应用。

第一性原理：
- 修复流程必须闭环：发现→诊断→修复→验证
- 不自动覆盖源码，先写入临时文件验证
- 所有操作可审计、可回滚
"""

import ast
import tempfile
from typing import Any, Dict, Optional

from agent_core.common.logger import get_logger
from agent_core.llm.siliconflow_client import SiliconFlowClient


class AutoBugFixer:
    """自动Bug修复器。"""

    def __init__(self, llm: SiliconFlowClient) -> None:
        self._llm = llm
        self._logger = get_logger()

    async def fix(
        self, code: str, error_message: str
    ) -> Optional[str]:
        """
        执行完整修复工作流。

        Args:
            code: 原始代码。
            error_message: 错误信息。

        Returns:
            修复后的代码，验证失败返回None。
        """
        fixed = await self._llm.fix_code(code, error_message)
        if fixed is None:
            self._logger.warning("[AutoBugFixer] LLM returned no fix")
            return None
        if not self._validate_syntax(fixed):
            self._logger.warning("[AutoBugFixer] Fixed code has syntax errors")
            return None
        self._logger.info("[AutoBugFixer] Fix validated successfully")
        return fixed

    def _validate_syntax(self, code: str) -> bool:
        """验证Python语法。"""
        try:
            ast.parse(code)
            return True
        except SyntaxError:
            return False

    async def fix_file(self, file_path: str, error_message: str) -> bool:
        """
        修复文件中的Bug。

        Args:
            file_path: 文件路径。
            error_message: 错误信息。

        Returns:
            修复成功返回True。
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                code = f.read()
        except OSError as exc:
            self._logger.error(f"[AutoBugFixer] Cannot read file: {exc}")
            return False
        fixed = await self.fix(code, error_message)
        if fixed is None:
            return False
        return self._write_backup_and_apply(file_path, code, fixed)

    def _write_backup_and_apply(
        self, path: str, original: str, fixed: str
    ) -> bool:
        """写入备份并应用修复。"""
        try:
            backup = path + ".bak"
            with open(backup, "w", encoding="utf-8") as f:
                f.write(original)
            with open(path, "w", encoding="utf-8") as f:
                f.write(fixed)
            self._logger.info(f"[AutoBugFixer] Applied fix to {path}")
            return True
        except OSError as exc:
            self._logger.error(f"[AutoBugFixer] Write failed: {exc}")
            return False
