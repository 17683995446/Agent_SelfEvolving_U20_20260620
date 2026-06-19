"""
情绪与动机建模模块。

引入好奇心、无聊等内状态，调节探索-利用平衡与风险偏好。

第一性原理：
- 情绪是内感受推理的简化输出，快速调节行为倾向
- 好奇心驱动对高预测误差区域的探索
- 无聊检测防止局部最优陷阱
"""

from typing import Any, Dict

from agent_core.common.logger import get_logger


class EmotionState:
    """
    情绪状态。

    封装当前情绪维度值。
    """

    def __init__(self) -> None:
        self.curiosity: float = 0.5
        self.boredom: float = 0.0
        self.anxiety: float = 0.0
        self.confidence: float = 0.5

    def to_dict(self) -> Dict[str, float]:
        """
        转换为字典。

        Returns:
            情绪维度字典。
        """
        return {
            "curiosity": self.curiosity,
            "boredom": self.boredom,
            "anxiety": self.anxiety,
            "confidence": self.confidence,
        }


class EmotionEngine:
    """
    情绪引擎。

    根据预测误差、任务多样性、时间衰减更新情绪状态。
    """

    def __init__(
        self,
        curiosity_threshold: float = 0.3,
        boredom_threshold: float = 0.8,
    ) -> None:
        self._curiosity_threshold = curiosity_threshold
        self._boredom_threshold = boredom_threshold
        self._state = EmotionState()
        self._error_history: list[float] = []
        self._task_type_history: list[str] = []
        self._stagnation_counter: int = 0
        self._logger = get_logger()

    def update(
        self,
        prediction_error: float,
        task_type: str,
        success: bool,
    ) -> EmotionState:
        """
        更新情绪状态。

        Args:
            prediction_error: 预测误差。
            task_type: 当前任务类型。
            success: 是否成功。

        Returns:
            更新后的情绪状态。
        """
        self._error_history.append(prediction_error)
        if len(self._error_history) > 20:
            self._error_history.pop(0)
        self._update_curiosity(prediction_error)
        self._update_boredom(task_type)
        self._update_anxiety(success)
        self._update_confidence()
        return self._state

    def _update_curiosity(self, prediction_error: float) -> None:
        """基于预测误差更新好奇心。"""
        if prediction_error > self._curiosity_threshold:
            self._state.curiosity = min(
                self._state.curiosity + 0.1, 1.0
            )
        else:
            self._state.curiosity = max(
                self._state.curiosity - 0.05, 0.0
            )

    def _update_boredom(self, task_type: str) -> None:
        """基于任务重复性更新无聊感。"""
        self._task_type_history.append(task_type)
        if len(self._task_type_history) > 10:
            self._task_type_history.pop(0)
        if len(self._task_type_history) >= 5:
            recent = self._task_type_history[-5:]
            unique = len(set(recent))
            if unique == 1:
                self._stagnation_counter += 1
            else:
                self._stagnation_counter = max(
                    self._stagnation_counter - 1, 0
                )
        self._state.boredom = min(
            self._stagnation_counter * 0.2, 1.0
        )

    def _update_anxiety(self, success: bool) -> None:
        """基于成功/失败更新焦虑。"""
        if not success:
            self._state.anxiety = min(
                self._state.anxiety + 0.15, 1.0
            )
        else:
            self._state.anxiety = max(
                self._state.anxiety - 0.1, 0.0
            )

    def _update_confidence(self) -> None:
        """基于近期成功率更新信心。"""
        if len(self._error_history) < 5:
            return
        recent_errors = self._error_history[-5:]
        avg_error = sum(recent_errors) / len(recent_errors)
        self._state.confidence = max(
            0.0, min(1.0, 1.0 - avg_error)
        )

    def get_state(self) -> EmotionState:
        """
        获取当前情绪状态。

        Returns:
            情绪状态对象。
        """
        return self._state

    def adjust_exploration_bias(self, base_rate: float) -> float:
        """
        根据情绪调整探索率。

        好奇心高则增加探索，无聊高则强制探索。

        Args:
            base_rate: 基础探索率。

        Returns:
            调整后的探索率。
        """
        bias = 0.0
        if self._state.curiosity > 0.7:
            bias += 0.1
        if self._state.boredom > self._boredom_threshold:
            bias += 0.2
        if self._state.anxiety > 0.7:
            bias -= 0.1
        return max(0.0, min(1.0, base_rate + bias))
