"""
多agent自组织与共识（阶段6：从协作到自组织群体智能）

第一性原理：社会性生物通过"角色分化→分工协作→共识决策"实现群体智能。
  - 角色分化：群体中不同个体承担不同角色（leader/worker/observer）
  - 分工协作：按角色和能力分派任务，各司其职
  - 共识决策：重要决策通过投票达成群体共识

SelfOrganizationEngine 实现：
  1. assign_role() — 分配/变更角色
  2. get_role() — 获取当前角色
  3. form_team() — 基于能力组队
  4. propose_decision() — 发起共识决策（leader发起）
  5. vote() — 投票（workers参与）
  6. run_organization_cycle() — 运行自组织周期
  7. get_status() — 状态

与MultiAgentCollaborator的关系：
  - SelfOrganizationEngine 依赖 MultiAgentCollaborator 进行通信和共识
  - 角色信息通过心跳广播，邻居可见
  - 共识决策使用 MultiAgentCollaborator.propose_consensus()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

from core.multi_agent_collaborator import MultiAgentCollaborator
from core.interfaces import ISelfOrganization


class AgentRole(Enum):
    """Agent角色"""
    FOLLOWER = "follower"    # 跟随者（默认，等待指令）
    CANDIDATE = "candidate"  # 候选人（竞选leader）
    LEADER = "leader"        # 领导者（协调任务分配）
    WORKER = "worker"        # 工作者（执行任务）
    OBSERVER = "observer"    # 观察者（只读，不执行任务）


@dataclass
class TeamInfo:
    """团队信息"""
    team_id: str
    leader_id: str
    members: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    formed_at: float = field(default_factory=time.time)
    task_description: str = ""


@dataclass
class DecisionRecord:
    """决策记录"""
    decision_id: str
    proposal: Dict[str, Any]
    proposer_id: str
    votes: Dict[str, bool] = field(default_factory=dict)
    status: str = "pending"  # pending/approved/rejected
    created_at: float = field(default_factory=time.time)
    decided_at: Optional[float] = None


class SelfOrganizationEngine(ISelfOrganization):
    """
    自组织引擎

    第一性原理：群体通过"角色分化→分工协作→共识决策"实现自组织。
    Leader负责协调，Workers负责执行，共识机制确保决策一致性。

    核心方法（<=7个）：
    1. assign_role() — 分配角色
    2. get_role() — 获取角色
    3. form_team() — 组队
    4. propose_decision() — 发起决策
    5. vote() — 投票
    6. run_organization_cycle() — 运行自组织周期
    7. get_status() — 状态
    """

    # 选举超时（秒）：leader多久没心跳则触发重新选举
    ELECTION_TIMEOUT = 10.0
    # 共识通过比例
    QUORUM_RATIO = 0.5

    def __init__(self,
                 collaborator: MultiAgentCollaborator,
                 logger=None):
        """
        Args:
            collaborator: 多agent协作器
            logger: 日志器
        """
        self.collaborator = collaborator
        self.agent_id = collaborator.agent_id
        self.logger = logger

        # 当前角色
        self._role: AgentRole = AgentRole.FOLLOWER
        # 已知的leader ID
        self._known_leader: Optional[str] = None
        self._last_leader_heartbeat: float = 0.0
        # 团队信息
        self._current_team: Optional[TeamInfo] = None
        # 决策记录
        self._decisions: Dict[str, DecisionRecord] = {}
        # 角色历史
        self._role_history: List[Dict[str, Any]] = []

        # 统计
        self._total_role_changes = 0
        self._total_teams_formed = 0
        self._total_decisions = 0
        self._total_decisions_approved = 0

    # ========================================================================
    # 公开方法
    # ========================================================================

    def assign_role(self, role: AgentRole, reason: str = "") -> None:
        """
        分配/变更角色

        第一性原理：群体中个体根据能力、负载和群体需要承担不同角色。
        Leader负责协调，Worker负责执行，Observer只观察不执行。

        Args:
            role: 新角色
            reason: 变更原因
        """
        old_role = self._role
        self._role = role
        self._total_role_changes += 1

        self._role_history.append({
            "timestamp": time.time(),
            "from": old_role.value,
            "to": role.value,
            "reason": reason,
        })

        if role == AgentRole.LEADER:
            self._known_leader = self.agent_id
            self._last_leader_heartbeat = time.time()

        if self.logger:
            self.logger.info(
                f"Role changed: {old_role.value}→{role.value} ({reason})"
            )

    def get_role(self) -> AgentRole:
        """获取当前角色"""
        return self._role

    def form_team(self,
                  task_description: str,
                  required_capabilities: List[str],
                  team_members: Optional[List[str]] = None) -> TeamInfo:
        """
        基于能力组队

        第一性原理：群体根据任务需求自动组队，选择具备所需能力的成员。
        Leader负责组队，Workers加入团队。

        Args:
            task_description: 任务描述
            required_capabilities: 所需能力列表
            team_members: 指定成员列表，None则自动选择

        Returns:
            团队信息
        """
        if team_members is None:
            # 自动选择：从邻居中选具备所需能力的
            team_members = []
            neighbors = self.collaborator.discovery.get_neighbors(alive_only=True)
            for neighbor in neighbors:
                if all(cap in neighbor.capabilities for cap in required_capabilities):
                    team_members.append(neighbor.agent_id)

        team_id = f"team_{self.agent_id}_{int(time.time() * 1000)}"
        team = TeamInfo(
            team_id=team_id,
            leader_id=self.agent_id,
            members=team_members,
            capabilities=required_capabilities,
            task_description=task_description,
        )
        self._current_team = team
        self._total_teams_formed += 1

        # 组队后自动成为leader
        if self._role != AgentRole.LEADER:
            self.assign_role(AgentRole.LEADER, reason=f"formed_team_{team_id}")

        if self.logger:
            self.logger.info(
                f"Team formed: {team_id} members={len(team_members)} "
                f"caps={required_capabilities}"
            )

        return team

    def propose_decision(self,
                         decision_id: str,
                         proposal: Dict[str, Any],
                         participant_ids: Optional[List[str]] = None,
                         on_approved: Optional[Callable] = None) -> Dict[str, Any]:
        """
        发起共识决策

        第一性原理：重要决策需要群体共识。Leader发起提案，Workers投票。
        达到quorum则通过，否则否决。

        Args:
            decision_id: 决策ID
            proposal: 提案内容
            participant_ids: 参与者列表，None则用团队成员
            on_approved: 通过后的回调

        Returns:
            {"decision_id": str, "status": str, "proposal": dict}
        """
        if self._role != AgentRole.LEADER:
            return {"decision_id": decision_id, "status": "not_leader",
                    "proposal": proposal, "error": "只有leader能发起决策"}

        if participant_ids is None:
            if self._current_team:
                participant_ids = self._current_team.members
            else:
                participant_ids = [
                    n.agent_id for n in self.collaborator.discovery.get_neighbors()
                ]

        # 创建决策记录
        decision = DecisionRecord(
            decision_id=decision_id,
            proposal=proposal,
            proposer_id=self.agent_id,
        )
        self._decisions[decision_id] = decision
        self._total_decisions += 1

        # 通过协作器发起共识
        self.collaborator.propose_consensus(
            proposal_id=decision_id,
            value=proposal,
            participant_ids=participant_ids,
            on_commit=lambda v: self._on_decision_approved(decision_id, v, on_approved),
        )

        return {
            "decision_id": decision_id,
            "status": "proposed",
            "proposal": proposal,
            "participants": participant_ids,
        }

    def vote(self, decision_id: str, vote_value: bool) -> Dict[str, Any]:
        """
        对决策投票

        第一性原理：个体根据自身判断对提案投票。
        简化策略：基于提案内容简单判断（实际可加入更复杂逻辑）。

        Args:
            decision_id: 决策ID
            vote_value: True=赞成, False=反对

        Returns:
            {"decision_id": str, "vote": bool, "status": str}
        """
        if decision_id not in self._decisions:
            # 记录别人发起的决策
            self._decisions[decision_id] = DecisionRecord(
                decision_id=decision_id,
                proposal={},
                proposer_id="",
            )

        decision = self._decisions[decision_id]
        decision.votes[self.agent_id] = vote_value

        return {
            "decision_id": decision_id,
            "vote": vote_value,
            "status": "voted",
        }

    def run_organization_cycle(self) -> Dict[str, Any]:
        """
        运行自组织周期

        第一性原理：群体周期性自组织——检查leader存活、触发选举、
        处理决策投票、更新角色。

        Returns:
            {"role": str, "leader": str, "team": dict, "decisions": int}
        """
        now = time.time()

        # 1. 检查leader存活（非leader才检查）
        if self._role != AgentRole.LEADER and self._known_leader:
            if now - self._last_leader_heartbeat > self.ELECTION_TIMEOUT:
                # Leader超时，触发选举
                self._start_election()

        # 2. Leader广播心跳
        if self._role == AgentRole.LEADER:
            self._last_leader_heartbeat = now
            self.collaborator.broadcast_heartbeat(
                load_score=0.0,
                metadata={"role": "leader", "team": self._current_team.team_id if self._current_team else None},
            )

        # 3. 处理消息
        self.collaborator.process_messages()

        # 4. 检查邻居的心跳元数据，更新已知leader
        for neighbor in self.collaborator.discovery.get_neighbors():
            role = neighbor.metadata.get("role")
            if role == "leader":
                self._known_leader = neighbor.agent_id
                self._last_leader_heartbeat = neighbor.last_seen
                if self._role == AgentRole.CANDIDATE:
                    # 发现已有leader，退回follower
                    self.assign_role(AgentRole.FOLLOWER, reason="found_existing_leader")

        return {
            "role": self._role.value,
            "leader": self._known_leader or "",
            "team": self._current_team.team_id if self._current_team else None,
            "decisions": len(self._decisions),
        }

    def get_status(self) -> Dict[str, Any]:
        """自组织状态"""
        return {
            "agent_id": self.agent_id,
            "role": self._role.value,
            "known_leader": self._known_leader,
            "has_team": self._current_team is not None,
            "team_id": self._current_team.team_id if self._current_team else None,
            "team_members": self._current_team.members if self._current_team else [],
            "total_decisions": len(self._decisions),
            "total_role_changes": self._total_role_changes,
            "total_teams_formed": self._total_teams_formed,
            "role_history": self._role_history[-5:],  # 最近5次角色变更
        }

    # ========================================================================
    # 内部方法
    # ========================================================================

    def _start_election(self) -> None:
        """触发选举：自己成为候选人"""
        if self._role == AgentRole.LEADER:
            return
        self.assign_role(AgentRole.CANDIDATE, reason="election_started")
        if self.logger:
            self.logger.info(f"Election started: {self.agent_id} is candidate")

    def _on_decision_approved(self, decision_id: str,
                               value: Dict[str, Any],
                               callback: Optional[Callable]) -> None:
        """决策通过回调"""
        decision = self._decisions.get(decision_id)
        if decision:
            decision.status = "approved"
            decision.decided_at = time.time()
            self._total_decisions_approved += 1

        if self.logger:
            self.logger.info(f"Decision approved: {decision_id}")

        if callback:
            try:
                callback(value)
            except Exception:
                pass
