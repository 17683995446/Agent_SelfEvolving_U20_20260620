"""
拜占庭容错模块。

实现恶意节点检测，基于行为分析和投票一致性。

第一性原理：
- 恶意节点的行为必然偏离正常模式
- 多数诚实节点可压制少数恶意节点
- 检测必须基于可观测的行为而非意图
"""

from typing import Any, Dict, List, Optional, Set

from agent_core.common.logger import get_logger


class ByzantineDetector:
    """
    拜占庭节点检测器。

    通过行为分析识别可能的恶意节点。
    """

    def __init__(self, threshold_ratio: float = 0.33) -> None:
        self._threshold_ratio = threshold_ratio
        self._node_votes: Dict[str, List[Any]] = {}
        self._node_behaviors: Dict[str, Dict[str, Any]] = {}
        self._logger = get_logger()

    def record_vote(self, node_id: str, vote: Any) -> None:
        """
        记录节点投票。

        Args:
            node_id: 节点标识。
            vote: 投票值。
        """
        if node_id not in self._node_votes:
            self._node_votes[node_id] = []
        self._node_votes[node_id].append(vote)

    def record_behavior(
        self, node_id: str, behavior_type: str, detail: Any
    ) -> None:
        """
        记录节点行为。

        Args:
            node_id: 节点标识。
            behavior_type: 行为类型。
            detail: 行为详情。
        """
        if node_id not in self._node_behaviors:
            self._node_behaviors[node_id] = {}
        self._node_behaviors[node_id][behavior_type] = detail

    def detect_malicious(self, all_nodes: List[str]) -> List[str]:
        """
        检测可能的恶意节点。

        Args:
            all_nodes: 所有节点列表。

        Returns:
            可疑节点ID列表。
        """
        suspicious: Set[str] = set()
        suspicious.update(self._detect_vote_deviation(all_nodes))
        suspicious.update(self._detect_behavior_anomaly())
        return list(suspicious)

    def _detect_vote_deviation(self, all_nodes: List[str]) -> Set[str]:
        """基于投票偏离检测。"""
        suspicious: Set[str] = set()
        if not self._node_votes:
            return suspicious
        for node_id, votes in self._node_votes.items():
            if len(votes) < 2:
                continue
            recent = votes[-5:]
            others = [
                v for nid, vl in self._node_votes.items()
                if nid != node_id for v in vl[-5:]
            ]
            if not others:
                continue
            agreement = sum(1 for v in recent if v in others) / len(recent)
            if agreement < self._threshold_ratio:
                suspicious.add(node_id)
                self._logger.warning(
                    f"[ByzantineDetector] {node_id} vote deviation: {agreement:.2f}"
                )
        return suspicious

    def _detect_behavior_anomaly(self) -> Set[str]:
        """基于行为异常检测。"""
        suspicious: Set[str] = set()
        for node_id, behaviors in self._node_behaviors.items():
            if behaviors.get("timeout_count", 0) > 5:
                suspicious.add(node_id)
            if behaviors.get("invalid_message_count", 0) > 3:
                suspicious.add(node_id)
        return suspicious

    def clear_history(self, node_id: Optional[str] = None) -> None:
        """
        清除历史记录。

        Args:
            node_id: 指定节点，None则清除全部。
        """
        if node_id is None:
            self._node_votes.clear()
            self._node_behaviors.clear()
        else:
            self._node_votes.pop(node_id, None)
            self._node_behaviors.pop(node_id, None)
