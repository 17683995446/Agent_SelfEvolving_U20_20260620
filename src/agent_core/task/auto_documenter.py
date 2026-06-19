"""
自动文档生成工作流。

扫描模块源码，利用LLM生成结构化API文档。

第一性原理：
- 文档是代码的镜像，必须同步更新
- 自动生成减少人工维护成本
- Markdown格式通用、可渲染
"""

import os
from typing import Any, Dict, List, Optional

from agent_core.common.interfaces import ModuleInterface
from agent_core.common.logger import get_logger
from agent_core.llm.siliconflow_client import SiliconFlowClient


class AutoDocumenter(ModuleInterface):
    """
    自动文档生成器。

    对指定模块或目录生成Markdown格式API文档。
    """

    def __init__(self, llm: SiliconFlowClient) -> None:
        self._llm = llm
        self._logger = get_logger()

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "AutoDocumenter"

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化文档生成器。"""
        self._logger.info("[AutoDocumenter] Initialized")
        return True

    async def health_check(self) -> Dict[str, Any]:
        """健康检查。"""
        return {"status": "healthy", "metrics": {}}

    async def shutdown(self) -> None:
        """优雅关闭。"""
        pass

    async def document_file(
        self, file_path: str, output_path: Optional[str] = None
    ) -> Optional[str]:
        """
        为单个文件生成文档。

        Args:
            file_path: 源码文件路径。
            output_path: 文档输出路径，None则返回字符串。

        Returns:
            生成的Markdown文档，失败返回None。
        """
        code = self._read_file(file_path)
        if code is None:
            return None
        docs = await self._llm.generate_docs(code)
        if docs is None:
            self._logger.warning(f"[AutoDocumenter] No docs for {file_path}")
            return None
        if output_path is not None:
            self._write_file(output_path, docs)
        return docs

    def _read_file(self, file_path: str) -> Optional[str]:
        """读取文件内容。"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as exc:
            self._logger.error(f"[AutoDocumenter] Cannot read {file_path}: {exc}")
            return None

    def _write_file(self, path: str, content: str) -> bool:
        """写入文件内容。"""
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self._logger.info(f"[AutoDocumenter] Written {path}")
            return True
        except OSError as exc:
            self._logger.error(f"[AutoDocumenter] Cannot write {path}: {exc}")
            return False

    async def document_directory(
        self,
        source_dir: str,
        output_dir: str,
        pattern: str = ".py",
    ) -> List[str]:
        """
        批量为目录下所有匹配文件生成文档。

        Args:
            source_dir: 源码目录。
            output_dir: 文档输出目录。
            pattern: 文件后缀。

        Returns:
            成功生成的文档路径列表。
        """
        os.makedirs(output_dir, exist_ok=True)
        generated: List[str] = []
        for root, _, files in os.walk(source_dir):
            for name in files:
                if not name.endswith(pattern):
                    continue
                src = os.path.join(root, name)
                rel = os.path.relpath(src, source_dir)
                dst = os.path.join(
                    output_dir, rel.replace(os.sep, "_") + ".md"
                )
                docs = await self.document_file(src, dst)
                if docs is not None:
                    generated.append(dst)
        self._logger.info(
            f"[AutoDocumenter] Directory done: {len(generated)} docs"
        )
        return generated

    async def generate_index(
        self, doc_paths: List[str], output_path: str
    ) -> bool:
        """
        生成文档索引页。

        Args:
            doc_paths: 文档路径列表。
            output_path: 索引输出路径。

        Returns:
            成功返回True。
        """
        lines = ["# API Documentation Index\n", "| Module | Path |", "|--------|------|"]
        for path in doc_paths:
            name = os.path.basename(path).replace(".md", "")
            lines.append(f"| {name} | {path} |")
        content = "\n".join(lines) + "\n"
        return self._write_file(output_path, content)
