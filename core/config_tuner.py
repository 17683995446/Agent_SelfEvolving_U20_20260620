"""
配置自动调优模块

第一性原理：生物体的内稳态调节—— 当环境变化时，
自动调整生理参数以维持最佳运行状态。

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
class ConfigParameter:
    """配置参数定义"""
    name: str
    current_value: float
    min_value: float
    max_value: float
    step_size: float
    target_metric: str  # 要优化的指标名
    optimize_direction: str  # "minimize" 或 "maximize"


class ConfigAutoTuner:
    """
    配置自动调优器

    根据运行数据自动调整系统配置参数，优化目标指标。

    核心方法（<=7个）：
    1. register_parameter() — 注册可调参数
    2. evaluate_configuration() — 评估当前配置效果
    3. suggest_next_value() — 建议下一个参数值
    4. hill_climbing_optimize() — 爬山法优化
    5. apply_best_configuration() — 应用最优配置
    6. get_optimization_history() — 获取优化历史
    7. get_stats() — 统计
    """

    def __init__(self, exploration_rate: float = 0.2):
        """
        Args:
            exploration_rate: 探索率，0-1之间，越高越倾向于尝试新值
        """
        self._exploration_rate = exploration_rate
        self._parameters: Dict[str, ConfigParameter] = {}
        self._history: List[Dict[str, Any]] = []
        self._best_configs: Dict[str, Dict[str, Any]] = {}

    def register_parameter(self, name: str, current_value: float,
                           min_value: float, max_value: float,
                           step_size: float,
                           target_metric: str,
                           optimize_direction: str = "minimize") -> None:
        """
        注册一个可调参数

        第一性原理：定义搜索空间—— 知道哪些参数可以调、范围是多少。
        """
        self._parameters[name] = ConfigParameter(
            name=name,
            current_value=current_value,
            min_value=min_value,
            max_value=max_value,
            step_size=step_size,
            target_metric=target_metric,
            optimize_direction=optimize_direction,
        )

    def evaluate_configuration(self, param_name: str,
                               value: float,
                               metric_func: Callable[[], float]) -> Dict[str, Any]:
        """
        评估特定配置的效果

        临时设置参数值，运行指标函数，记录结果。
        """
        # 这里模拟评估：实际应用中需要真正修改配置并运行一段时间
        # 将当前测试的值临时存入，让metric_func可以读取
        self._current_test_value = value
        metric_value = metric_func()

        result = {
            "param_name": param_name,
            "value": value,
            "metric_value": metric_value,
            "timestamp": time.time(),
        }
        self._history.append(result)
        return result

    def suggest_next_value(self, param_name: str) -> float:
        """
        建议下一个参数值

        第一性原理：探索-利用权衡—— 有时尝试新方向（探索），
        有时在当前最佳附近微调（利用）。

        策略：
        1. 如果有历史数据，向更优方向移动
        2. 以 exploration_rate 概率随机探索
        3. 确保在合法范围内
        """
        if param_name not in self._parameters:
            return 0.0

        param = self._parameters[param_name]

        # 获取该参数的历史记录
        param_history = [h for h in self._history if h["param_name"] == param_name]

        # 探索：随机选择
        if np.random.random() < self._exploration_rate or not param_history:
            steps = int((param.max_value - param.min_value) / param.step_size)
            random_step = np.random.randint(0, steps + 1)
            return param.min_value + random_step * param.step_size

        # 利用：向更优方向移动
        if param.optimize_direction == "minimize":
            best = min(param_history, key=lambda x: x["metric_value"])
        else:
            best = max(param_history, key=lambda x: x["metric_value"])

        best_value = best["value"]

        # 尝试左右邻居
        left = max(param.min_value, best_value - param.step_size)
        right = min(param.max_value, best_value + param.step_size)

        # 选择未充分探索的方向
        left_count = sum(1 for h in param_history if abs(h["value"] - left) < param.step_size / 2)
        right_count = sum(1 for h in param_history if abs(h["value"] - right) < param.step_size / 2)

        if left_count < right_count:
            return left
        else:
            return right

    def hill_climbing_optimize(self, param_name: str,
                                metric_func: Callable[[], float],
                                max_iterations: int = 20) -> Dict[str, Any]:
        """
        爬山法优化

        从当前值开始，逐步向更优方向移动，直到收敛。

        第一性原理：梯度上升—— 像登山者一样，每一步都向更高的地方走。
        """
        if param_name not in self._parameters:
            return {"error": "parameter not registered"}

        param = self._parameters[param_name]
        current_value = param.current_value

        # 评估当前值
        best_result = self.evaluate_configuration(param_name, current_value, metric_func)
        best_metric = best_result["metric_value"]

        iteration = 0
        improved = False  # 初始化，避免max_iterations=0时NameError
        for iteration in range(max_iterations):
            # 生成邻居值
            neighbors = []
            if current_value - param.step_size >= param.min_value:
                neighbors.append(current_value - param.step_size)
            if current_value + param.step_size <= param.max_value:
                neighbors.append(current_value + param.step_size)

            improved = False
            for neighbor in neighbors:
                result = self.evaluate_configuration(param_name, neighbor, metric_func)
                metric = result["metric_value"]

                is_better = (
                    metric < best_metric if param.optimize_direction == "minimize"
                    else metric > best_metric
                )

                if is_better:
                    best_metric = metric
                    current_value = neighbor
                    best_result = result
                    improved = True

            if not improved:
                break  # 收敛

        # 记录最优配置
        self._best_configs[param_name] = {
            "value": current_value,
            "metric": best_metric,
            "iterations": iteration + 1,
        }

        return {
            "param_name": param_name,
            "optimal_value": current_value,
            "best_metric": best_metric,
            "iterations": iteration + 1,
            "converged": not improved,
        }

    def apply_best_configuration(self, param_name: str) -> bool:
        """
        应用最优配置

        将参数更新为优化后的最佳值。
        """
        if param_name not in self._best_configs:
            return False

        best = self._best_configs[param_name]
        if param_name in self._parameters:
            self._parameters[param_name].current_value = best["value"]
            return True
        return False

    def get_optimization_history(self, param_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取优化历史"""
        if param_name:
            return [h for h in self._history if h["param_name"] == param_name]
        return self._history

    def get_stats(self) -> Dict[str, Any]:
        return {
            "registered_parameters": list(self._parameters.keys()),
            "total_evaluations": len(self._history),
            "best_configs": {
                name: {"value": cfg["value"], "metric": cfg["metric"]}
                for name, cfg in self._best_configs.items()
            },
        }
