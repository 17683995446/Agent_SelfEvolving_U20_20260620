"""
价值对齐模块。

实现人类反馈强化学习(RLHF)，使智能体行为与人类价值观对齐。

第一性原理：
- 人类偏好作为奖励信号
- 奖励模型学习人类判断
- 策略优化在奖励与参考策略间平衡
"""

from typing import Dict, List, Optional, Tuple

import numpy as np

from agent_core.common.logger import get_logger


class PreferencePair:
    """
    偏好对。

    记录两个输出的比较结果。
    """

    def __init__(
        self,
        prompt: str,
        chosen: str,
        rejected: str,
    ) -> None:
        self._prompt = prompt
        self._chosen = chosen
        self._rejected = rejected

    def get_prompt(self) -> str:
        """获取提示。"""
        return self._prompt

    def get_chosen(self) -> str:
        """获取优选输出。"""
        return self._chosen

    def get_rejected(self) -> str:
        """获取拒绝输出。"""
        return self._rejected


class RewardModel:
    """
    奖励模型。

    学习预测人类偏好分数。
    """

    def __init__(self, feature_dim: int = 64) -> None:
        self._feature_dim = feature_dim
        self._weights = np.zeros(feature_dim)
        self._bias = 0.0

    def score(self, features: np.ndarray) -> float:
        """
        计算奖励分数。

        Args:
            features: 特征向量。

        Returns:
            分数。
        """
        if features.shape[0] != self._feature_dim:
            return 0.0
        return float(np.dot(features, self._weights) + self._bias)

    def update(
        self,
        chosen_features: np.ndarray,
        rejected_features: np.ndarray,
        learning_rate: float = 0.01,
    ) -> float:
        """
        基于偏好对更新模型。

        Args:
            chosen_features: 优选特征。
            rejected_features: 拒绝特征。
            learning_rate: 学习率。

        Returns:
            损失值。
        """
        diff = chosen_features - rejected_features
        margin = float(np.dot(diff, self._weights))
        loss = max(0.0, 1.0 - margin)
        if margin < 1.0:
            self._weights += learning_rate * diff
        return loss

    def get_weights(self) -> np.ndarray:
        """获取权重。"""
        return self._weights.copy()


class RLHFAligner:
    """
    RLHF对齐器。

    管理偏好数据、训练奖励模型、对齐策略。
    """

    def __init__(self) -> None:
        self._preferences: List[PreferencePair] = []
        self._reward_model = RewardModel()
        self._kl_coef = 0.1
        self._logger = get_logger()

    def add_preference(
        self,
        prompt: str,
        chosen: str,
        rejected: str,
    ) -> None:
        """
        添加偏好对。

        Args:
            prompt: 提示。
            chosen: 优选输出。
            rejected: 拒绝输出。
        """
        self._preferences.append(PreferencePair(prompt, chosen, rejected))

    def get_preference_count(self) -> int:
        """获取偏好对数量。"""
        return len(self._preferences)

    def train_reward_model(
        self,
        feature_extractor,
        epochs: int = 3,
    ) -> Dict[str, float]:
        """
        训练奖励模型。

        Args:
            feature_extractor: 特征提取函数。
            epochs: 训练轮数。

        Returns:
            训练统计。
        """
        total_loss = 0.0
        count = 0
        for _ in range(epochs):
            for pair in self._preferences:
                chosen_features = feature_extractor(pair.get_chosen())
                rejected_features = feature_extractor(pair.get_rejected())
                loss = self._reward_model.update(
                    chosen_features, rejected_features
                )
                total_loss += loss
                count += 1
        return {
            "loss": total_loss / max(count, 1),
            "samples": count,
        }

    def compute_rlhf_reward(
        self,
        features: np.ndarray,
        ref_score: float,
    ) -> float:
        """
        计算RLHF奖励（含KL惩罚）。

        Args:
            features: 特征向量。
            ref_score: 参考策略分数。

        Returns:
            最终奖励。
        """
        score = self._reward_model.score(features)
        kl_penalty = self._kl_coef * abs(score - ref_score)
        return score - kl_penalty

    def get_reward_model(self) -> RewardModel:
        """获取奖励模型。"""
        return self._reward_model

    def clear_preferences(self) -> None:
        """清空偏好数据。"""
        self._preferences.clear()
