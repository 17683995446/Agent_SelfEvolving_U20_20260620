"""
联邦学习聚合模块。

实现跨节点模型参数的安全聚合（FedAvg算法）。

第一性原理：
- 数据不出本地，只共享参数
- 聚合必须对异常值鲁棒
- 加权平均反映各节点数据量
"""

from typing import Any, Dict, List, Optional

import numpy as np

from agent_core.common.logger import get_logger


class FederatedAggregator:
    """
    联邦聚合器。

    收集各节点模型参数，执行加权平均聚合。
    """

    def __init__(self) -> None:
        self._updates: Dict[str, List[np.ndarray]] = {}
        self._weights: Dict[str, float] = {}
        self._logger = get_logger()

    def submit_update(
        self, node_id: str, params: List[np.ndarray], weight: float = 1.0
    ) -> None:
        """
        提交节点参数更新。

        Args:
            node_id: 节点标识。
            params: 模型参数列表（numpy数组）。
            weight: 该节点的数据权重。
        """
        self._updates[node_id] = [p.copy() for p in params]
        self._weights[node_id] = weight

    def aggregate(self) -> Optional[List[np.ndarray]]:
        """
        执行FedAvg聚合。

        Returns:
            聚合后的参数列表，无更新时返回None。
        """
        if not self._updates:
            return None
        total_weight = sum(self._weights.values())
        if total_weight == 0:
            return None
        result: List[np.ndarray] = []
        first_node = next(iter(self._updates))
        for i in range(len(self._updates[first_node])):
            weighted_sum = np.zeros_like(self._updates[first_node][i])
            for node_id, params in self._updates.items():
                w = self._weights[node_id] / total_weight
                weighted_sum += w * params[i]
            result.append(weighted_sum)
        self._logger.info(
            f"[FederatedAggregator] Aggregated {len(self._updates)} nodes"
        )
        return result

    def clear(self) -> None:
        """清空已收集的更新。"""
        self._updates.clear()
        self._weights.clear()

    def detect_outliers(
        self, threshold: float = 2.0
    ) -> List[str]:
        """
        检测异常节点（基于参数L2距离）。

        Args:
            threshold: 异常阈值（标准差倍数）。

        Returns:
            异常节点ID列表。
        """
        if len(self._updates) < 3:
            return []
        distances: Dict[str, float] = {}
        nodes = list(self._updates.keys())
        for i, node_a in enumerate(nodes):
            dists = []
            for j, node_b in enumerate(nodes):
                if i == j:
                    continue
                d = self._param_distance(
                    self._updates[node_a], self._updates[node_b]
                )
                dists.append(d)
            distances[node_a] = sum(dists) / len(dists)
        mean_dist = np.mean(list(distances.values()))
        std_dist = np.std(list(distances.values()))
        outliers = [
            nid for nid, d in distances.items()
            if d > mean_dist + threshold * std_dist
        ]
        return outliers

    def _param_distance(
        self, a: List[np.ndarray], b: List[np.ndarray]
    ) -> float:
        """计算两组参数的L2距离。"""
        total = 0.0
        for pa, pb in zip(a, b):
            total += float(np.linalg.norm(pa - pb))
        return total
