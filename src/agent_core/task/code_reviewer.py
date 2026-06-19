"""
代码审查与优化建议工作流。

利用LLM对系统代码进行定期审查，生成结构化审查报告。

第一性原理：
- 审查是质量保障的第一道防线
- 报告必须结构化、可行动、可追踪
- 所有发现按严重程度分级
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent_core.common.interfaces import ModuleInterface
from agent_core.common.logger import get_logger
from agent_core.llm.siliconflow_client import SiliconFlowClient


@dataclass
class ReviewFinding:
    """单个审查发现项。"""

    severity: str
    category: str
    line_hint: str
    message: str
    suggestion: str


@dataclass
class ReviewReport:
    """代码审查报告。"""

    file_path: str
    findings: List[ReviewFinding] = field(default_factory=list)
    summary: str = ""
    score: float = 0.0


class CodeReviewer(ModuleInterface):
    """
    代码审查器。

    对指定代码文件执行LLM驱动的审查，输出结构化报告。
    """

    def __init__(self, llm: SiliconFlowClient) -> None:
        self._llm = llm
        self._logger = get_logger()

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "CodeReviewer"

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化审查器。"""
        self._logger.info("[CodeReviewer] Initialized")
        return True

    async def health_check(self) -> Dict[str, Any]:
        """健康检查。"""
        return {"status": "healthy", "metrics": {}}

    async def shutdown(self) -> None:
        """优雅关闭。"""
        pass

    async def review_file(self, file_path: str) -> Optional[ReviewReport]:
        """
        审查单个文件。

        Args:
            file_path: 文件绝对路径。

        Returns:
            审查报告，读取失败返回None。
        """
        code = self._read_file(file_path)
        if code is None:
            return None
        return await self.review_code(file_path, code)

    def _read_file(self, file_path: str) -> Optional[str]:
        """读取文件内容。"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as exc:
            self._logger.error(f"[CodeReviewer] Cannot read {file_path}: {exc}")
            return None

    async def review_code(
        self, file_path: str, code: str
    ) -> Optional[ReviewReport]:
        """
        审查代码字符串。

        Args:
            file_path: 文件路径（用于报告标识）。
            code: 代码内容。

        Returns:
            结构化审查报告。
        """
        raw = await self._llm.review_code(code)
        if raw is None:
            self._logger.warning("[CodeReviewer] LLM returned no review")
            return None
        report = self._parse_review(file_path, raw)
        self._logger.info(
            f"[CodeReviewer] {file_path}: {len(report.findings)} findings, score={report.score}"
        )
        return report

    def _parse_review(self, file_path: str, raw: str) -> ReviewReport:
        """解析LLM原始输出为结构化报告。"""
        report = ReviewReport(file_path=file_path)
        report.findings = self._extract_findings(raw)
        report.score = self._compute_score(report.findings)
        report.summary = self._extract_summary(raw)
        return report

    def _extract_findings(self, raw: str) -> List[ReviewFinding]:
        """从原始文本中提取发现项。"""
        findings: List[ReviewFinding] = []
        lines = raw.splitlines()
        current: Dict[str, str] = {}
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("- Severity:"):
                current["severity"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("- Category:"):
                current["category"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("- Line:"):
                current["line_hint"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("- Message:"):
                current["message"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("- Suggestion:"):
                current["suggestion"] = stripped.split(":", 1)[1].strip()
                findings.append(self._build_finding(current))
                current = {}
        return findings

    def _build_finding(self, data: Dict[str, str]) -> ReviewFinding:
        """构建发现项对象。"""
        return ReviewFinding(
            severity=data.get("severity", "info"),
            category=data.get("category", "general"),
            line_hint=data.get("line_hint", "unknown"),
            message=data.get("message", ""),
            suggestion=data.get("suggestion", ""),
        )

    def _compute_score(self, findings: List[ReviewFinding]) -> float:
        """计算代码质量分数(0-100)。"""
        base = 100.0
        weights = {"critical": 20, "high": 10, "medium": 5, "low": 2, "info": 0}
        for f in findings:
            base -= weights.get(f.severity, 0)
        return max(base, 0.0)

    def _extract_summary(self, raw: str) -> str:
        """提取总结段落。"""
        for line in raw.splitlines():
            if line.lower().startswith("summary:"):
                return line.split(":", 1)[1].strip()
        return ""

    async def review_directory(
        self, directory: str, pattern: str = ".py"
    ) -> List[ReviewReport]:
        """
        批量审查目录下所有匹配文件。

        Args:
            directory: 目录路径。
            pattern: 文件后缀。

        Returns:
            审查报告列表。
        """
        reports: List[ReviewReport] = []
        for root, _, files in os.walk(directory):
            for name in files:
                if not name.endswith(pattern):
                    continue
                path = os.path.join(root, name)
                report = await self.review_file(path)
                if report is not None:
                    reports.append(report)
        self._logger.info(
            f"[CodeReviewer] Directory review complete: {len(reports)} files"
        )
        return reports

    def export_report(
        self, report: ReviewReport, output_path: str
    ) -> bool:
        """
        导出报告为JSON。

        Args:
            report: 审查报告。
            output_path: 输出文件路径。

        Returns:
            导出成功返回True。
        """
        data = {
            "file_path": report.file_path,
            "score": report.score,
            "summary": report.summary,
            "findings": [
                {
                    "severity": f.severity,
                    "category": f.category,
                    "line_hint": f.line_hint,
                    "message": f.message,
                    "suggestion": f.suggestion,
                }
                for f in report.findings
            ],
        }
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except OSError as exc:
            self._logger.error(f"[CodeReviewer] Export failed: {exc}")
            return False
