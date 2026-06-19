"""
自动Bug修复器测试。

覆盖：初始化、修复流程、语法校验、文件修复、备份写入。
"""

import os
import tempfile

import pytest

from agent_core.task.auto_bug_fixer import AutoBugFixer
from agent_core.llm.siliconflow_client import SiliconFlowClient


class FakeLLM:
    """Fake LLM for testing."""

    def __init__(self, fixed_code: str = "", return_none: bool = False) -> None:
        self._fixed = fixed_code
        self._return_none = return_none

    async def fix_code(self, code: str, error_message: str) -> Optional[str]:
        if self._return_none:
            return None
        return self._fixed


class TestAutoBugFixer:
    """AutoBugFixer测试类。"""

    @pytest.fixture
    def fixer(self):
        """创建修复器实例。"""
        llm = SiliconFlowClient()
        return AutoBugFixer(llm)

    def test_init(self, fixer):
        """测试初始化。"""
        assert fixer._llm is not None

    @pytest.mark.asyncio
    async def test_fix_success(self, fixer):
        """测试修复成功流程。"""
        fixer._llm = FakeLLM("def f(): return 1")
        result = await fixer.fix("def f(): return 0", "error")
        assert result == "def f(): return 1"

    @pytest.mark.asyncio
    async def test_fix_llm_returns_none(self, fixer):
        """测试LLM返回None时修复失败。"""
        fixer._llm = FakeLLM("", return_none=True)
        result = await fixer.fix("def f(): pass", "err")
        assert result is None

    @pytest.mark.asyncio
    async def test_fix_syntax_error(self, fixer):
        """测试修复后代码语法错误时返回None。"""
        fixer._llm = FakeLLM("def f(: pass")
        result = await fixer.fix("def f(): pass", "err")
        assert result is None

    def test_validate_syntax_valid(self, fixer):
        """测试有效代码语法校验通过。"""
        assert fixer._validate_syntax("def f(): return 1") is True

    def test_validate_syntax_invalid(self, fixer):
        """测试无效代码语法校验失败。"""
        assert fixer._validate_syntax("def f(: pass") is False

    @pytest.mark.asyncio
    async def test_fix_file_success(self, fixer):
        """测试文件修复成功。"""
        fixer._llm = FakeLLM("def f(): return 1")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("def f(): return 0")
            path = f.name
        try:
            result = await fixer.fix_file(path, "error")
            assert result is True
            with open(path, "r", encoding="utf-8") as f:
                assert f.read() == "def f(): return 1"
            assert os.path.exists(path + ".bak")
        finally:
            os.unlink(path)
            if os.path.exists(path + ".bak"):
                os.unlink(path + ".bak")

    @pytest.mark.asyncio
    async def test_fix_file_read_error(self, fixer):
        """测试文件读取失败返回False。"""
        result = await fixer.fix_file("/nonexistent/file.py", "err")
        assert result is False

    def test_write_backup_and_apply(self, fixer):
        """测试备份写入和应用。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("original")
            path = f.name
        try:
            result = fixer._write_backup_and_apply(path, "original", "fixed")
            assert result is True
            with open(path, "r", encoding="utf-8") as f:
                assert f.read() == "fixed"
            with open(path + ".bak", "r", encoding="utf-8") as f:
                assert f.read() == "original"
        finally:
            os.unlink(path)
            if os.path.exists(path + ".bak"):
                os.unlink(path + ".bak")
