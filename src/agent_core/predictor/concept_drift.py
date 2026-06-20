"""
概念漂移检测器。

基于 ADWIN（ADaptive WINdowing）算法检测数据分布变化。
当检测到漂移时，触发模型重置而非增量污染。

第一性原理：
- 生物神经系统通过突触可塑性适应环境变化，旧记忆在全新环境下应让位于新学习
- 非平稳环境中，持续增量学习会导致模型被过时数据拖累
- 漂移检测应基于误差流的统计特性变化，而非单点异常

ADWIN 算法核心：
- 维护一个自适应窗口 W
- 检测窗口内是否存在两个子窗口 W0、W1，其均值差异具有统计显著性
- 若存在，则丢弃 W0，保留 W1（即"遗忘"旧数据）
"""

from collections import deque
from typing import Deque, List, Tuple

import numpy as np

from agent_core.common.logger import get_logger

# ADWIN 默认参数
_DELTA_DEFAULT = 0.002  # 显著性水平（越小越保守，漂移检测越严格）
_MIN_WINDOW_SIZE = 10   # 最小窗口大小（样本不足时不检测）
_MAX_WINDOW_SIZE = 500  # 最大窗口大小（防止内存膨胀）


class ConceptDriftDetector:
    """
    概念漂移检测器（基于 ADWIN 变体）。

    维护误差流的自适应窗口，检测均值显著变化。
    """

    def __init__(
        self,
        delta: float = _DELTA_DEFAULT,
        min_window: int = _MIN_WINDOW_SIZE,
        max_window: int = _MAX_WINDOW_SIZE,
    ) -> None:
        self._delta = delta
        self._min_window = min_window
        self._max_window = max_window
        self._window: Deque[float] = deque(maxlen=max_window)
        self._drift_count = 0
        self._last_drift_index = 0
        self._total_samples = 0
        self._logger = get_logger()

    def update(self, error: float) -> bool:
        """
        添加新误差样本，返回是否检测到漂移。

        Args:
            error: 当前样本的预测误差（非负）。

        Returns:
            True 表示检测到概念漂移，应触发模型重置。
        """
        error = float(np.nan_to_num(error, nan=0.0, posinf=1.0, neginf=0.0))
        error = max(0.0, error)  # 误差非负
        self._window.append(error)
        self._total_samples += 1
        if len(self._window) < self._min_window:
            return False
        return self._detect_drift()

    def _detect_drift(self) -> bool:
        """检测窗口内是否存在均值显著变化的分割点。"""
        window_list = list(self._window)
        n = len(window_list)
        if n < self._min_window:
            return False
        # 从中间附近开始向两侧搜索分割点（性能优化）
        # 检查多个候选分割点
        candidates = self._candidate_splits(n)
        for split in candidates:
            w0 = window_list[:split]
            w1 = window_list[split:]
            if len(w0) < self._min_window // 2 or len(w1) < self._min_window // 2:
                continue
            if self._is_significant(w0, w1):
                self._handle_drift(split)
                return True
        return False

    def _candidate_splits(self, n: int) -> List[int]:
        """生成候选分割点（性能优化：不遍历所有点）。"""
        # 取 1/4、1/3、1/2、2/3、3/4 处
        points = {
            n // 4,
            n // 3,
            n // 2,
            (2 * n) // 3,
            (3 * n) // 4,
        }
        return sorted(p for p in points if self._min_window // 2 <= p < n)

    def _is_significant(
        self, w0: List[float], w1: List[float]
    ) -> bool:
        """基于 Hoeffding bound 检验两子窗口均值差异是否显著。"""
        n0, n1 = len(w0), len(w1)
        mean0 = float(np.mean(w0))
        mean1 = float(np.mean(w1))
        diff = abs(mean0 - mean1)
        # Hoeffding bound: epsilon = sqrt(1/(2*n) * ln(4/delta))
        # 合并两窗口的 bound
        epsilon = self._hoeffding_bound(n0, n1)
        return diff > epsilon

    def _hoeffding_bound(self, n0: int, n1: int) -> float:
        """计算合并 Hoeffding bound。"""
        # 误差范围 [0, 1]，故 range = 1
        # 合并方差近似：1/(2*n0) + 1/(2*n1)
        variance_term = 1.0 / (2.0 * max(n0, 1)) + 1.0 / (2.0 * max(n1, 1))
        return float(np.sqrt(variance_term * np.log(4.0 / self._delta)))

    def _handle_drift(self, split: int) -> None:
        """处理漂移：保留分割点后的数据，丢弃之前。"""
        window_list = list(self._window)
        new_window = window_list[split:]
        self._window = deque(new_window, maxlen=self._max_window)
        self._drift_count += 1
        self._last_drift_index = self._total_samples
        self._logger.info(
            f"[DriftDetector] Drift detected #{self._drift_count} "
            f"at sample {self._total_samples}, "
            f"trimmed window to {len(self._window)} samples"
        )

    def reset(self) -> None:
        """完全重置检测器（漂移后模型重置时调用）。"""
        self._window.clear()
        self._last_drift_index = self._total_samples

    @property
    def drift_count(self) -> int:
        """累计漂移次数。"""
        return self._drift_count

    @property
    def window_size(self) -> int:
        """当前窗口大小。"""
        return len(self._window)

    @property
    def recent_mean(self) -> float:
        """近期误差均值。"""
        if not self._window:
            return 0.0
        return float(np.mean(list(self._window)))

    def get_stats(self) -> dict:
        """获取统计信息。"""
        return {
            "drift_count": self._drift_count,
            "window_size": len(self._window),
            "recent_mean": self.recent_mean,
            "total_samples": self._total_samples,
        }
