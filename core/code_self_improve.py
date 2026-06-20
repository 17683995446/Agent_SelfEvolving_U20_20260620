"""
代码自我诊断与优化模块

第一性原理：生物体的DNA既能指导蛋白质合成，也能通过突变和自然选择自我优化。
CodeSelfImprovement 让Agent能读取、分析、优化自己的源代码。

约束：
- 纯Python实现
- 方法数 <= 7
"""

from __future__ import annotations

import ast
import inspect
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class CodeSelfImprovement:
    """
    代码自我优化器

    分析自身源码，发现性能瓶颈和可优化点，生成改进方案。

    核心方法（<=7个）：
    1. analyze_module() — 分析模块源码
    2. find_bottlenecks() — 发现性能瓶颈
    3. suggest_optimizations() — 生成优化建议
    4. apply_optimization() — 应用优化（创建补丁）
    5. benchmark_function() — 基准测试函数性能
    6. rollback_changes() — 回滚修改
    7. get_stats() — 统计
    """

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(__file__).parent.parent
        self._analysis_history: List[Dict[str, Any]] = []
        self._applied_patches: List[Dict[str, Any]] = []
        self._backup_cache: Dict[str, str] = {}

    def analyze_module(self, module_path: Path) -> Dict[str, Any]:
        """
        分析模块源码结构

        返回模块的函数列表、类列表、复杂度评估。
        """
        if not module_path.exists():
            return {"error": "file not found"}

        source = module_path.read_text(encoding="utf-8")
        lines = source.splitlines()

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return {"error": str(e)}

        functions = []
        classes = []
        total_complexity = 0

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_lines = node.end_lineno - node.lineno if node.end_lineno else 0
                complexity = self._estimate_complexity(node)
                total_complexity += complexity
                functions.append({
                    "name": node.name,
                    "line": node.lineno,
                    "lines": func_lines,
                    "complexity": complexity,
                    "args": len(node.args.args),
                })
            elif isinstance(node, ast.ClassDef):
                classes.append({
                    "name": node.name,
                    "line": node.lineno,
                    "methods": len([n for n in node.body if isinstance(n, ast.FunctionDef)]),
                })

        result = {
            "file": str(module_path.relative_to(self.project_root)),
            "total_lines": len(lines),
            "blank_lines": len([l for l in lines if not l.strip()]),
            "functions": functions,
            "classes": classes,
            "avg_complexity": total_complexity / len(functions) if functions else 0,
            "max_complexity": max((f["complexity"] for f in functions), default=0),
        }
        self._analysis_history.append(result)
        return result

    def _estimate_complexity(self, node: ast.AST) -> int:
        """估计函数复杂度（基于分支数量）"""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity

    def find_bottlenecks(self, module_path: Path) -> List[Dict[str, Any]]:
        """
        发现性能瓶颈

        第一性原理：profiler就像医生的听诊器，找出"心跳过速"的代码段。
        """
        analysis = self.analyze_module(module_path)
        if "error" in analysis:
            return []

        bottlenecks = []

        # 1. 长函数（超过50行）
        for func in analysis["functions"]:
            if func["lines"] > 50:
                bottlenecks.append({
                    "type": "long_function",
                    "target": func["name"],
                    "line": func["line"],
                    "severity": min(func["lines"] / 100, 1.0),
                    "suggestion": f"函数{func['name']}过长({func['lines']}行)，建议拆分为子函数",
                })

        # 2. 高复杂度函数（超过10）
        for func in analysis["functions"]:
            if func["complexity"] > 10:
                bottlenecks.append({
                    "type": "high_complexity",
                    "target": func["name"],
                    "line": func["line"],
                    "severity": min(func["complexity"] / 20, 1.0),
                    "suggestion": f"函数{func['name']}复杂度{func['complexity']}，建议简化条件分支",
                })

        # 3. 参数过多的函数（超过5个）
        for func in analysis["functions"]:
            if func["args"] > 5:
                bottlenecks.append({
                    "type": "too_many_args",
                    "target": func["name"],
                    "line": func["line"],
                    "severity": min((func["args"] - 5) / 5, 1.0),
                    "suggestion": f"函数{func['name']}参数过多({func['args']}个)，建议使用配置对象",
                })

        return sorted(bottlenecks, key=lambda x: x["severity"], reverse=True)

    def suggest_optimizations(self, module_path: Path) -> List[Dict[str, Any]]:
        """
        生成优化建议

        基于瓶颈分析，生成具体的代码改进方案。
        """
        bottlenecks = self.find_bottlenecks(module_path)
        suggestions = []

        for b in bottlenecks:
            if b["type"] == "long_function":
                suggestions.append({
                    "priority": b["severity"],
                    "action": "extract_function",
                    "target": b["target"],
                    "description": b["suggestion"],
                    "estimated_benefit": "可读性+30%，维护成本-20%",
                })
            elif b["type"] == "high_complexity":
                suggestions.append({
                    "priority": b["severity"],
                    "action": "simplify_branches",
                    "target": b["target"],
                    "description": b["suggestion"],
                    "estimated_benefit": "测试覆盖率+15%，bug率-25%",
                })
            elif b["type"] == "too_many_args":
                suggestions.append({
                    "priority": b["severity"],
                    "action": "introduce_config_object",
                    "target": b["target"],
                    "description": b["suggestion"],
                    "estimated_benefit": "API清晰度+40%",
                })

        return suggestions

    def apply_optimization(self, module_path: Path,
                           suggestion: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用优化（创建补丁文件）

        第一性原理：生物进化不是直接修改DNA，而是先产生变异副本，
        自然选择后再替换。这里我们先创建.patch文件，验证后再应用。
        """
        if not module_path.exists():
            return {"success": False, "error": "file not found"}

        # 备份原文件
        source = module_path.read_text(encoding="utf-8")
        backup_path = module_path.with_suffix(module_path.suffix + ".backup")
        if str(module_path) not in self._backup_cache:
            self._backup_cache[str(module_path)] = source
            backup_path.write_text(source, encoding="utf-8")

        # 生成补丁描述（实际代码修改需要更复杂的AST操作，这里生成补丁文件）
        patch_content = f"""# Patch for {module_path.name}
# Target: {suggestion['target']}
# Action: {suggestion['action']}
# Description: {suggestion['description']}
# Generated: {time.ctime()}

## Before
# (see original file)

## After suggestion
# {suggestion['description']}
# Estimated benefit: {suggestion.get('estimated_benefit', 'unknown')}

## Implementation notes
# 1. Review the suggested changes
# 2. Run tests to verify correctness
# 3. Apply patch if tests pass
"""

        patch_path = module_path.with_suffix(module_path.suffix + ".patch")
        patch_path.write_text(patch_content, encoding="utf-8")

        self._applied_patches.append({
            "file": str(module_path),
            "target": suggestion["target"],
            "action": suggestion["action"],
            "timestamp": time.time(),
            "patch_file": str(patch_path),
        })

        return {
            "success": True,
            "patch_file": str(patch_path),
            "backup_file": str(backup_path),
            "message": f"Patch created for {suggestion['target']}",
        }

    def benchmark_function(self, func, *args, iterations: int = 100) -> Dict[str, float]:
        """
        基准测试函数性能

        测量函数执行时间和稳定性。
        """
        times = []
        for _ in range(iterations):
            t0 = time.time()
            try:
                func(*args)
            except Exception:
                continue
            times.append((time.time() - t0) * 1000)

        arr = np.array(times)
        if len(times) == 0:
            return {
                "mean_ms": 0.0,
                "std_ms": 0.0,
                "min_ms": 0.0,
                "max_ms": 0.0,
                "iterations": iterations,
            }
        return {
            "mean_ms": float(np.mean(arr)),
            "std_ms": float(np.std(arr)),
            "min_ms": float(np.min(arr)),
            "max_ms": float(np.max(arr)),
            "iterations": iterations,
        }

    def rollback_changes(self, module_path: Path) -> bool:
        """
        回滚修改

        从备份恢复原始文件。
        """
        key = str(module_path)
        if key in self._backup_cache:
            module_path.write_text(self._backup_cache[key], encoding="utf-8")
            return True

        backup_path = module_path.with_suffix(module_path.suffix + ".backup")
        if backup_path.exists():
            module_path.write_text(backup_path.read_text(encoding="utf-8"), encoding="utf-8")
            return True

        return False

    def get_stats(self) -> Dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "analyses": len(self._analysis_history),
            "patches": len(self._applied_patches),
            "backups": len(self._backup_cache),
            "recent_patches": [
                {"file": p["file"], "target": p["target"], "action": p["action"]}
                for p in self._applied_patches[-5:]
            ],
        }
