"""
自动文档生成器测试。

覆盖：初始化、单文件文档、目录批量文档、索引生成、读写错误。
"""

import os
import tempfile

import pytest

from agent_core.task.auto_documenter import AutoDocumenter
from agent_core.llm.siliconflow_client import SiliconFlowClient


class FakeLLMDocs:
    """Fake LLM that returns markdown docs."""

    async def generate_docs(self, code: str) -> str:
        return "# Module Docs\n\nGenerated."


class FakeLLMNone:
    """Fake LLM that returns None."""

    async def generate_docs(self, code: str) -> None:
        return None


class TestAutoDocumenter:
    """AutoDocumenter测试类。"""

    @pytest.fixture
    def docer(self):
        """创建文档生成器实例。"""
        return AutoDocumenter(SiliconFlowClient())

    @pytest.mark.asyncio
    async def test_initialize(self, docer):
        """测试初始化成功。"""
        result = await docer.initialize({})
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check(self, docer):
        """测试健康检查。"""
        health = await docer.health_check()
        assert health["status"] == "healthy"

    def test_version(self, docer):
        """测试版本号。"""
        assert docer.version == "1.0.0"

    def test_module_name(self, docer):
        """测试模块名称。"""
        assert docer.module_name == "AutoDocumenter"

    @pytest.mark.asyncio
    async def test_document_file_success(self, docer):
        """测试单文件文档生成成功。"""
        docer._llm = FakeLLMDocs()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("def f(): pass")
            src = f.name
        try:
            result = await docer.document_file(src)
            assert result == "# Module Docs\n\nGenerated."
        finally:
            os.unlink(src)

    @pytest.mark.asyncio
    async def test_document_file_with_output(self, docer):
        """测试单文件文档生成并写入文件。"""
        docer._llm = FakeLLMDocs()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("def f(): pass")
            src = f.name
        dst = src + ".md"
        try:
            result = await docer.document_file(src, dst)
            assert result == "# Module Docs\n\nGenerated."
            assert os.path.exists(dst)
            with open(dst, "r", encoding="utf-8") as f:
                assert f.read() == "# Module Docs\n\nGenerated."
        finally:
            os.unlink(src)
            if os.path.exists(dst):
                os.unlink(dst)

    @pytest.mark.asyncio
    async def test_document_file_not_found(self, docer):
        """测试文件不存在返回None。"""
        result = await docer.document_file("/nonexistent/file.py")
        assert result is None

    @pytest.mark.asyncio
    async def test_document_file_llm_none(self, docer):
        """测试LLM返回None时返回None。"""
        docer._llm = FakeLLMNone()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("def f(): pass")
            src = f.name
        try:
            result = await docer.document_file(src)
            assert result is None
        finally:
            os.unlink(src)

    @pytest.mark.asyncio
    async def test_document_directory(self, docer):
        """测试目录批量文档生成。"""
        docer._llm = FakeLLMDocs()
        with tempfile.TemporaryDirectory() as src_dir:
            with open(os.path.join(src_dir, "a.py"), "w") as f:
                f.write("def a(): pass")
            with open(os.path.join(src_dir, "b.txt"), "w") as f:
                f.write("not python")
            with tempfile.TemporaryDirectory() as dst_dir:
                result = await docer.document_directory(src_dir, dst_dir)
                assert len(result) == 1
                assert result[0].endswith("a.py.md")

    @pytest.mark.asyncio
    async def test_generate_index(self, docer):
        """测试索引生成。"""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "index.md")
            ok = await docer.generate_index(["/docs/a.md", "/docs/b.md"], path)
            assert ok is True
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "API Documentation Index" in content
            assert "a" in content
            assert "b" in content
