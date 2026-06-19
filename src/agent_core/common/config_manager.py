"""
配置管理器模块。

支持运行时动态调整参数，无需重启系统。

第一性原理：
- 生物通过反馈回路实时调节内稳态参数
- 配置变更应即时生效，不中断运行
- 参数调整基于性能反馈自适应
"""

import copy
import threading
import time
from typing import Any, Dict, Optional

from agent_core.common.logger import get_logger


class ConfigManager:
    """
    配置管理器。

    单例模式，全局统一配置存储与动态更新。
    """

    _instance: "ConfigManager" = None  # type: ignore[assignment]

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup()
        return cls._instance

    def _setup(self) -> None:
        self._config: Dict[str, Any] = {}
        self._history: Dict[str, list] = {}
        self._logger = get_logger()
        self._window_seconds: float = 300.0
        self._max_history: int = 100
        # Bug28修复：增加线程锁，保护并发读写（事件循环线程与Dashboard HTTP线程）
        self._lock = threading.RLock()

    def load(self, config: Dict[str, Any]) -> None:
        """
        加载配置（深拷贝避免共享引用）。

        Args:
            config: 配置字典。
        """
        with self._lock:
            self._config = copy.deepcopy(config)
        self._logger.info("[ConfigManager] Config loaded")

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值。

        Args:
            key: 配置键名。
            default: 默认值。

        Returns:
            配置值。
        """
        with self._lock:
            # Bug28修复：返回深拷贝避免外部修改污染内部状态
            value = self._config.get(key, default)
        return copy.deepcopy(value) if value is not None else default

    def set(self, key: str, value: Any) -> None:
        """
        动态设置配置值（深拷贝避免外部修改污染内部状态）。

        Args:
            key: 配置键名。
            value: 配置值。
        """
        with self._lock:
            old_value = self._config.get(key)
            self._config[key] = copy.deepcopy(value)
            self._record_history(key, old_value, value)
        self._logger.info(
            f"[ConfigManager] Config updated: {key} = {value}"
        )

    def _record_history(
        self, key: str, old_value: Any, new_value: Any
    ) -> None:
        """记录配置变更历史，限制上限。"""
        if key not in self._history:
            self._history[key] = []
        self._history[key].append(
            (time.time(), old_value, new_value)
        )
        if len(self._history[key]) > self._max_history:
            self._history[key] = self._history[key][-self._max_history:]

    def get_history(self, key: str) -> list:
        """
        获取配置变更历史。

        Args:
            key: 配置键名。

        Returns:
            变更历史列表。
        """
        return self._history.get(key, [])

    def adapt_exploration_rate(self, recent_errors: list[tuple[float, float]]) -> None:
        """
        根据近期误差自适应调整探索率。

        Args:
            recent_errors: (timestamp, error) 列表。
        """
        filtered = self._filter_window(recent_errors)
        if not filtered:
            return
        avg_error = sum(filtered) / len(filtered)
        current_rate = self.get("exploration_rate", 0.3)
        new_rate = self._compute_exploration_rate(current_rate, avg_error)
        if new_rate != current_rate:
            self.set("exploration_rate", new_rate)

    def _filter_window(self, entries: list[tuple[float, Any]]) -> list[Any]:
        """过滤时间窗口内的条目。"""
        cutoff = time.time() - self._window_seconds
        return [v for ts, v in entries if ts >= cutoff]

    def _compute_exploration_rate(
        self, current_rate: float, avg_error: float
    ) -> float:
        """计算新的探索率。"""
        if avg_error > 0.5:
            return min(current_rate + 0.05, 0.8)
        if avg_error < 0.1:
            return max(current_rate - 0.05, 0.1)
        return current_rate

    def adapt_epsilon(self, recent_rewards: list[tuple[float, float]]) -> None:
        """
        根据近期奖励自适应调整epsilon。

        Args:
            recent_rewards: (timestamp, reward) 列表。
        """
        filtered = self._filter_window(recent_rewards)
        if not filtered:
            return
        avg_reward = sum(filtered) / len(filtered)
        current_epsilon = self.get("epsilon", 0.2)
        new_epsilon = self._compute_epsilon(current_epsilon, avg_reward)
        if new_epsilon != current_epsilon:
            self.set("epsilon", new_epsilon)

    def _compute_epsilon(
        self, current_epsilon: float, avg_reward: float
    ) -> float:
        """计算新的epsilon值。"""
        if avg_reward < 0.3:
            return min(current_epsilon + 0.05, 0.5)
        if avg_reward > 0.7:
            return max(current_epsilon - 0.05, 0.05)
        return current_epsilon

    def adapt_interrupt_threshold(self, recent_interrupts: list[tuple[float, int]]) -> None:
        """
        根据中断频率调整中断阈值。

        Args:
            recent_interrupts: (timestamp, count) 列表。
        """
        filtered = self._filter_window(recent_interrupts)
        if not filtered:
            return
        total = sum(filtered)
        current_threshold = self.get("interrupt_threshold", 0.7)
        new_threshold = self._compute_interrupt_threshold(
            current_threshold, total
        )
        if new_threshold != current_threshold:
            self.set("interrupt_threshold", new_threshold)

    def _compute_interrupt_threshold(
        self, current_threshold: float, interrupts: int
    ) -> float:
        """计算新的中断阈值。"""
        if interrupts > 10:
            return min(current_threshold + 0.05, 0.9)
        if interrupts < 2:
            return max(current_threshold - 0.05, 0.5)
        return current_threshold

    def get_all(self) -> Dict[str, Any]:
        """
        获取全部配置。

        Returns:
            配置字典。
        """
        with self._lock:
            return copy.deepcopy(self._config)

    @classmethod
    def reset_for_testing(cls) -> None:
        """重置单例，用于测试隔离。"""
        cls._instance = None


def get_config_manager() -> ConfigManager:
    """
    获取配置管理器实例。

    Returns:
        ConfigManager实例。
    """
    return ConfigManager()
