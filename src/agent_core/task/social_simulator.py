"""
社会仿真模块。

实现多智能体博弈、信誉机制与协作联盟。

第一性原理：
- 智能体通过交互建立社会结构
- 信誉降低交易成本
- 联盟增强集体收益
"""

from typing import Dict, List, Optional, Tuple

from agent_core.common.logger import get_logger


class AgentReputation:
    """
    智能体信誉。

    记录交互历史，计算信誉分数。
    """

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id
        self._cooperate_count = 0
        self._defect_count = 0
        self._total_interactions = 0

    def record_interaction(self, cooperated: bool) -> None:
        """
        记录一次交互结果。

        Args:
            cooperated: 对方是否合作。
        """
        self._total_interactions += 1
        if cooperated:
            self._cooperate_count += 1
        else:
            self._defect_count += 1

    def get_score(self) -> float:
        """
        获取信誉分数。

        Returns:
            信誉分数 [0, 1]。
        """
        if self._total_interactions == 0:
            return 0.5
        return self._cooperate_count / self._total_interactions

    def get_agent_id(self) -> str:
        """获取智能体ID。"""
        return self._agent_id


class Coalition:
    """
    协作联盟。

    智能体组成的协作群体。
    """

    def __init__(self, coalition_id: str) -> None:
        self._id = coalition_id
        self._members: List[str] = []
        self._shared_resources: float = 0.0

    def add_member(self, agent_id: str) -> bool:
        """
        添加成员。

        Args:
            agent_id: 智能体ID。

        Returns:
            是否添加成功。
        """
        if agent_id not in self._members:
            self._members.append(agent_id)
            return True
        return False

    def remove_member(self, agent_id: str) -> bool:
        """
        移除成员。

        Args:
            agent_id: 智能体ID。

        Returns:
            是否移除成功。
        """
        if agent_id in self._members:
            self._members.remove(agent_id)
            return True
        return False

    def contribute(self, amount: float) -> None:
        """
        贡献共享资源。

        Args:
            amount: 贡献数量。
        """
        self._shared_resources += amount

    def get_member_count(self) -> int:
        """获取成员数量。"""
        return len(self._members)

    def get_shared_resources(self) -> float:
        """获取共享资源。"""
        return self._shared_resources

    def get_members(self) -> List[str]:
        """获取成员列表。"""
        return self._members.copy()


class SocialSimulator:
    """
    社会仿真器。

    管理多智能体间的博弈、信誉与联盟。
    """

    def __init__(self) -> None:
        self._reputations: Dict[str, AgentReputation] = {}
        self._coalitions: Dict[str, Coalition] = {}
        self._logger = get_logger()

    def register_agent(self, agent_id: str) -> None:
        """
        注册智能体。

        Args:
            agent_id: 智能体ID。
        """
        if agent_id not in self._reputations:
            self._reputations[agent_id] = AgentReputation(agent_id)

    def record_interaction(
        self,
        agent_a: str,
        agent_b: str,
        a_cooperated: bool,
        b_cooperated: bool,
    ) -> None:
        """
        记录双向交互。

        Args:
            agent_a: 智能体A。
            agent_b: 智能体B。
            a_cooperated: A是否合作。
            b_cooperated: B是否合作。
        """
        self.register_agent(agent_a)
        self.register_agent(agent_b)
        self._reputations[agent_a].record_interaction(a_cooperated)
        self._reputations[agent_b].record_interaction(b_cooperated)

    def get_reputation(self, agent_id: str) -> float:
        """
        获取智能体信誉。

        Args:
            agent_id: 智能体ID。

        Returns:
            信誉分数。
        """
        rep = self._reputations.get(agent_id)
        if rep is None:
            return 0.5
        return rep.get_score()

    def create_coalition(self, coalition_id: str) -> Coalition:
        """
        创建联盟。

        Args:
            coalition_id: 联盟ID。

        Returns:
            联盟实例。
        """
        coalition = Coalition(coalition_id)
        self._coalitions[coalition_id] = coalition
        return coalition

    def join_coalition(
        self,
        agent_id: str,
        coalition_id: str,
    ) -> bool:
        """
        加入联盟。

        Args:
            agent_id: 智能体ID。
            coalition_id: 联盟ID。

        Returns:
            是否加入成功。
        """
        coalition = self._coalitions.get(coalition_id)
        if coalition is None:
            return False
        return coalition.add_member(agent_id)

    def get_coalition(self, coalition_id: str) -> Optional[Coalition]:
        """
        获取联盟。

        Args:
            coalition_id: 联盟ID。

        Returns:
            联盟实例或None。
        """
        return self._coalitions.get(coalition_id)

    def decide_action_tit_for_tat(
        self,
        agent_id: str,
        opponent_id: str,
    ) -> str:
        """
        以牙还牙策略决策。

        Args:
            agent_id: 自身ID。
            opponent_id: 对手ID。

        Returns:
            "cooperate" 或 "defect"。
        """
        rep = self._reputations.get(opponent_id)
        if rep is None or rep.get_score() >= 0.5:
            return "cooperate"
        return "defect"

    def get_agent_count(self) -> int:
        """获取注册智能体数量。"""
        return len(self._reputations)

    def get_coalition_count(self) -> int:
        """获取联盟数量。"""
        return len(self._coalitions)
