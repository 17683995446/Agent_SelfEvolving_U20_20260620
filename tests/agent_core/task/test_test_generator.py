"""
自动测试生成模块测试。

覆盖：代码分析、类提取、函数提取、文件生成、错误处理。
"""

import os
import tempfile

import pytest

from agent_core.task.test_generator import TestGenerator
from agent_core.llm.siliconflow_client import SiliconFlowClient


class FakeLLMTests:
    """Fake LLM for test generation."""

    async def generate_tests(self, code: str, framework: str = "pytest") -> str:
        return "def test_example(): pass"


class FakeLLMNone:
    """Fake LLM returning None."""

    async def generate_tests(self, code: str, framework: str = "pytest") -> None:
        return None


class TestTestGenerator:
    """TestGenerator测试类。"""

    @pytest.fixture
    def generator(self):
        """创建测试生成器实例。"""
        return TestGenerator(SiliconFlowClient())

    def test_analyze_code_empty(self, generator):
        """测试空代码分析。"""
        result = generator.analyze_code("")
        assert result == {"classes": [], "functions": []}

    def test_analyze_code_classes(self, generator):
        """测试类提取。"""
        code = "class Foo:\n  def bar(self): pass\n  def _private(self): pass"
        result = generator.analyze_code(code)
        assert len(result["classes"]) == 1
        assert result["classes"][0]["name"] == "Foo"
        assert result["classes"][0]["methods"] == ["bar"]

    def test_analyze_code_functions(self, generator):
        """测试函数提取。"""
        code = "def add(a, b):\n  return a + b"
        result = generator.analyze_code(code)
        assert len(result["functions"]) == 1
        assert result["functions"][0]["name"] == "add"
        assert result["functions"][0]["args"] == ["a", "b"]

    def test_analyze_code_invalid(self, generator):
        """测试无效代码返回空。"""
        result = generator.analyze_code("def bad(: pass")
        assert result == {"classes": [], "functions": []}

    @pytest.mark.asyncio
    async def test_generate_tests(self, generator):
        """测试生成测试代码。"""
        generator._llm = FakeLLMTests()
        result = await generator.generate_tests("def f(): pass")
        assert result == "def test_example(): pass"

    @pytest.mark.asyncio
    async def test_generate_test_file(self, generator):
        """测试生成测试文件。"""
        generator._llm = FakeLLMTests()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as src:
            src.write("def f(): pass")
            src_path = src.name
        dst_path = src_path + "_test.py"
        try:
            result = await generator.generate_test_file(src_path, dst_path)
            assert result is True
            with open(dst_path, "r") as f:
                assert f.read() == "def test_example(): pass"
        finally:
            os.unlink(src_path)
            if os.path.exists(dst_path):
                os.unlink(dst_path)

    @pytest.mark.asyncio
    async def test_generate_test_file_llm_none(self, generator):
        """测试LLM返回None时失败。"""
        generator._llm = FakeLLMNone()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as src:
            src.write("def f(): pass")
            src_path = src.name
        dst_path = src_path + "_test.py"
        try:
            result = await generator.generate_test_file(src_path, dst_path)
            assert result is False
        finally:
            os.unlink(src_path)

    @pytest.mark.asyncio
    async def test_generate_test_file_not_found(self, generator):
        """测试源文件不存在时失败。"""
        result = await generator.generate_test_file("/nonexistent.py", "/tmp/out.py")
        assert result is False
