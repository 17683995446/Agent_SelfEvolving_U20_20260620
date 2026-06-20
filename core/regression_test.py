"""
性能回归测试框架

第一性原理：生物体的免疫系统—— 识别"自身"与"非自身"，
当新代码导致性能下降时自动标记为"异常"。

约束：
- 纯Python实现
- 方法数 <= 7
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable

import numpy as np


@dataclass
class PerformanceBaseline:
    """性能基线"""
    func_name: str
    mean_ms: float
    std_ms: float
    timestamp: float


class RegressionTestFramework:
    """
    性能回归测试框架

    自动对比优化前后的性能，标记回归（性能下降）。

    核心方法（<=7个）：
    1. record_baseline() — 记录性能基线
    2. run_comparison() — 运行对比测试
    3. detect_regression() — 检测性能回归
    4. generate_report() — 生成回归报告
    5. benchmark_module() — 对整个模块进行基准测试
    6. approve_changes() — 批准性能变化（更新基线）
    7. get_stats() — 统计
    """

    def __init__(self, regression_threshold: float = 0.2):
        """
        Args:
            regression_threshold: 性能回归阈值，超过此比例视为回归
        """
        self._threshold = regression_threshold
        self._baselines: Dict[str, PerformanceBaseline] = {}
        self._comparison_history: List[Dict[str, Any]] = []
        self._approved_changes: List[str] = []

    def record_baseline(self, func_name: str,
                        benchmark_func: Callable,
                        *args,
                        iterations: int = 100) -> PerformanceBaseline:
        """
        记录函数性能基线

        第一性原理：建立"正常状态"的参考标准，类似生物的稳态设定点。
        """
        times = []
        for _ in range(iterations):
            t0 = time.time()
            try:
                benchmark_func(*args)
            except Exception:
                continue
            times.append((time.time() - t0) * 1000)

        arr = np.array(times)
        if len(times) == 0:
            mean_ms = 0.0
            std_ms = 0.0
        else:
            mean_ms = float(np.mean(arr))
            std_ms = float(np.std(arr))
        baseline = PerformanceBaseline(
            func_name=func_name,
            mean_ms=mean_ms,
            std_ms=std_ms,
            timestamp=time.time(),
        )
        self._baselines[func_name] = baseline
        return baseline

    def run_comparison(self, func_name: str,
                       benchmark_func: Callable,
                       *args,
                       iterations: int = 100) -> Dict[str, Any]:
        """
        运行对比测试

        对比当前性能与基线，计算变化百分比。
        """
        if func_name not in self._baselines:
            baseline = self.record_baseline(func_name, benchmark_func, *args, iterations=iterations)
            return {
                "func_name": func_name,
                "baseline_recorded": True,
                "baseline_mean_ms": baseline.mean_ms,
            }

        baseline = self._baselines[func_name]

        # 运行当前测试
        times = []
        for _ in range(iterations):
            t0 = time.time()
            try:
                benchmark_func(*args)
            except Exception:
                continue
            times.append((time.time() - t0) * 1000)

        arr = np.array(times)
        if len(times) == 0:
            current_mean = 0.0
            current_std = 0.0
        else:
            current_mean = float(np.mean(arr))
            current_std = float(np.std(arr))

        # 计算变化
        change_pct = (current_mean - baseline.mean_ms) / baseline.mean_ms if baseline.mean_ms > 0 else 0

        result = {
            "func_name": func_name,
            "baseline_mean_ms": baseline.mean_ms,
            "baseline_std_ms": baseline.std_ms,
            "current_mean_ms": current_mean,
            "current_std_ms": current_std,
            "change_pct": change_pct,
            "regression": change_pct > self._threshold,
            "improvement": change_pct < -self._threshold,
            "timestamp": time.time(),
        }

        self._comparison_history.append(result)
        return result

    def detect_regression(self) -> List[Dict[str, Any]]:
        """
        检测所有已记录基线的函数是否存在性能回归

        第一性原理：免疫系统的异常检测—— 识别偏离正常范围的"入侵者"。
        """
        regressions = []
        for func_name, baseline in self._baselines.items():
            # 检查最近一次对比结果
            recent = [
                c for c in self._comparison_history
                if c["func_name"] == func_name
            ]
            if recent:
                latest = recent[-1]
                if latest.get("regression", False):
                    regressions.append({
                        "func_name": func_name,
                        "severity": latest["change_pct"],
                        "baseline_ms": latest["baseline_mean_ms"],
                        "current_ms": latest["current_mean_ms"],
                        "description": f"{func_name} 性能下降 {latest['change_pct']*100:.1f}%",
                    })
        return sorted(regressions, key=lambda x: x["severity"], reverse=True)

    def generate_report(self) -> Dict[str, Any]:
        """
        生成回归测试报告
        """
        regressions = self.detect_regression()
        improvements = [
            c for c in self._comparison_history
            if c.get("improvement", False)
        ]

        return {
            "total_baselines": len(self._baselines),
            "total_comparisons": len(self._comparison_history),
            "regressions_found": len(regressions),
            "improvements_found": len(improvements),
            "regression_list": regressions[:5],
            "improvement_list": [
                {
                    "func_name": c["func_name"],
                    "improvement_pct": abs(c["change_pct"]) * 100,
                }
                for c in improvements[-5:]
            ],
            "health_status": "HEALTHY" if not regressions else "DEGRADED",
        }

    def benchmark_module(self, module: Any,
                         func_prefix: str = "",
                         iterations: int = 50) -> Dict[str, Dict[str, Any]]:
        """
        对整个模块的函数进行基准测试

        自动发现模块中的可调用函数并建立基线。
        """
        results = {}
        import inspect

        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and name.startswith(func_prefix):
                try:
                    baseline = self.record_baseline(
                        name, obj, iterations=iterations
                    )
                    results[name] = {
                        "mean_ms": baseline.mean_ms,
                        "std_ms": baseline.std_ms,
                        "status": "baseline_recorded",
                    }
                except Exception as e:
                    results[name] = {"status": "error", "error": str(e)}

        return results

    def approve_changes(self, func_name: str) -> bool:
        """
        批准性能变化（更新基线）

        当确认性能变化是预期内的（如功能增强导致变慢），
        更新基线以反映新的"正常状态"。
        """
        recent = [
            c for c in self._comparison_history
            if c["func_name"] == func_name
        ]
        if not recent:
            return False

        latest = recent[-1]
        new_baseline = PerformanceBaseline(
            func_name=func_name,
            mean_ms=latest["current_mean_ms"],
            std_ms=latest["current_std_ms"],
            timestamp=time.time(),
        )
        self._baselines[func_name] = new_baseline
        self._approved_changes.append(func_name)
        return True

    def get_stats(self) -> Dict[str, Any]:
        return {
            "baselines": list(self._baselines.keys()),
            "comparisons": len(self._comparison_history),
            "regressions": len(self.detect_regression()),
            "approved_changes": len(self._approved_changes),
            "health": self.generate_report()["health_status"],
        }
