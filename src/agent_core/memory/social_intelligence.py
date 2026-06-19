"""
社会智能模块。

多Agent博弈策略、信誉机制与联盟形成。

第一性原理：
- 社会性动物通过互惠利他获得进化优势
- 信誉机制防止搭便车行为
- 联盟将局部优势转化为全局收益
"""

from typing import Any, Dict, List, Optional

from agent_core.common.logger import get_logger


class ReputationTracker:
    """
    信誉追踪器。

    记录其他Agent的历史合作行为。
    """

    def __init__(self, decay_factor: float = 0.95) -> None:
        self._decay_factor = decay_factor
        self._reputations: Dict[str, float] = {}
        self._interactions: Dict[str, List[bool]] = {}
        self._logger = get_logger()

    def record_interaction(self, agent_id: str, cooperated: bool) -> None:
        """
        记录一次交互结果。

        Args:
            agent_id: 对方Agent ID。
            cooperated: 是否合作。
        """
        if agent_id not in self._interactions:
            self._interactions[agent_id] = []
        self._interactions[agent_id].append(cooperated)
        recent = self._interactions[agent_id][-10:]
        score = sum(1.0 for c in recent if c) / len(recent)
        self._reputations[agent_id] = score

    def get_reputation(self, agent_id: str) -> float:
        """
        获取Agent信誉分。

        Args:
            agent_id: Agent ID。

        Returns:
            信誉分，范围为[0, 1]，无记录返回0.5。
        """
        return self._reputations.get(agent_id, 0.5)

    def decay_reputations(self) -> None:
        """对所有信誉分进行衰减。"""
        for agent_id in self._reputations:
            self._reputations[agent_id] = (
                0.5
                + (self._reputations[agent_id] - 0.5)
                * self._decay_factor
            )

    def get_trusted_agents(self, threshold: float = 0.6) -> List[str]:
        """
        获取可信Agent列表。

        Args:
            threshold: 信誉阈值。

        Returns:
            可信Agent ID列表。
        """
        return [
            aid
            for aid, score in self._reputations.items()
            if score >= threshold
        ]


class CoalitionManager:
    """
    联盟管理器。

    动态组建Agent联盟完成复杂任务。
    """

    def __init__(self) -> None:
        self._coalitions: Dict[str, List[str]] = {}
        self._logger = get_logger()

    def form_coalition(
        self,
        coalition_id: str,
        agent_ids: List[str],
        reputation_tracker: ReputationTracker,
    ) -> bool:
        """
        组建联盟。

        Args:
            coalition_id: 联盟ID。
            agent_ids: 候选Agent ID列表。
            reputation_tracker: 信誉追踪器。

        Returns:
            成功组建返回True。
        """
        trusted = [
            aid
            for aid in agent_ids
            if reputation_tracker.get_reputation(aid) >= 0.5
        ]
        if len(trusted) < 2:
            self._logger.warning(
                f"[CoalitionManager] Not enough trusted agents for {coalition_id}"
            )
            return False
        self._coalitions[coalition_id] = trusted
        self._logger.info(
            f"[CoalitionManager] Formed {coalition_id} with {len(trusted)} agents"
        )
        return True

    def dissolve_coalition(self, coalition_id: str) -> None:
        """
        解散联盟。

        Args:
            coalition_id: 联盟ID。
        """
        if coalition_id in self._coalitions:
            del self._coalitions[coalition_id]
            self._logger.info(
                f"[CoalitionManager] Dissolved {coalition_id}"
            )

    def get_members(self, coalition_id: str) -> List[str]:
        """
        获取联盟成员。

        Args:
            coalition_id: 联盟ID。

        Returns:
            成员ID列表。
        """
        return self._coalitions.get(coalition_id, []).copy()

    def list_coalitions(self) -> List[str]:
        """
        列出所有联盟。

        Returns:
            联盟ID列表。
        """
        return list(self._coalitions.keys())


class GameTheoreticStrategy:
    """
    博弈论策略。

    实现近似纳什均衡的决策策略。
    """

    def __init__(self) -> None:
        self._logger = get_logger()

    def choose_action(
        self,
        agent_id: str,
        reputation_tracker: ReputationTracker,
        payoff_matrix: Dict[str, Dict[str, float]],
    ) -> str:
        """
        选择博弈动作。

        使用信誉加权选择最优响应。

        Args:
            agent_id: 对方Agent ID。
            reputation_tracker: 信誉追踪器。
            payoff_matrix: 收益矩阵 {"cooperate": {"cooperate": 3, "defect": 0}, ...}。

        Returns:
            选择的动作 "cooperate" 或 "defect"。
        """
        reputation = reputation_tracker.get_reputation(agent_id)
        coop_payoff = (
            payoff_matrix.get("cooperate", {}).get("cooperate", 0.0)
            * reputation
            + payoff_matrix.get("cooperate", {}).get("defect", 0.0)
            * (1.0 - reputation)
        )
        defect_payoff = (
            payoff_matrix.get("defect", {}).get("cooperate", 0.0)
            * reputation
            + payoff_matrix.get("defect", {}).get("defect", 0.0)
            * (1.0 - reputation)
        )
        if coop_payoff >= defect_payoff:
            return "cooperate"
        return "defect"

    def tit_for_tat(
        self,
        agent_id: str,
        last_opponent_action: Optional[str],
    ) -> str:
        """
        以牙还牙策略。

        Args:
            agent_id: 对方Agent ID。
            last_opponent_action: 对方上次动作。

        Returns:
            本次动作。
        """
        if last_opponent_action is None:
            return "cooperate"
        return last_opponent_action
