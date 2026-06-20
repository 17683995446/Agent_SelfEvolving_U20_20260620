"""
代码自动生成模块

第一性原理：DNA转录翻译—— 根据基因序列（需求描述）合成蛋白质（代码）。
CodeGenerator 从结构化需求描述生成可运行的Python模块。

约束：
- 纯Python实现
- 方法数 <= 7
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


class CodeGenerator:
    """
    代码生成器

    从结构化需求描述生成Python模块代码。

    核心方法（<=7个）：
    1. parse_requirement() — 解析需求描述
    2. generate_class() — 生成类定义
    3. generate_methods() — 生成方法列表
    4. assemble_module() — 组装完整模块
    5. validate_generated() — 验证生成代码的语法
    6. write_module() — 写入文件
    7. get_stats() — 统计
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(__file__).parent.parent
        self._generated_count = 0
        self._history: List[Dict[str, Any]] = []

    def parse_requirement(self, requirement: str) -> Dict[str, Any]:
        """
        解析自然语言需求描述

        提取关键信息：模块名、类名、方法、约束。

        第一性原理：语言理解—— 从自然语言中提取结构化语义。
        """
        result = {
            "raw": requirement,
            "module_name": None,
            "class_name": None,
            "methods": [],
            "constraints": [],
        }

        # 提取模块名：匹配 "xxx模块" 或 "模块xxx"，xxx可以是英文单词
        # 先尝试匹配 "英文模块"
        mod_match = re.search(r'([a-zA-Z_]\w*)\s*模块', requirement)
        if mod_match:
            result["module_name"] = mod_match.group(1)
        else:
            # 尝试匹配 "模块英文"
            mod_match2 = re.search(r'模块\s*([a-zA-Z_]\w*)', requirement)
            if mod_match2:
                result["module_name"] = mod_match2.group(1)

        # 提取类名：匹配 "xxx类" 或直接的大写开头英文单词
        cls_match = re.search(r'([A-Z][a-zA-Z_]*)\s*类', requirement)
        if cls_match:
            result["class_name"] = cls_match.group(1)
        else:
            # 尝试提取大写开头的英文单词作为类名（前面不是英文字母）
            cls_match2 = re.search(r'(?<![a-zA-Z])([A-Z][a-zA-Z_]*)', requirement)
            if cls_match2:
                result["class_name"] = cls_match2.group(1)

        # 提取方法：在"包含/实现/支持/提供/有"到"方法"之间的所有小写开头英文标识符
        start_idx = -1
        for keyword in ("包含", "实现", "支持", "提供", "有"):
            pos = requirement.find(keyword)
            if pos != -1:
                start_idx = pos
                break
        end_idx = requirement.find("方法", start_idx) if start_idx != -1 else -1
        if start_idx != -1 and end_idx != -1:
            segment = requirement[start_idx:end_idx]
            method_words = re.findall(r'[a-zA-Z_]\w*', segment)
            for word in method_words:
                if re.match(r'^[a-z_]', word) and word not in result["methods"]:
                    result["methods"].append(word)
        else:
            # 回退：匹配 "英文方法名方法" 格式
            for match in re.finditer(r'([a-z_]\w*)\s*(?:方法|功能)', requirement):
                method_name = match.group(1)
                if method_name not in result["methods"]:
                    result["methods"].append(method_name)

        # 提取约束（去重）
        constraint_keywords = ["约束", "限制", "不超过", "最多", "至少"]
        seen_constraints = set()
        for keyword in constraint_keywords:
            if keyword in requirement:
                sentences = requirement.split("。")
                for sent in sentences:
                    if keyword in sent:
                        c = sent.strip()
                        if c not in seen_constraints:
                            seen_constraints.add(c)
                            result["constraints"].append(c)

        return result

    def generate_class(self, class_name: str, methods: List[str],
                       constraints: List[str]) -> str:
        """
        生成类定义

        根据类名、方法列表和约束生成Python类代码。
        """
        lines = [
            f"class {class_name}:",
            f'    """',
            f"    {class_name}",
            "",
        ]

        # 添加约束说明
        if constraints:
            lines.append("    约束:")
            for c in constraints:
                lines.append(f"    - {c}")
            lines.append("")

        lines.extend([
            f'    """',
            "",
            "    def __init__(self):",
            "        pass",
            "",
        ])

        # 生成方法存根
        for method in methods:
            lines.extend([
                f"    def {method}(self):",
                f'        """',
                f"        {method} 方法",
                f'        """',
                "        pass",
                "",
            ])

        return "\n".join(lines)

    def generate_methods(self, parsed: Dict[str, Any]) -> List[str]:
        """
        生成方法列表

        根据解析结果生成具体的方法实现代码。
        """
        methods = []

        for method_name in parsed.get("methods", []):
            # 根据方法名推断功能并生成代码
            if "统计" in method_name or "stats" in method_name:
                code = f"""    def {method_name}(self):
        return {{
            "count": 0,
            "status": "ok",
        }}"""
            elif "检查" in method_name or "check" in method_name:
                code = f"""    def {method_name}(self):
        return True"""
            elif "计算" in method_name or "compute" in method_name or "calc" in method_name:
                code = f"""    def {method_name}(self, x, y):
        return x + y"""
            else:
                code = f"""    def {method_name}(self):
        pass"""

            methods.append(code)

        return methods

    def assemble_module(self, parsed: Dict[str, Any]) -> str:
        """
        组装完整模块

        将类定义、方法、导入语句组装为可运行的Python模块。
        """
        lines = [
            '"""',
            f"{parsed.get('module_name', 'generated')} 模块",
            "",
            f"根据需求自动生成: {parsed['raw'][:80]}...",
            '"""',
            "",
            "from __future__ import annotations",
            "",
            "from typing import Dict, List, Optional",
            "",
            "import numpy as np",
            "",
        ]

        class_name = parsed.get("class_name") or "AutoGenerated"
        methods = self.generate_methods(parsed)

        # 类定义
        lines.append(f"class {class_name}:")
        lines.append(f'    """')
        lines.append(f"    {class_name}")
        lines.append("")

        if parsed.get("constraints"):
            lines.append("    约束:")
            for c in parsed["constraints"]:
                lines.append(f"    - {c}")
            lines.append("")

        lines.extend([
            f'    """',
            "",
            "    def __init__(self):",
            "        self._data = {}",
            "",
        ])

        # 添加生成的方法
        for method_code in methods:
            lines.append(method_code)
            lines.append("")

        return "\n".join(lines)

    def validate_generated(self, source: str) -> bool:
        """验证生成代码的语法"""
        try:
            compile(source, "<generated>", "exec")
            return True
        except SyntaxError:
            return False

    def write_module(self, module_name: str, source: str) -> Path:
        """
        写入模块文件

        将生成的代码写入到项目目录中。
        """
        target_dir = self.project_root / "generated"
        target_dir.mkdir(exist_ok=True)

        file_path = target_dir / f"{module_name}.py"
        file_path.write_text(source, encoding="utf-8")

        self._generated_count += 1
        self._history.append({
            "module": module_name,
            "path": str(file_path),
            "lines": len(source.splitlines()),
        })

        return file_path

    def generate_from_requirement(self, requirement: str) -> Dict[str, Any]:
        """
        从需求描述生成完整模块

        端到端生成流程：解析需求 → 生成代码 → 验证 → 写入文件。
        """
        parsed = self.parse_requirement(requirement)
        source = self.assemble_module(parsed)
        valid = self.validate_generated(source)

        result = {
            "parsed": parsed,
            "source": source,
            "valid": valid,
            "module_name": parsed.get("module_name", "generated_module"),
        }

        if valid and parsed.get("module_name"):
            file_path = self.write_module(parsed["module_name"], source)
            result["file_path"] = str(file_path)

        return result

    def get_stats(self) -> Dict[str, Any]:
        return {
            "generated_count": self._generated_count,
            "history": self._history[-5:],
        }
