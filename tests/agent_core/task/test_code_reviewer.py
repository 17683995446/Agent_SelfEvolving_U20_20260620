"""
代码审查器测试。

覆盖：初始化、审查解析、分数计算、目录扫描、报告导出。
"""

import json
import os
import tempfile

import pytest

from agent_core.task.code_reviewer import CodeReviewer, ReviewFinding, ReviewReport
from agent_core.llm.siliconflow_client import SiliconFlowClient


class FakeLLMReview:
    """Fake LLM that returns structured review text."""

    async def review_code(self, code: str) -> str:
        return (
            "- Severity: high\n"
            "- Category: style\n"
            "- Line: 10\n"
            "- Message: missing type hint\n"
            "- Suggestion: add type hints\n"
            "Summary: good code"
        )


class FakeLLMNone:
    """Fake LLM that returns None."""

    async def review_code(self, code: str) -> None:
        return None


class TestCodeReviewer:
    """CodeReviewer测试类。"""

    @pytest.fixture
    def reviewer(self):
        """创建审查器实例。"""
        return CodeReviewer(SiliconFlowClient())

    @pytest.mark.asyncio
    async def test_initialize(self, reviewer):
        """测试初始化成功。"""
        result = await reviewer.initialize({})
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check(self, reviewer):
        """测试健康检查。"""
        health = await reviewer.health_check()
        assert health["status"] == "healthy"

    def test_version(self, reviewer):
        """测试版本号。"""
        assert reviewer.version == "1.0.0"

    def test_module_name(self, reviewer):
        """测试模块名称。"""
        assert reviewer.module_name == "CodeReviewer"

    @pytest.mark.asyncio
    async def test_review_code_parsing(self, reviewer):
        """测试审查结果解析。"""
        reviewer._llm = FakeLLMReview()
        report = await reviewer.review_code("/tmp/test.py", "def f(): pass")
        assert report is not None
        assert report.file_path == "/tmp/test.py"
        assert len(report.findings) == 1
        assert report.findings[0].severity == "high"
        assert report.findings[0].category == "style"
        assert report.findings[0].message == "missing type hint"
        assert report.score == 90.0

    @pytest.mark.asyncio
    async def test_review_code_llm_none(self, reviewer):
        """测试LLM返回None时返回None。"""
        reviewer._llm = FakeLLMNone()
        report = await reviewer.review_code("/tmp/test.py", "def f(): pass")
        assert report is None

    def test_compute_score_empty(self, reviewer):
        """测试无发现时分数为100。"""
        score = reviewer._compute_score([])
        assert score == 100.0

    def test_compute_score_critical(self, reviewer):
        """测试critical严重度扣分。"""
        findings = [
            ReviewFinding("critical", "bug", "1", "err", "fix"),
        ]
        score = reviewer._compute_score(findings)
        assert score == 80.0

    def test_compute_score_multiple(self, reviewer):
        """测试多个发现项累加扣分。"""
        findings = [
            ReviewFinding("high", "bug", "1", "err", "fix"),
            ReviewFinding("medium", "style", "2", "warn", "fix"),
        ]
        score = reviewer._compute_score(findings)
        assert score == 85.0

    def test_extract_summary(self, reviewer):
        """测试总结提取。"""
        raw = "Summary: overall good\n- Severity: low"
        summary = reviewer._extract_summary(raw)
        assert summary == "overall good"

    def test_extract_summary_missing(self, reviewer):
        """测试无总结时返回空字符串。"""
        summary = reviewer._extract_summary("no summary here")
        assert summary == ""

    @pytest.mark.asyncio
    async def test_review_file_not_found(self, reviewer):
        """测试文件不存在返回None。"""
        report = await reviewer.review_file("/nonexistent/file.py")
        assert report is None

    @pytest.mark.asyncio
    async def test_review_file_success(self, reviewer):
        """测试文件审查成功。"""
        reviewer._llm = FakeLLMReview()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as f:
            f.write("def f(): pass")
            path = f.name
        try:
            report = await reviewer.review_file(path)
            assert report is not None
            assert report.file_path == path
        finally:
            os.unlink(path)

    def test_export_report(self, reviewer):
        """测试报告导出。"""
        report = ReviewReport(
            file_path="/a.py",
            findings=[
                ReviewFinding("low", "style", "5", "msg", "sug"),
            ],
            summary="ok",
            score=98.0,
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = f.name
        try:
            result = reviewer.export_report(report, path)
            assert result is True
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["file_path"] == "/a.py"
            assert data["score"] == 98.0
            assert len(data["findings"]) == 1
        finally:
            os.unlink(path)
