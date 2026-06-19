"""
持续学习模块。

实现弹性权重巩固（EWC），防止学习新任务时遗忘旧知识。

第一性原理：
- 重要参数应被保护，不重要参数可用于新任务
- Fisher信息衡量参数对旧任务的重要性
- 正则化约束参数偏离旧最优解
"""

from typing import Any, Dict, List, Optional

import numpy as np

from agent_core.common.logger import get_logger


class ContinualLearner:
    """
    持续学习器。

    使用EWC方法保护已学知识。
    """

    def __init__(self, lambda_ewc: float = 1000.0) -> None:
        self._lambda = lambda_ewc
        self._optimal_params: Dict[str, np.ndarray] = {}
        self._fisher: Dict[str, np.ndarray] = {}
        self._logger = get_logger()

    def consolidate(self, params: Dict[str, np.ndarray], gradients: Dict[str, np.ndarray]) -> None:
        """
        巩固当前任务知识。

        Args:
            params: 当前最优参数。
            gradients: 参数梯度（用于估计Fisher信息）。
        """
        for name, p in params.items():
            self._optimal_params[name] = p.copy()
            grad = gradients.get(name, np.zeros_like(p))
            self._fisher[name] = grad ** 2
        self._logger.info("[ContinualLearner] Task consolidated")

    def compute_ewc_loss(self, current_params: Dict[str, np.ndarray]) -> float:
        """
        计算EWC正则化损失。

        Args:
            current_params: 当前参数。

        Returns:
            EWC损失值。
        """
        loss = 0.0
        for name, p in current_params.items():
            if name not in self._optimal_params:
                continue
            diff = p - self._optimal_params[name]
            fisher = self._fisher.get(name, np.zeros_like(p))
            loss += np.sum(fisher * (diff ** 2))
        return 0.5 * self._lambda * loss

    def compute_ewc_gradient(self, current_params: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
        """
        计算EWC正则化梯度。

        Args:
            current_params: 当前参数。

        Returns:
            EWC梯度字典。
        """
        ewc_grad: Dict[str, np.ndarray] = {}
        for name, p in current_params.items():
            if name not in self._optimal_params:
                continue
            diff = p - self._optimal_params[name]
            fisher = self._fisher.get(name, np.zeros_like(p))
            ewc_grad[name] = self._lambda * fisher * diff
        return ewc_grad

    def get_protected_params(self) -> List[str]:
        """获取受保护的参数名称列表。"""
        return list(self._optimal_params.keys())

    def reset(self) -> None:
        """重置所有巩固的知识。"""
        self._optimal_params.clear()
        self._fisher.clear()
