"""
阶段6测试：多agent自组织与共识 — SelfOrganizationEngine

测试覆盖：
  1. SelfOrganizationEngine 基本功能（初始角色/状态）
  2. 角色分配与变更（assign_role + 历史记录）
  3. 角色查询（get_role）
  4. 组队（form_team — 指定成员）
  5. 组队（form_team — 自动从邻居选择）
  6. 组队后自动成为leader
  7. 共识决策（propose_decision — leader发起）
  8. 非leader不能发起决策
  9. 投票（vote）
  10. 自组织周期（run_organization_cycle — leader广播心跳）
  11. 自组织周期（follower检查leader存活）
  12. 选举触发（leader超时→候选人）
  13. 发现已有leader时候选人退回follower
  14. 决策通过回调（on_approved）
  15. Agent集成：assign_role + form_team + get_organization_status

第一性原理验证：
  - 群体通过角色分化实现分工
  - Leader负责协调和决策，Workers负责执行
  - 共识机制确保群体决策一致性
  - 选举机制确保leader失效后群体能自恢复
"""

import sys
import os
import time

# 确保能导入模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.self_organization import (
    SelfOrganizationEngine, AgentRole, TeamInfo, DecisionRecord,
)
from core.multi_agent_collaborator import MultiAgentCollaborator
from communication import MessageBus
from agent import SelfEvolvingAgent
from core.config import AgentConfig


# ============================================================================
# 测试框架
# ============================================================================

passed = 0
failed = 0


def assert_true(cond, msg):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [PASS] {msg}")
    else:
        failed += 1
        print(f"  [FAIL] {msg}")


def assert_eq(actual, expected, msg):
    assert_true(actual == expected, f"{msg} (expected={expected}, actual={actual})")


# ============================================================================
# 测试用例
# ============================================================================

def test_engine_basic():
    """测试1: SelfOrganizationEngine 基本功能"""
    print("\n--- 测试1: Engine 基本功能 ---")
    collab = MultiAgentCollaborator(agent_id="agent_a")
    engine = SelfOrganizationEngine(collaborator=collab)

    # 初始角色应为follower
    assert_eq(engine.get_role(), AgentRole.FOLLOWER, "初始角色=follower")

    # 状态
    status = engine.get_status()
    assert_eq(status["agent_id"], "agent_a", "状态agent_id正确")
    assert_eq(status["role"], "follower", "状态role=follower")
    assert_eq(status["has_team"], False, "初始无团队")
    assert_eq(status["total_role_changes"], 0, "初始无角色变更")
    assert_eq(status["total_teams_formed"], 0, "初始无组队")


def test_assign_role():
    """测试2: 角色分配与变更"""
    print("\n--- 测试2: 角色分配与变更 ---")
    collab = MultiAgentCollaborator(agent_id="agent_a")
    engine = SelfOrganizationEngine(collaborator=collab)

    # 分配leader角色
    engine.assign_role(AgentRole.LEADER, reason="elected")
    assert_eq(engine.get_role(), AgentRole.LEADER, "角色=leader")

    # 分配worker角色
    engine.assign_role(AgentRole.WORKER, reason="task_assigned")
    assert_eq(engine.get_role(), AgentRole.WORKER, "角色=worker")

    status = engine.get_status()
    assert_eq(status["total_role_changes"], 2, "2次角色变更")
    assert_eq(len(status["role_history"]), 2, "角色历史2条")
    assert_eq(status["role_history"][-1]["to"], "worker", "最近变更为worker")
    assert_eq(status["role_history"][-1]["from"], "leader", "最近变更从leader")


def test_assign_leader_sets_known_leader():
    """测试3: 分配leader时设置known_leader"""
    print("\n--- 测试3: 分配leader设置known_leader ---")
    collab = MultiAgentCollaborator(agent_id="agent_a")
    engine = SelfOrganizationEngine(collaborator=collab)

    engine.assign_role(AgentRole.LEADER, reason="self_elected")
    status = engine.get_status()
    assert_eq(status["known_leader"], "agent_a", "known_leader=自己")


def test_get_role():
    """测试4: 角色查询"""
    print("\n--- 测试4: 角色查询 ---")
    collab = MultiAgentCollaborator(agent_id="agent_a")
    engine = SelfOrganizationEngine(collaborator=collab)

    assert_eq(engine.get_role(), AgentRole.FOLLOWER, "初始follower")
    engine.assign_role(AgentRole.OBSERVER, reason="monitoring")
    assert_eq(engine.get_role(), AgentRole.OBSERVER, "变更为observer")


def test_form_team_with_members():
    """测试5: 组队 — 指定成员"""
    print("\n--- 测试5: 组队 — 指定成员 ---")
    collab = MultiAgentCollaborator(agent_id="agent_a")
    engine = SelfOrganizationEngine(collaborator=collab)

    team = engine.form_team(
        task_description="数据处理任务",
        required_capabilities=["compute", "storage"],
        team_members=["agent_b", "agent_c"],
    )

    assert_true(isinstance(team, TeamInfo), "返回TeamInfo")
    assert_eq(team.leader_id, "agent_a", "leader=agent_a")
    assert_eq(len(team.members), 2, "2个成员")
    assert_true("agent_b" in team.members, "包含agent_b")
    assert_true("agent_c" in team.members, "包含agent_c")
    assert_eq(len(team.capabilities), 2, "2个能力")
    assert_true("compute" in team.capabilities, "能力含compute")

    status = engine.get_status()
    assert_eq(status["has_team"], True, "有团队")
    assert_eq(status["total_teams_formed"], 1, "组队1次")


def test_form_team_auto_select():
    """测试6: 组队 — 自动从邻居选择"""
    print("\n--- 测试6: 组队 — 自动从邻居选择 ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
    collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)

    # B注册能力并广播心跳
    collab_b.register_capability("compute", lambda p: None)
    collab_b.broadcast_heartbeat(load_score=0.2)
    collab_a.process_messages()

    engine = SelfOrganizationEngine(collaborator=collab_a)
    team = engine.form_team(
        task_description="计算任务",
        required_capabilities=["compute"],
        team_members=None,  # 自动选择
    )

    # 应自动选中agent_b
    assert_true("agent_b" in team.members, "自动选中agent_b")


def test_form_team_makes_leader():
    """测试7: 组队后自动成为leader"""
    print("\n--- 测试7: 组队后自动成为leader ---")
    collab = MultiAgentCollaborator(agent_id="agent_a")
    engine = SelfOrganizationEngine(collaborator=collab)

    assert_eq(engine.get_role(), AgentRole.FOLLOWER, "组队前是follower")
    engine.form_team(
        task_description="任务",
        required_capabilities=["compute"],
        team_members=["agent_b"],
    )
    assert_eq(engine.get_role(), AgentRole.LEADER, "组队后是leader")


def test_propose_decision_as_leader():
    """测试8: 共识决策 — leader发起"""
    print("\n--- 测试8: leader发起决策 ---")
    collab = MultiAgentCollaborator(agent_id="agent_a")
    engine = SelfOrganizationEngine(collaborator=collab)

    # 先成为leader
    engine.assign_role(AgentRole.LEADER, reason="test")
    engine.form_team(
        task_description="任务",
        required_capabilities=["compute"],
        team_members=["agent_b", "agent_c"],
    )

    result = engine.propose_decision(
        decision_id="dec_1",
        proposal={"action": "execute_plan", "priority": "high"},
        participant_ids=["agent_b", "agent_c"],
    )

    assert_eq(result["decision_id"], "dec_1", "决策ID正确")
    assert_eq(result["status"], "proposed", "状态=proposed")
    assert_true("action" in result["proposal"], "提案含action")
    assert_eq(len(result["participants"]), 2, "2个参与者")


def test_propose_decision_non_leader_rejected():
    """测试9: 非leader不能发起决策"""
    print("\n--- 测试9: 非leader不能发起决策 ---")
    collab = MultiAgentCollaborator(agent_id="agent_a")
    engine = SelfOrganizationEngine(collaborator=collab)

    # 仍是follower
    result = engine.propose_decision(
        decision_id="dec_1",
        proposal={"action": "test"},
        participant_ids=["agent_b"],
    )

    assert_eq(result["status"], "not_leader", "状态=not_leader")
    assert_true("error" in result, "包含错误信息")


def test_vote():
    """测试10: 投票"""
    print("\n--- 测试10: 投票 ---")
    collab = MultiAgentCollaborator(agent_id="agent_a")
    engine = SelfOrganizationEngine(collaborator=collab)

    # 对一个决策投票（即使该决策不是自己发起的）
    result = engine.vote("dec_external", vote_value=True)
    assert_eq(result["decision_id"], "dec_external", "决策ID正确")
    assert_eq(result["vote"], True, "投票=True")
    assert_eq(result["status"], "voted", "状态=voted")

    # 投反对票
    result2 = engine.vote("dec_external2", vote_value=False)
    assert_eq(result2["vote"], False, "投票=False")


def test_run_organization_cycle_as_leader():
    """测试11: 自组织周期 — leader广播心跳"""
    print("\n--- 测试11: leader周期广播心跳 ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
    collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)

    engine_a = SelfOrganizationEngine(collaborator=collab_a)
    engine_a.assign_role(AgentRole.LEADER, reason="test")
    engine_a.form_team(
        task_description="任务",
        required_capabilities=["compute"],
        team_members=["agent_b"],
    )

    # A运行周期
    result = engine_a.run_organization_cycle()
    assert_eq(result["role"], "leader", "角色=leader")
    assert_eq(result["leader"], "agent_a", "leader=agent_a")

    # B处理消息后应发现A是leader
    collab_b.process_messages()
    neighbors_b = collab_b.discovery.get_neighbors()
    assert_true(len(neighbors_b) >= 1, "B发现邻居")
    b_neighbor = neighbors_b[0]
    assert_eq(b_neighbor.metadata.get("role"), "leader", "B看到A是leader")


def test_run_organization_cycle_follower_detects_leader():
    """测试12: follower通过周期发现leader"""
    print("\n--- 测试12: follower发现leader ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
    collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)

    engine_a = SelfOrganizationEngine(collaborator=collab_a)
    engine_b = SelfOrganizationEngine(collaborator=collab_b)

    # A成为leader并广播
    engine_a.assign_role(AgentRole.LEADER, reason="test")
    engine_a.run_organization_cycle()

    # B运行周期，应发现A是leader
    result = engine_b.run_organization_cycle()
    assert_eq(result["role"], "follower", "B仍是follower")
    assert_eq(result["leader"], "agent_a", "B发现leader=agent_a")


def test_election_triggered_on_leader_timeout():
    """测试13: leader超时触发选举"""
    print("\n--- 测试13: leader超时触发选举 ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
    collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)

    engine_a = SelfOrganizationEngine(collaborator=collab_a)
    engine_b = SelfOrganizationEngine(collaborator=collab_b)

    # A成为leader
    engine_a.assign_role(AgentRole.LEADER, reason="test")
    engine_a.run_organization_cycle()
    collab_b.process_messages()
    engine_b.run_organization_cycle()

    # B现在知道leader是A
    assert_eq(engine_b.get_role(), AgentRole.FOLLOWER, "B是follower")
    status_b = engine_b.get_status()
    assert_eq(status_b["known_leader"], "agent_a", "B知道leader=A")

    # 模拟leader超时：把B的last_leader_heartbeat和邻居表中A的last_seen都设到很久以前
    # 这样step1检测到超时触发选举，step4因A已stale不会发现leader，候选人不会退回
    stale_time = time.time() - engine_b.ELECTION_TIMEOUT - 1
    engine_b._last_leader_heartbeat = stale_time
    for neighbor in collab_b.discovery._neighbors.values():
        if neighbor.metadata.get("role") == "leader":
            neighbor.last_seen = stale_time

    # 再次运行周期，应触发选举
    result = engine_b.run_organization_cycle()
    assert_eq(engine_b.get_role(), AgentRole.CANDIDATE, "B变为candidate（选举触发）")


def test_candidate_steps_down_on_existing_leader():
    """测试14: 候选人发现已有leader时退回follower"""
    print("\n--- 测试14: 候选人退回follower ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
    collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)

    engine_a = SelfOrganizationEngine(collaborator=collab_a)
    engine_b = SelfOrganizationEngine(collaborator=collab_b)

    # B先成为候选人
    engine_b.assign_role(AgentRole.CANDIDATE, reason="election")
    assert_eq(engine_b.get_role(), AgentRole.CANDIDATE, "B是candidate")

    # A成为leader并广播
    engine_a.assign_role(AgentRole.LEADER, reason="test")
    engine_a.run_organization_cycle()

    # B运行周期，应发现A是leader并退回follower
    engine_b.run_organization_cycle()
    assert_eq(engine_b.get_role(), AgentRole.FOLLOWER, "B退回follower")


def test_decision_approved_callback():
    """测试15: 决策通过回调"""
    print("\n--- 测试15: 决策通过回调 ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
    collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)

    engine_a = SelfOrganizationEngine(collaborator=collab_a)
    engine_a.assign_role(AgentRole.LEADER, reason="test")
    engine_a.form_team(
        task_description="任务",
        required_capabilities=["compute"],
        team_members=["agent_b"],
    )

    callback_called = []
    engine_a.propose_decision(
        decision_id="dec_1",
        proposal={"action": "execute"},
        participant_ids=["agent_b"],
        on_approved=lambda v: callback_called.append(v),
    )

    # 模拟共识通过：手动触发回调
    engine_a._on_decision_approved("dec_1", {"action": "execute"}, None)
    # 由于我们传了callback=None给_on_decision_approved，需要重新测试
    # 实际上propose_decision内部注册了callback，但_on_decision_approved的callback参数是None
    # 让我们直接测试callback路径

    # 重新发起一个带回调的决策
    callback_called2 = []
    engine_a.propose_decision(
        decision_id="dec_2",
        proposal={"action": "execute2"},
        participant_ids=["agent_b"],
        on_approved=lambda v: callback_called2.append(v),
    )

    # 直接调用内部回调（模拟共识通过）
    decision = engine_a._decisions.get("dec_2")
    assert_true(decision is not None, "决策记录存在")
    assert_eq(decision.status, "pending", "初始状态=pending")

    # 模拟共识引擎调用commit回调
    # propose_decision内部注册了 lambda v: self._on_decision_approved(decision_id, v, on_approved)
    # 所以我们需要通过collaborator的consensus机制触发
    # 简化测试：直接验证决策记录状态变化
    engine_a._on_decision_approved("dec_2", {"action": "execute2"},
                                    lambda v: callback_called2.append(v))
    assert_eq(len(callback_called2), 1, "回调被调用1次")
    assert_eq(callback_called2[0]["action"], "execute2", "回调收到正确提案")

    decision = engine_a._decisions.get("dec_2")
    assert_eq(decision.status, "approved", "决策状态=approved")


def test_agent_integration_assign_role():
    """测试16: Agent集成 — assign_role"""
    print("\n--- 测试16: Agent集成assign_role ---")
    config = AgentConfig()
    config.agent_name = "test_agent_org"
    agent = SelfEvolvingAgent(config=config)

    # 初始角色
    status = agent.get_organization_status()
    assert_eq(status["role"], "follower", "初始follower")

    # 分配leader
    result = agent.assign_role("leader", reason="test")
    assert_eq(result["role"], "leader", "角色=leader")
    assert_eq(result["changed"], True, "发生了变更")
    assert_eq(result["previous_role"], "follower", "之前是follower")

    # 验证状态
    status = agent.get_organization_status()
    assert_eq(status["role"], "leader", "状态role=leader")
    assert_eq(status["total_role_changes"], 1, "1次角色变更")


def test_agent_integration_unknown_role():
    """测试17: Agent集成 — 未知角色"""
    print("\n--- 测试17: 未知角色 ---")
    config = AgentConfig()
    config.agent_name = "test_agent_org2"
    agent = SelfEvolvingAgent(config=config)

    result = agent.assign_role("unknown_role", reason="test")
    assert_eq(result["changed"], False, "未变更")
    assert_true("error" in result, "包含错误信息")


def test_agent_integration_form_team():
    """测试18: Agent集成 — form_team"""
    print("\n--- 测试18: Agent集成form_team ---")
    config = AgentConfig()
    config.agent_name = "test_agent_org3"
    agent = SelfEvolvingAgent(config=config)

    result = agent.form_team(
        task_description="测试任务",
        required_capabilities=["compute"],
        team_members=["agent_x", "agent_y"],
    )

    assert_true("team_id" in result, "返回team_id")
    assert_eq(result["leader_id"], "test_agent_org3", "leader是自己")
    assert_eq(len(result["members"]), 2, "2个成员")
    assert_eq(result["task_description"], "测试任务", "任务描述正确")

    # 验证状态
    status = agent.get_organization_status()
    assert_eq(status["has_team"], True, "有团队")
    assert_eq(status["role"], "leader", "组队后是leader")


def test_agent_integration_vote():
    """测试19: Agent集成 — vote"""
    print("\n--- 测试19: Agent集成vote ---")
    config = AgentConfig()
    config.agent_name = "test_agent_org4"
    agent = SelfEvolvingAgent(config=config)

    result = agent.vote("decision_1", True)
    assert_eq(result["decision_id"], "decision_1", "决策ID正确")
    assert_eq(result["vote"], True, "投票=True")
    assert_eq(result["status"], "voted", "状态=voted")


def test_agent_integration_get_status_includes_organization():
    """测试20: Agent.get_status包含organization_status"""
    print("\n--- 测试20: get_status包含organization_status ---")
    config = AgentConfig()
    config.agent_name = "test_agent_org5"
    agent = SelfEvolvingAgent(config=config)

    status = agent.get_status()
    assert_true("organization_status" in status, "包含organization_status")
    assert_eq(status["organization_status"]["role"], "follower", "角色=follower")
    assert_eq(status["organization_status"]["agent_id"], "test_agent_org5", "agent_id正确")


def test_agent_integration_run_organization_cycle():
    """测试21: Agent集成 — run_organization_cycle"""
    print("\n--- 测试21: Agent集成run_organization_cycle ---")
    config = AgentConfig()
    config.agent_name = "test_agent_org6"
    agent = SelfEvolvingAgent(config=config)

    # 作为follower运行周期
    result = agent.run_organization_cycle()
    assert_eq(result["role"], "follower", "角色=follower")
    assert_true("leader" in result, "包含leader字段")
    assert_true("decisions" in result, "包含decisions字段")


def test_role_history_bounded():
    """测试22: 角色历史有界（最近5条）"""
    print("\n--- 测试22: 角色历史有界 ---")
    collab = MultiAgentCollaborator(agent_id="agent_a")
    engine = SelfOrganizationEngine(collaborator=collab)

    # 进行10次角色变更
    for i in range(10):
        engine.assign_role(AgentRole.WORKER if i % 2 == 0 else AgentRole.OBSERVER,
                           reason=f"change_{i}")

    status = engine.get_status()
    # role_history在get_status中只返回最近5条
    assert_eq(len(status["role_history"]), 5, "只返回最近5条历史")
    # 但total_role_changes是完整计数
    assert_eq(status["total_role_changes"], 10, "总共10次变更")


def test_multiple_agents_organization():
    """测试23: 多agent自组织场景"""
    print("\n--- 测试23: 多agent自组织场景 ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="leader_a", message_bus=bus)
    collab_b = MultiAgentCollaborator(agent_id="worker_b", message_bus=bus)
    collab_c = MultiAgentCollaborator(agent_id="worker_c", message_bus=bus)

    engine_a = SelfOrganizationEngine(collaborator=collab_a)
    engine_b = SelfOrganizationEngine(collaborator=collab_b)
    engine_c = SelfOrganizationEngine(collaborator=collab_c)

    # A成为leader并组队
    engine_a.assign_role(AgentRole.LEADER, reason="bootstrap")
    team = engine_a.form_team(
        task_description="群体任务",
        required_capabilities=["compute"],
        team_members=["worker_b", "worker_c"],
    )
    assert_eq(len(team.members), 2, "团队2个成员")

    # A广播心跳
    engine_a.run_organization_cycle()

    # B和C运行周期，应发现A是leader
    engine_b.run_organization_cycle()
    engine_c.run_organization_cycle()

    assert_eq(engine_b.get_role(), AgentRole.FOLLOWER, "B是follower")
    assert_eq(engine_c.get_role(), AgentRole.FOLLOWER, "C是follower")
    assert_eq(engine_b.get_status()["known_leader"], "leader_a", "B知道leader=A")
    assert_eq(engine_c.get_status()["known_leader"], "leader_a", "C知道leader=A")


# ============================================================================
# 主函数
# ============================================================================

def _cleanup_persistent_state():
    """清理测试产生的持久化状态（秩序化阶段1：测试数据隔离）"""
    import glob
    for f in ["./data/memory.db", "./data/goals_state.json"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    for pattern in ["./data/skills/*.py", "./data/checkpoints/*.json"]:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except OSError:
                pass


def main():
    _cleanup_persistent_state()
    print("=" * 70)
    print("阶段6测试：多agent自组织与共识 — SelfOrganizationEngine")
    print("=" * 70)

    tests = [
        test_engine_basic,
        test_assign_role,
        test_assign_leader_sets_known_leader,
        test_get_role,
        test_form_team_with_members,
        test_form_team_auto_select,
        test_form_team_makes_leader,
        test_propose_decision_as_leader,
        test_propose_decision_non_leader_rejected,
        test_vote,
        test_run_organization_cycle_as_leader,
        test_run_organization_cycle_follower_detects_leader,
        test_election_triggered_on_leader_timeout,
        test_candidate_steps_down_on_existing_leader,
        test_decision_approved_callback,
        test_agent_integration_assign_role,
        test_agent_integration_unknown_role,
        test_agent_integration_form_team,
        test_agent_integration_vote,
        test_agent_integration_get_status_includes_organization,
        test_agent_integration_run_organization_cycle,
        test_role_history_bounded,
        test_multiple_agents_organization,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            global failed
            failed += 1
            print(f"  [ERROR] {test.__name__}: {e}")
            import traceback
            traceback.print_exc()

    _cleanup_persistent_state()

    print("\n" + "=" * 70)
    print(f"测试结果: {passed} passed, {failed} failed")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
