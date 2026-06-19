"""
PPO强化学习训练模块。

实现简化版近端策略优化（PPO），用于策略梯度学习。

第一性原理：
- 策略梯度直接优化期望回报
- 裁剪目标防止策略突变
- 优势函数减少方差
"""

from typing import Any, Dict, List, Tuple

import numpy as np

from agent_core.common.logger import get_logger


class PPOTrainer:
    """
    PPO训练器。

    使用裁剪目标优化策略参数。
    """

    def __init__(
        self,
        clip_epsilon: float = 0.2,
        learning_rate: float = 0.001,
        gamma: float = 0.99,
        lam: float = 0.95,
    ) -> None:
        self._clip_eps = clip_epsilon
        self._lr = learning_rate
        self._gamma = gamma
        self._lam = lam
        self._logger = get_logger()
        self._trajectory: List[Dict[str, Any]] = []

    def record_step(
        self,
        state: np.ndarray,
        action: np.ndarray,
        reward: float,
        value: float,
        log_prob: float,
    ) -> None:
        """
        记录一步交互。

        Args:
            state: 状态。
            action: 动作。
            reward: 奖励。
            value: 价值估计。
            log_prob: 动作对数概率。
        """
        self._trajectory.append({
            "state": state.copy(),
            "action": action.copy(),
            "reward": reward,
            "value": value,
            "log_prob": log_prob,
        })

    def compute_advantages(self) -> List[float]:
        """
        计算GAE优势估计。

        Returns:
            优势值列表。
        """
        advantages: List[float] = []
        gae = 0.0
        for t in reversed(range(len(self._trajectory))):
            if t == len(self._trajectory) - 1:
                next_value = 0.0
            else:
                next_value = self._trajectory[t + 1]["value"]
            delta = (
                self._trajectory[t]["reward"]
                + self._gamma * next_value
                - self._trajectory[t]["value"]
            )
            gae = delta + self._gamma * self._lam * gae
            advantages.insert(0, gae)
        return advantages

    def compute_ppo_loss(
        self,
        old_log_prob: float,
        new_log_prob: float,
        advantage: float,
    ) -> float:
        """
        计算PPO裁剪损失。

        Args:
            old_log_prob: 旧策略对数概率。
            new_log_prob: 新策略对数概率。
            advantage: 优势值。

        Returns:
            损失值（正值，越小表示策略越优）。
        """
        ratio = np.exp(new_log_prob - old_log_prob)
        clipped = np.clip(ratio, 1 - self._clip_eps, 1 + self._clip_eps)
        loss = max(ratio * advantage, clipped * advantage)
        return float(loss)

    def update_policy(
        self,
        policy_gradient_fn: Any,
    ) -> Dict[str, float]:
        """
        更新策略（简化版，实际需神经网络）。

        Args:
            policy_gradient_fn: 策略梯度计算函数。

        Returns:
            训练统计。
        """
        advantages = self.compute_advantages()
        total_loss = 0.0
        for step, adv in zip(self._trajectory, advantages):
            total_loss += abs(adv)
        self._trajectory.clear()
        return {"loss": total_loss / max(len(advantages), 1)}

    def clear_trajectory(self) -> None:
        """清空轨迹。"""
        self._trajectory.clear()

    def get_trajectory_length(self) -> int:
        """获取当前轨迹长度。"""
        return len(self._trajectory)
