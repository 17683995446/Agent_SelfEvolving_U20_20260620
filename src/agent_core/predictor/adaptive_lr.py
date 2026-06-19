"""
自适应学习率模块。

实现动态学习率调整策略（Adam/RMSprop/余弦退火）。

第一性原理：
- 学习率过大导致震荡，过小导致收敛慢
- 梯度历史指导学习率调整
- 周期性退火帮助跳出局部最优
"""

from typing import Any, Dict, Optional

import numpy as np

from agent_core.common.logger import get_logger


class AdaptiveLearningRate:
    """
    自适应学习率调度器。

    支持多种调度策略。
    """

    def __init__(
        self,
        initial_lr: float = 0.01,
        strategy: str = "adam",
        decay_rate: float = 0.9,
        min_lr: float = 1e-6,
    ) -> None:
        self._initial_lr = initial_lr
        self._current_lr = initial_lr
        self._strategy = strategy
        self._decay_rate = decay_rate
        self._min_lr = min_lr
        self._step_count = 0
        self._m: Optional[np.ndarray] = None
        self._v: Optional[np.ndarray] = None
        self._beta1 = 0.9
        self._beta2 = 0.999
        self._eps = 1e-8
        self._logger = get_logger()

    def step(self, gradient: np.ndarray) -> np.ndarray:
        """
        执行一步参数更新计算。

        Args:
            gradient: 梯度数组。

        Returns:
            参数更新量。
        """
        self._step_count += 1
        if self._strategy == "adam":
            return self._adam_step(gradient)
        if self._strategy == "rmsprop":
            return self._rmsprop_step(gradient)
        if self._strategy == "cosine":
            return self._cosine_step(gradient)
        return self._sgd_step(gradient)

    def _adam_step(self, gradient: np.ndarray) -> np.ndarray:
        """Adam优化步骤。"""
        if self._m is None:
            self._m = np.zeros_like(gradient)
            self._v = np.zeros_like(gradient)
        self._m = self._beta1 * self._m + (1 - self._beta1) * gradient
        self._v = self._beta2 * self._v + (1 - self._beta2) * (gradient ** 2)
        m_hat = self._m / (1 - self._beta1 ** self._step_count)
        v_hat = self._v / (1 - self._beta2 ** self._step_count)
        update = self._current_lr * m_hat / (np.sqrt(v_hat) + self._eps)
        return update

    def _rmsprop_step(self, gradient: np.ndarray) -> np.ndarray:
        """RMSprop优化步骤。"""
        if self._v is None:
            self._v = np.zeros_like(gradient)
        self._v = self._decay_rate * self._v + (1 - self._decay_rate) * (gradient ** 2)
        update = self._current_lr * gradient / (np.sqrt(self._v) + self._eps)
        return update

    def _cosine_step(self, gradient: np.ndarray) -> np.ndarray:
        """余弦退火步骤。"""
        self._current_lr = self._min_lr + (self._initial_lr - self._min_lr) * (
            1 + np.cos(np.pi * self._step_count / 1000)
        ) / 2
        return self._current_lr * gradient

    def _sgd_step(self, gradient: np.ndarray) -> np.ndarray:
        """普通SGD步骤。"""
        self._current_lr *= self._decay_rate
        self._current_lr = max(self._current_lr, self._min_lr)
        return self._current_lr * gradient

    @property
    def learning_rate(self) -> float:
        """当前学习率。"""
        return float(self._current_lr)

    def reset(self) -> None:
        """重置状态。"""
        self._current_lr = self._initial_lr
        self._step_count = 0
        self._m = None
        self._v = None
