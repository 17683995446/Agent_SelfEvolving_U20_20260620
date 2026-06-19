"""
世界模型模块。

学习环境动态，预测未来状态，支持规划与决策。

第一性原理：
- 智能体需要理解环境如何响应动作
- 预测未来状态是规划的基础
- 不确定性必须被显式建模
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from agent_core.common.logger import get_logger


class WorldModel:
    """
    世界模型。

    基于历史转移学习状态转移概率，预测下一状态。
    """

    def __init__(self, state_dim: int, action_dim: int) -> None:
        self._state_dim = state_dim
        self._action_dim = action_dim
        self._transitions: List[Tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        self._state_means: Dict[int, np.ndarray] = {}
        self._state_counts: Dict[int, int] = {}
        self._logger = get_logger()

    def observe_transition(
        self, state: np.ndarray, action: np.ndarray, next_state: np.ndarray
    ) -> None:
        """
        观察状态转移。

        Args:
            state: 当前状态。
            action: 执行动作。
            next_state: 下一状态。
        """
        self._transitions.append((state.copy(), action.copy(), next_state.copy()))
        action_key = self._action_key(action)
        if action_key not in self._state_means:
            self._state_means[action_key] = np.zeros(self._state_dim)
            self._state_counts[action_key] = 0
        self._state_means[action_key] += next_state - state
        self._state_counts[action_key] += 1

    def predict(
        self, state: np.ndarray, action: np.ndarray
    ) -> np.ndarray:
        """
        预测下一状态。

        Args:
            state: 当前状态。
            action: 执行动作。

        Returns:
            预测的下一状态。
        """
        action_key = self._action_key(action)
        if action_key not in self._state_counts:
            return state.copy()
        mean_delta = self._state_means[action_key] / self._state_counts[action_key]
        return state + mean_delta

    def predict_uncertainty(
        self, state: np.ndarray, action: np.ndarray
    ) -> Tuple[np.ndarray, float]:
        """
        预测下一状态及其不确定性。

        Args:
            state: 当前状态。
            action: 执行动作。

        Returns:
            (预测状态, 不确定性估计)。
        """
        action_key = self._action_key(action)
        pred = self.predict(state, action)
        if action_key not in self._state_counts or self._state_counts[action_key] < 2:
            return pred, 1.0
        deltas = [
            ns - s for s, a, ns in self._transitions
            if self._action_key(a) == action_key
        ]
        var = np.var(deltas, axis=0)
        uncertainty = float(np.mean(var))
        return pred, uncertainty

    def rollout(
        self,
        state: np.ndarray,
        actions: List[np.ndarray],
    ) -> List[np.ndarray]:
        """
        执行多步前向推演。

        Args:
            state: 初始状态。
            actions: 动作序列。

        Returns:
            预测状态序列。
        """
        states = [state.copy()]
        current = state.copy()
        for action in actions:
            current = self.predict(current, action)
            states.append(current.copy())
        return states

    def _action_key(self, action: np.ndarray) -> int:
        """将动作映射为离散键。"""
        return hash(action.tobytes()) % (2 ** 32)

    def get_stats(self) -> Dict[str, Any]:
        """获取模型统计。"""
        return {
            "transitions": len(self._transitions),
            "unique_actions": len(self._state_counts),
        }
