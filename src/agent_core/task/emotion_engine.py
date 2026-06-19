"""
情感计算模块。

实现情绪识别、情绪状态管理与情绪表达。

第一性原理：
- 情绪是对内外部事件的快速评估反应
- 多维度情绪空间（愉悦度、唤醒度、支配度）
- 情绪影响决策权重与行为选择
"""

from typing import Dict, List, Optional, Tuple

import numpy as np

from agent_core.common.logger import get_logger


class EmotionState:
    """
    情绪状态。

    使用PAD三维模型：愉悦度(Pleasure)、唤醒度(Arousal)、支配度(Dominance)。
    """

    def __init__(
        self,
        pleasure: float = 0.0,
        arousal: float = 0.0,
        dominance: float = 0.0,
    ) -> None:
        self._pleasure = float(np.clip(pleasure, -1.0, 1.0))
        self._arousal = float(np.clip(arousal, -1.0, 1.0))
        self._dominance = float(np.clip(dominance, -1.0, 1.0))

    def to_vector(self) -> np.ndarray:
        """转换为向量。"""
        return np.array([self._pleasure, self._arousal, self._dominance])

    def distance(self, other: "EmotionState") -> float:
        """
        计算与另一情绪状态的距离。

        Args:
            other: 另一情绪状态。

        Returns:
            欧氏距离。
        """
        return float(np.linalg.norm(self.to_vector() - other.to_vector()))

    def get_pleasure(self) -> float:
        """获取愉悦度。"""
        return self._pleasure

    def get_arousal(self) -> float:
        """获取唤醒度。"""
        return self._arousal

    def get_dominance(self) -> float:
        """获取支配度。"""
        return self._dominance


class EmotionLabel:
    """
    情绪标签。

    预定义基本情绪在PAD空间中的坐标。
    """

    LABELS: Dict[str, Tuple[float, float, float]] = {
        "joy": (0.8, 0.6, 0.4),
        "sadness": (-0.8, -0.4, -0.6),
        "anger": (-0.6, 0.8, 0.6),
        "fear": (-0.7, 0.7, -0.8),
        "surprise": (0.2, 0.9, 0.1),
        "disgust": (-0.7, 0.2, -0.3),
        "trust": (0.7, 0.3, 0.5),
        "anticipation": (0.4, 0.5, 0.2),
        "neutral": (0.0, 0.0, 0.0),
    }

    @classmethod
    def get_state(cls, name: str) -> EmotionState:
        """
        获取标签对应情绪状态。

        Args:
            name: 情绪名称。

        Returns:
            情绪状态。
        """
        pad = cls.LABELS.get(name, (0.0, 0.0, 0.0))
        return EmotionState(*pad)

    @classmethod
    def classify(cls, state: EmotionState) -> str:
        """
        将情绪状态分类为最近标签。

        Args:
            state: 情绪状态。

        Returns:
            最近的情绪标签名称。
        """
        best_label = "neutral"
        best_distance = float("inf")
        for name, pad in cls.LABELS.items():
            dist = state.distance(EmotionState(*pad))
            if dist < best_distance:
                best_distance = dist
                best_label = name
        return best_label


class EmotionEngine:
    """
    情感引擎。

    管理情绪状态，响应事件更新情绪，并提供情绪表达。
    """

    def __init__(
        self,
        decay_rate: float = 0.05,
        sensitivity: float = 0.3,
    ) -> None:
        self._state = EmotionState()
        self._decay_rate = decay_rate
        self._sensitivity = sensitivity
        self._history: List[EmotionState] = []
        self._logger = get_logger()

    def perceive_event(
        self,
        event_valence: float,
        event_arousal: float,
    ) -> EmotionState:
        """
        感知事件并更新情绪。

        Args:
            event_valence: 事件效价 [-1, 1]。
            event_arousal: 事件唤醒度 [-1, 1]。

        Returns:
            更新后的情绪状态。
        """
        delta_p = event_valence * self._sensitivity
        delta_a = event_arousal * self._sensitivity
        new_p = np.clip(self._state.get_pleasure() + delta_p, -1.0, 1.0)
        new_a = np.clip(self._state.get_arousal() + delta_a, -1.0, 1.0)
        self._state = EmotionState(new_p, new_a, self._state.get_dominance())
        self._history.append(self._state)
        if len(self._history) > 1000:
            self._history.pop(0)
        return self._state

    def decay(self) -> EmotionState:
        """
        情绪自然衰减。

        Returns:
            衰减后的情绪状态。
        """
        new_p = self._state.get_pleasure() * (1 - self._decay_rate)
        new_a = self._state.get_arousal() * (1 - self._decay_rate)
        new_d = self._state.get_dominance() * (1 - self._decay_rate)
        self._state = EmotionState(new_p, new_a, new_d)
        return self._state

    def get_current_state(self) -> EmotionState:
        """获取当前情绪状态。"""
        return self._state

    def get_current_label(self) -> str:
        """获取当前情绪标签。"""
        return EmotionLabel.classify(self._state)

    def express(self) -> str:
        """
        表达当前情绪。

        Returns:
            情绪表达文本。
        """
        label = self.get_current_label()
        intensity = abs(self._state.get_pleasure()) + abs(self._state.get_arousal())
        if intensity < 0.3:
            return "feeling neutral"
        return f"feeling {label} with intensity {intensity:.2f}"

    def get_history(self) -> List[EmotionState]:
        """获取情绪历史。"""
        return self._history.copy()

    def reset(self) -> None:
        """重置情绪状态。"""
        self._state = EmotionState()
        self._history.clear()
