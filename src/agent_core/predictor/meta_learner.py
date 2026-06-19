"""
元学习模块。

在线调整预测器学习率与探索-利用比例。

第一性原理：
- 大脑通过神经调制系统动态调整可塑性
- 误差收敛速度反映当前学习率是否合适
- 环境稳定性决定探索与利用的权衡
"""

from typing import Any, Dict, List, Optional

from agent_core.common.logger import get_logger


class MetaLearner:
    """
    元学习器。

    根据近期误差趋势自适应调整学习参数。
    """

    def __init__(self) -> None:
        self._error_history: list[float] = []
        self._adaptation_rate_history: list[float] = []
        self._exploration_history: list[float] = []
        self._logger = get_logger()
        self._window_size: int = 10
        self._algorithm_scores: Dict[str, float] = {}
        self._algorithm_errors: Dict[str, list[float]] = {}

    def record_error(self, error: float) -> None:
        """
        记录误差。

        Args:
            error: 当前周期误差。
        """
        self._error_history.append(error)
        if len(self._error_history) > self._window_size * 2:
            self._error_history.pop(0)

    def record_adaptation_rate(self, rate: float) -> None:
        """
        记录当前适应率。

        Args:
            rate: 适应率值。
        """
        self._adaptation_rate_history.append(rate)
        if len(self._adaptation_rate_history) > self._window_size * 2:
            self._adaptation_rate_history.pop(0)

    def record_exploration_rate(self, rate: float) -> None:
        """
        记录当前探索率。

        Args:
            rate: 探索率值。
        """
        self._exploration_history.append(rate)
        if len(self._exploration_history) > self._window_size * 2:
            self._exploration_history.pop(0)

    def suggest_adaptation_rate(self, current_rate: float) -> float:
        """
        建议新的适应率。

        误差下降慢则增大，震荡则减小。

        Args:
            current_rate: 当前适应率。

        Returns:
            建议的适应率。
        """
        if len(self._error_history) < self._window_size:
            return current_rate
        recent = self._error_history[-self._window_size:]
        older = self._error_history[-self._window_size * 2:-self._window_size]
        if not older:
            return current_rate
        recent_mean = sum(recent) / len(recent)
        older_mean = sum(older) / len(older)
        trend = recent_mean - older_mean
        if trend > 0.01:
            new_rate = min(current_rate * 1.1, 0.5)
            self._logger.debug(
                f"[MetaLearner] Increase adaptation rate to {new_rate:.4f}"
            )
            return new_rate
        if trend < -0.01:
            new_rate = max(current_rate * 0.9, 0.001)
            self._logger.debug(
                f"[MetaLearner] Decrease adaptation rate to {new_rate:.4f}"
            )
            return new_rate
        return current_rate

    def suggest_exploration_rate(
        self, current_rate: float, environment_variance: float
    ) -> float:
        """
        建议新的探索率。

        环境变化大则增加探索，稳定则减少。

        Args:
            current_rate: 当前探索率。
            environment_variance: 环境方差。

        Returns:
            建议的探索率。
        """
        if environment_variance > 0.1:
            new_rate = min(current_rate + 0.05, 0.8)
        elif environment_variance < 0.01:
            new_rate = max(current_rate - 0.03, 0.1)
        else:
            new_rate = current_rate
        return round(new_rate, 4)

    def compute_environment_variance(self) -> float:
        """
        计算环境方差。

        Returns:
            误差历史的标准差。
        """
        if len(self._error_history) < 3:
            return 0.0
        recent = self._error_history[-self._window_size:]
        mean = sum(recent) / len(recent)
        variance = sum((e - mean) ** 2 for e in recent) / len(recent)
        return variance ** 0.5

    def record_algorithm_error(self, name: str, error: float) -> None:
        """记录指定算法的误差。"""
        if name not in self._algorithm_errors:
            self._algorithm_errors[name] = []
        self._algorithm_errors[name].append(error)
        if len(self._algorithm_errors[name]) > self._window_size * 2:
            self._algorithm_errors[name].pop(0)

    def suggest_best_algorithm(self, candidates: List[str]) -> Optional[str]:
        """
        根据历史误差建议最优算法。

        Args:
            candidates: 候选算法名称列表。

        Returns:
            最优算法名称，无数据返回None。
        """
        best: Optional[str] = None
        best_score = float("inf")
        for name in candidates:
            errors = self._algorithm_errors.get(name, [])
            if len(errors) < self._window_size:
                continue
            score = sum(errors[-self._window_size:]) / self._window_size
            if score < best_score:
                best_score = score
                best = name
        if best:
            self._logger.debug(f"[MetaLearner] Suggest algorithm: {best}")
        return best

    def get_meta_state(self) -> Dict[str, Any]:
        """获取元学习状态。"""
        return {
            "error_count": len(self._error_history),
            "latest_error": (
                self._error_history[-1] if self._error_history else None
            ),
            "env_variance": self.compute_environment_variance(),
            "algorithm_scores": {
                k: sum(v[-self._window_size:]) / min(len(v), self._window_size)
                for k, v in self._algorithm_errors.items()
            },
        }
