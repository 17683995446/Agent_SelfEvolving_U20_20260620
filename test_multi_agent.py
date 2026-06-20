"""
阶段3测试：多agent协作框架 — 从单兵到群体协作

测试覆盖：
  1. MultiAgentCollaborator 基本功能（注册能力/状态）
  2. 心跳广播与邻居发现
  3. 任务分派（按能力匹配）
  4. 任务接收与执行（handler调用）
  5. 任务结果回传（RESULT消息）
  6. 超时重分派
  7. 共识提案（2PC）
  8. 多agent协作场景（2个agent互相分派任务）
  9. Agent集成：register_capability + collaborate
  10. 消息总线统计

第一性原理验证：
  - 多个agent通过共享MessageBus能互相发现
  - 任务能按能力匹配分派到最佳邻居
  - 任务结果能回传给分派方
  - 共识提案能通过2PC达成一致
"""

import sys
import os
import time
import tempfile
import shutil
from pathlib import Path

# 确保能导入模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.multi_agent_collaborator import MultiAgentCollaborator
from communication import (
    AgentMessage, MessageType, MessageBus,
    AgentDiscovery, TaskDispatcher, TaskStatus,
    ConsensusEngine, ConsensusState,
)
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

def test_collaborator_basic():
    """测试1: MultiAgentCollaborator 基本功能"""
    print("\n--- 测试1: Collaborator 基本功能 ---")
    collab = MultiAgentCollaborator(agent_id="agent_a")

    assert_eq(collab.agent_id, "agent_a", "agent_id正确")
    assert_eq(len(collab.get_capabilities()), 0, "初始无能力")

    # 注册能力
    collab.register_capability("compute", lambda p: p.get("x", 0) + p.get("y", 0))
    assert_eq(len(collab.get_capabilities()), 1, "注册1个能力")
    assert_true("compute" in collab.get_capabilities(), "能力包含compute")

    # 状态
    status = collab.get_status()
    assert_eq(status["agent_id"], "agent_a", "状态agent_id正确")
    assert_eq(status["capabilities"], ["compute"], "状态capabilities正确")


def test_heartbeat_and_discovery():
    """测试2: 心跳广播与邻居发现"""
    print("\n--- 测试2: 心跳广播与邻居发现 ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
    collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)

    # A广播心跳
    collab_a.broadcast_heartbeat(load_score=0.3, metadata={"role": "worker"})

    # B处理消息
    collab_b.process_messages()

    # B应发现A
    neighbors = collab_b.discovery.get_neighbors()
    assert_true(len(neighbors) == 1, "B发现1个邻居")
    assert_eq(neighbors[0].agent_id, "agent_a", "邻居是agent_a")
    assert_eq(neighbors[0].load_score, 0.3, "负载=0.3")

    # A不应发现自己
    collab_a.process_messages()
    a_neighbors = collab_a.discovery.get_neighbors()
    assert_eq(len(a_neighbors), 0, "A不发现自己")


def test_task_dispatch_and_execute():
    """测试3: 任务分派与执行"""
    print("\n--- 测试3: 任务分派与执行 ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
    collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)

    # B注册能力
    results_received = []
    def compute_handler(payload):
        return payload.get("x", 0) * payload.get("y", 0)
    collab_b.register_capability("compute", compute_handler)

    # 先让B广播心跳，A发现B
    collab_b.broadcast_heartbeat(load_score=0.2)
    collab_a.process_messages()
    assert_eq(len(collab_a.discovery.get_neighbors()), 1, "A发现B")

    # A分派任务给B
    task_id, msg = collab_a.dispatch_task(
        task_type="compute",
        payload={"x": 6, "y": 7},
        required_capability="compute",
    )
    assert_true(msg is not None, "分派消息非None")
    assert_eq(msg.target_id, "agent_b", "目标是agent_b")

    # B处理任务消息
    collab_b.process_messages()

    # A处理结果消息
    collab_a.process_messages()

    # 检查任务状态
    task = collab_a.dispatcher.get_task(task_id)
    assert_true(task is not None, "任务记录存在")
    assert_eq(task.status, TaskStatus.COMPLETED, "任务已完成")

    # 检查统计
    assert_eq(collab_a._total_tasks_dispatched, 1, "A分派了1个任务")
    assert_eq(collab_b._total_tasks_received, 1, "B接收了1个任务")
    assert_eq(collab_b._total_tasks_completed, 0, "B完成数（结果回传后才算A的completed）")


def test_task_result_callback():
    """测试4: 任务结果回调"""
    print("\n--- 测试4: 任务结果回调 ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
    collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)

    collab_b.register_capability("greet", lambda p: f"Hello {p.get('name','')}!")

    # B广播心跳
    collab_b.broadcast_heartbeat(load_score=0.1)
    collab_a.process_messages()

    # A分派任务，带回调
    callback_results = []
    def on_result(result_dict):
        callback_results.append(result_dict)

    task_id, msg = collab_a.dispatch_task(
        task_type="greet",
        payload={"name": "World"},
        on_result=on_result,
    )

    # B处理任务
    collab_b.process_messages()

    # A处理结果
    collab_a.process_messages()

    # 回调应被触发
    assert_true(len(callback_results) == 1, "回调被触发1次")
    assert_true(callback_results[0]["success"], "回调结果success=True")
    assert_eq(callback_results[0]["result"], "Hello World!", "结果正确")


def test_no_candidate_dispatch():
    """测试5: 无可用邻居时分派失败"""
    print("\n--- 测试5: 无可用邻居时分派失败 ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)

    # 无邻居，分派应失败
    task_id, msg = collab_a.dispatch_task(
        task_type="compute",
        payload={"x": 1},
    )
    assert_true(msg is None, "无邻居时分派消息为None")
    task = collab_a.dispatcher.get_task(task_id)
    assert_true(task is not None, "任务记录仍创建")
    assert_eq(task.status, TaskStatus.PENDING, "状态仍为PENDING")


def test_capability_filtering():
    """测试6: 能力过滤（所需能力不匹配时分派失败）"""
    print("\n--- 测试6: 能力过滤 ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
    collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)

    # B只注册compute能力
    collab_b.register_capability("compute", lambda p: 0)

    # B广播心跳
    collab_b.broadcast_heartbeat(load_score=0.1)
    collab_a.process_messages()

    # A分派需要"translate"能力的任务，应失败
    task_id, msg = collab_a.dispatch_task(
        task_type="translate",
        payload={"text": "hello"},
        required_capability="translate",
    )
    assert_true(msg is None, "能力不匹配时分派失败")

    # A分派需要"compute"能力的任务，应成功
    task_id2, msg2 = collab_a.dispatch_task(
        task_type="compute",
        payload={"x": 1},
        required_capability="compute",
    )
    assert_true(msg2 is not None, "能力匹配时分派成功")


def test_load_based_selection():
    """测试7: 按负载选择最佳邻居"""
    print("\n--- 测试7: 按负载选择最佳邻居 ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
    collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)
    collab_c = MultiAgentCollaborator(agent_id="agent_c", message_bus=bus)

    # B和C都注册compute能力
    collab_b.register_capability("compute", lambda p: "from_b")
    collab_c.register_capability("compute", lambda p: "from_c")

    # B负载高，C负载低
    collab_b.broadcast_heartbeat(load_score=0.9)
    collab_c.broadcast_heartbeat(load_score=0.1)
    collab_a.process_messages()

    # A分派任务，应选C（负载低）
    task_id, msg = collab_a.dispatch_task(
        task_type="compute",
        payload={},
        required_capability="compute",
    )
    assert_eq(msg.target_id, "agent_c", "选择负载低的agent_c")


def test_consensus_proposal():
    """测试8: 共识提案（2PC）"""
    print("\n--- 测试8: 共识提案 ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
    collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)
    collab_c = MultiAgentCollaborator(agent_id="agent_c", message_bus=bus)

    committed = []
    def on_commit(value):
        committed.append(value)

    # A发起提案
    collab_a.propose_consensus(
        proposal_id="prop_1",
        value={"action": "scale_up", "factor": 2},
        participant_ids=["agent_b", "agent_c"],
        on_commit=on_commit,
    )

    # B和C处理prepare消息，回复投票
    collab_b.process_messages()
    collab_c.process_messages()

    # A处理投票
    collab_a.process_messages()

    # 检查提案状态
    prop = collab_a.consensus.get_proposal("prop_1")
    assert_true(prop is not None, "提案存在")
    # 应已commit（2个参与者都投赞成）
    assert_eq(prop.state, ConsensusState.COMMITTED, "提案已COMMITTED")
    assert_true(len(committed) == 1, "commit回调被触发")
    assert_eq(committed[0]["action"], "scale_up", "commit值正确")


def test_multi_agent_collaboration_scenario():
    """测试9: 多agent协作场景（3个agent互相分派）"""
    print("\n--- 测试9: 多agent协作场景 ---")
    bus = MessageBus()
    agents = {}
    for name in ["alpha", "beta", "gamma"]:
        c = MultiAgentCollaborator(agent_id=name, message_bus=bus)
        agents[name] = c

    # 各agent注册不同能力
    agents["alpha"].register_capability("analyze", lambda p: {"analysis": p.get("data", "")})
    agents["beta"].register_capability("transform", lambda p: {"transformed": p.get("input", "")})
    agents["gamma"].register_capability("report", lambda p: {"report": p.get("result", "")})

    # 全员广播心跳
    for c in agents.values():
        c.broadcast_heartbeat(load_score=0.2)
    # 全员处理消息
    for c in agents.values():
        c.process_messages()

    # 每个agent应发现另外2个
    for name, c in agents.items():
        neighbors = c.discovery.get_neighbors()
        assert_eq(len(neighbors), 2, f"{name}发现2个邻居")

    # alpha分派transform任务给beta
    task_id, msg = agents["alpha"].dispatch_task(
        task_type="transform",
        payload={"input": "raw_data"},
        required_capability="transform",
    )
    assert_eq(msg.target_id, "beta", "transform任务分派给beta")

    # beta处理
    agents["beta"].process_messages()
    # alpha处理结果
    agents["alpha"].process_messages()

    task = agents["alpha"].dispatcher.get_task(task_id)
    assert_eq(task.status, TaskStatus.COMPLETED, "transform任务完成")


def test_agent_integration_register_and_collaborate():
    """测试10: Agent集成 - register_capability + collaborate"""
    print("\n--- 测试10: Agent集成 ---")
    tmp_skills = tempfile.mkdtemp(prefix="agent_skills_")
    try:
        config_a = AgentConfig()
        config_a.agent_name = "AgentA"
        config_a.execution_dry_run = True
        config_b = AgentConfig()
        config_b.agent_name = "AgentB"
        config_b.execution_dry_run = True
        agent_a = SelfEvolvingAgent(config=config_a)
        agent_b = SelfEvolvingAgent(config=config_b)

        # 让B共享A的消息总线
        agent_b.collaborator.message_bus = agent_a.collaborator.message_bus
        # 重新订阅（因为换了bus）
        agent_b.collaborator._subscribe_to_bus()

        # B注册能力
        agent_b.register_capability("compute_sum", lambda p: p.get("a", 0) + p.get("b", 0))

        # B广播心跳
        agent_b.collaborator.broadcast_heartbeat(load_score=0.1)
        agent_a.collaborator.process_messages()

        # A分派任务给B
        task_id, msg = agent_a.collaborate(
            task_type="compute_sum",
            payload={"a": 10, "b": 20},
            required_capability="compute_sum",
        )
        assert_true(msg is not None, "分派消息非None")
        assert_eq(msg.target_id, "AgentB", "目标是AgentB")

        # B处理
        agent_b.collaborator.process_messages()
        # A处理结果
        agent_a.collaborator.process_messages()

        task = agent_a.collaborator.dispatcher.get_task(task_id)
        assert_eq(task.status, TaskStatus.COMPLETED, "任务完成")

        # 状态查询
        status = agent_a.get_collaboration_status()
        assert_true("neighbors" in status, "状态包含neighbors")
        assert_true("tasks" in status, "状态包含tasks")
    finally:
        shutil.rmtree(tmp_skills, ignore_errors=True)


def test_agent_get_status_includes_collaboration():
    """测试11: Agent.get_status 包含 collaboration_status"""
    print("\n--- 测试11: get_status包含collaboration_status ---")
    config = AgentConfig()
    config.execution_dry_run = True
    agent = SelfEvolvingAgent(config=config)

    status = agent.get_status()
    assert_true("collaboration_status" in status, "包含collaboration_status")
    assert_true("agent_id" in status["collaboration_status"], "包含agent_id")
    assert_true("capabilities" in status["collaboration_status"], "包含capabilities")


def test_message_bus_stats():
    """测试12: 消息总线统计"""
    print("\n--- 测试12: 消息总线统计 ---")
    bus = MessageBus()
    collab = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)

    # 发布几条心跳
    collab.broadcast_heartbeat(load_score=0.5)
    collab.process_messages()

    stats = collab.get_status()
    assert_true("message_bus" in stats, "状态包含message_bus")
    assert_true("heartbeats_sent" in stats, "包含heartbeats_sent")
    assert_true(stats["heartbeats_sent"] >= 1, "至少发送1次心跳")


def test_stale_neighbor_pruning():
    """测试13: 超时邻居剔除"""
    print("\n--- 测试13: 超时邻居剔除 ---")
    bus = MessageBus()
    # 设置短超时
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
    collab_a.discovery.stale_timeout = 0.5  # 0.5秒超时

    collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)
    collab_b.broadcast_heartbeat(load_score=0.1)
    collab_a.process_messages()
    assert_eq(len(collab_a.discovery.get_neighbors()), 1, "发现B")

    # 等待超时
    time.sleep(0.6)
    collab_a.process_messages()  # 会触发prune_stale
    assert_eq(len(collab_a.discovery.get_neighbors()), 0, "B超时被剔除")


def test_task_timeout_retry():
    """测试14: 任务超时重分派"""
    print("\n--- 测试14: 任务超时重分派 ---")
    bus = MessageBus()
    collab_a = MultiAgentCollaborator(agent_id="agent_a", message_bus=bus)
    collab_a.dispatcher.assign_timeout = 0.3  # 短超时

    collab_b = MultiAgentCollaborator(agent_id="agent_b", message_bus=bus)
    collab_b.register_capability("slow", lambda p: "result")
    collab_b.broadcast_heartbeat(load_score=0.1)
    collab_a.process_messages()

    # A分派任务
    task_id, msg = collab_a.dispatch_task(
        task_type="slow",
        payload={},
        required_capability="slow",
    )
    # 不让B处理，模拟超时

    # 等待超时
    time.sleep(0.4)
    # A检查超时
    retry_ids = collab_a.dispatcher.check_timeouts()
    assert_true(task_id in retry_ids, "任务超时进入重分派列表")


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
    print("阶段3测试：多agent协作框架")
    print("=" * 70)

    tests = [
        test_collaborator_basic,
        test_heartbeat_and_discovery,
        test_task_dispatch_and_execute,
        test_task_result_callback,
        test_no_candidate_dispatch,
        test_capability_filtering,
        test_load_based_selection,
        test_consensus_proposal,
        test_multi_agent_collaboration_scenario,
        test_agent_integration_register_and_collaborate,
        test_agent_get_status_includes_collaboration,
        test_message_bus_stats,
        test_stale_neighbor_pruning,
        test_task_timeout_retry,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            global failed
            failed += 1
            import traceback
            print(f"  [ERROR] {test.__name__} 异常: {e}")
            traceback.print_exc()

    _cleanup_persistent_state()

    print("\n" + "=" * 70)
    print(f"测试结果: {passed} 通过, {failed} 失败, 共 {passed + failed} 项断言")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
