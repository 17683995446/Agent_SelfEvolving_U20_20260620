"""
阶段7测试：综合验证与长任务实战 — 端到端集成

测试覆盖（5个实战场景，验证6个新阶段的全链路集成）：
  场景1: 端到端长任务实战 — 设定目标→习得技能→自驱执行→技能进化
  场景2: 多agent协作长任务 — Leader组队→分派子任务→Workers执行→结果汇总
  场景3: 自组织群体智能 — 多agent自组织→选举leader→共识决策→协作执行
  场景4: 技能进化闭环实战 — 使用→评估→优化→验证→部署→回滚
  场景5: 断点续传实战 — 长任务中断→重启→恢复→完成

第一性原理验证：
  - Agent能自主设定长任务目标并分解执行（阶段1+4）
  - Agent能从需求习得技能并应用于任务（阶段2）
  - 多agent能协作完成超出单agent能力的任务（阶段3+6）
  - 技能能通过使用反馈自动进化（阶段5）
  - 长任务支持断点续传，中断后可恢复（阶段4）
  - 全链路：目标→技能→协作→自组织→执行→进化→续传
"""

import sys
import os
import time
import tempfile
import shutil

# 确保能导入模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.skill_library import SkillLibrary
from core.multi_agent_collaborator import MultiAgentCollaborator
from core.long_task_orchestrator import LongTaskOrchestrator, TaskStatus, StepStatus
from core.skill_evolution import SkillEvolutionEngine
from core.self_organization import SelfOrganizationEngine, AgentRole
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
# 场景1: 端到端长任务实战 — 设定目标→习得技能→自驱执行→技能进化
# ============================================================================

def test_scenario1_end_to_end_long_task():
    """场景1: 端到端长任务实战"""
    print("\n=== 场景1: 端到端长任务实战 ===")
    print("  目标: Agent习得计算技能→启动长任务→自驱执行→技能进化")

    tmp_dir = tempfile.mkdtemp(prefix="phase7_s1_")
    try:
        # --- 步骤1: 创建Agent并习得技能 ---
        config = AgentConfig()
        config.agent_name = "agent_e2e"
        agent = SelfEvolvingAgent(config=config)

        # 习得一个计算技能
        learn_result = agent.learn_skill("compute the sum of two numbers")
        assert_eq(learn_result["success"], True, "习得compute技能成功")
        skill_name = learn_result["skill_name"]
        print(f"  习得技能: {skill_name}")

        # 验证技能可用（compute模板: execute(x=0, y=0) → x+y）
        use_result = agent.use_skill(skill_name, x=10, y=5)
        assert_eq(use_result["success"], True, "技能调用成功")
        assert_eq(use_result["result"], 15, "计算结果=15")

        # --- 步骤2: 启动长任务（用习得的技能执行步骤） ---
        phases = [
            # 阶段0: 数据准备
            [
                {"description": "计算第一批数据", "skill_name": skill_name,
                 "skill_kwargs": {"x": 10, "y": 20}},
                {"description": "计算第二批数据", "skill_name": skill_name,
                 "skill_kwargs": {"x": 30, "y": 40}},
            ],
            # 阶段1: 汇总
            [
                {"description": "计算汇总数据", "skill_name": skill_name,
                 "skill_kwargs": {"x": 50, "y": 60}},
            ],
        ]
        task_id = agent.start_long_task(
            description="端到端数据计算长任务",
            phases=phases,
        )
        assert_true(task_id.startswith("longtask_"), "任务ID格式正确")
        print(f"  启动长任务: {task_id}")

        # --- 步骤3: 自驱执行直到完成 ---
        progress = agent.run_long_task(max_steps=50)
        assert_eq(progress["status"], "completed", "长任务完成")
        assert_eq(progress["progress"], 1.0, "进度=100%")
        assert_eq(progress["completed_steps"], 3, "完成3步")
        print(f"  长任务完成: progress={progress['progress']:.0%}")

        # --- 步骤4: 技能进化（多次使用后评估） ---
        # 多次调用技能以积累统计数据
        for _ in range(5):
            agent.use_skill(skill_name, x=1, y=2)

        eval_result = agent.evaluate_skill(skill_name)
        assert_true(eval_result is not None, "技能评估有结果")
        assert_true(eval_result["invoke_count"] >= 6, "调用次数>=6")
        assert_eq(eval_result["success_rate"], 1.0, "成功率=1.0")
        print(f"  技能评估: score={eval_result['score']:.2f} verdict={eval_result['verdict']}")

        # --- 步骤5: 验证Agent状态包含所有阶段信息 ---
        status = agent.get_status()
        assert_true("goal_status" in status, "状态含goal_status(阶段1)")
        assert_true("skill_stats" in status, "状态含skill_stats(阶段2)")
        assert_true("collaboration_status" in status, "状态含collaboration_status(阶段3)")
        assert_true("long_task_status" in status, "状态含long_task_status(阶段4)")
        assert_true("skill_evolution_status" in status, "状态含skill_evolution_status(阶段5)")
        assert_true("organization_status" in status, "状态含organization_status(阶段6)")
        print("  全链路状态验证通过")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================================
# 场景2: 多agent协作长任务 — Leader组队→分派→Workers执行→汇总
# ============================================================================

def test_scenario2_multi_agent_collaboration():
    """场景2: 多agent协作长任务"""
    print("\n=== 场景2: 多agent协作长任务 ===")
    print("  目标: Leader组队→分派子任务→Workers执行→结果汇总")

    tmp_dir = tempfile.mkdtemp(prefix="phase7_s2_")
    bus = MessageBus()
    try:
        # --- 步骤1: 创建3个agent，共享消息总线 ---
        config_leader = AgentConfig()
        config_leader.agent_name = "leader_agent"
        leader = SelfEvolvingAgent(config=config_leader)

        config_w1 = AgentConfig()
        config_w1.agent_name = "worker_1"
        worker1 = SelfEvolvingAgent(config=config_w1)

        config_w2 = AgentConfig()
        config_w2.agent_name = "worker_2"
        worker2 = SelfEvolvingAgent(config=config_w2)

        # 共享同一消息总线（替换各自独立的bus）
        leader.collaborator.message_bus = bus
        worker1.collaborator.message_bus = bus
        worker2.collaborator.message_bus = bus
        # 重新订阅
        leader.collaborator._subscribe_to_bus()
        worker1.collaborator._subscribe_to_bus()
        worker2.collaborator._subscribe_to_bus()

        # --- 步骤2: Workers注册能力 ---
        worker1.register_capability("compute", lambda p: sum(p.get("data", [])))
        worker2.register_capability("compute", lambda p: max(p.get("data", [])))

        # --- 步骤3: Leader组队 ---
        # 先让workers广播心跳
        worker1.collaborator.broadcast_heartbeat(load_score=0.2)
        worker2.collaborator.broadcast_heartbeat(load_score=0.3)
        leader.collaborator.process_messages()

        team_result = leader.form_team(
            task_description="分布式计算任务",
            required_capabilities=["compute"],
            team_members=["worker_1", "worker_2"],
        )
        assert_eq(team_result["leader_id"], "leader_agent", "Leader是自己")
        assert_eq(len(team_result["members"]), 2, "2个worker成员")
        print(f"  组队完成: {team_result['team_id']}")

        # --- 步骤4: Leader分派任务给workers ---
        task_id1, msg1 = leader.collaborate(
            task_type="compute",
            payload={"data": [1, 2, 3, 4, 5]},
            required_capability="compute",
        )
        assert_true(msg1 is not None, "任务1分派成功")

        task_id2, msg2 = leader.collaborate(
            task_type="compute",
            payload={"data": [10, 20, 30]},
            required_capability="compute",
        )
        assert_true(msg2 is not None, "任务2分派成功")
        print(f"  分派2个任务: {task_id1}, {task_id2}")

        # --- 步骤5: Workers处理任务 ---
        worker1.collaborator.process_messages()
        worker2.collaborator.process_messages()

        # 验证workers收到了任务
        assert_true(worker1.collaborator._total_tasks_received >= 1 or
                    worker2.collaborator._total_tasks_received >= 1,
                    "至少1个worker收到任务")
        print("  Workers处理任务完成")

        # --- 步骤6: Leader成为leader角色 ---
        org_status = leader.get_organization_status()
        assert_eq(org_status["role"], "leader", "Leader角色=leader")
        assert_eq(org_status["has_team"], True, "Leader有团队")
        print("  Leader角色验证通过")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================================
# 场景3: 自组织群体智能 — 选举+共识+协作
# ============================================================================

def test_scenario3_self_organizing_swarm():
    """场景3: 自组织群体智能"""
    print("\n=== 场景3: 自组织群体智能 ===")
    print("  目标: 多agent自组织→选举leader→共识决策→协作执行")

    bus = MessageBus()
    # 创建3个协作器
    collab_a = MultiAgentCollaborator(agent_id="node_a", message_bus=bus)
    collab_b = MultiAgentCollaborator(agent_id="node_b", message_bus=bus)
    collab_c = MultiAgentCollaborator(agent_id="node_c", message_bus=bus)

    engine_a = SelfOrganizationEngine(collaborator=collab_a)
    engine_b = SelfOrganizationEngine(collaborator=collab_b)
    engine_c = SelfOrganizationEngine(collaborator=collab_c)

    # --- 步骤1: A自荐为leader并组队 ---
    engine_a.assign_role(AgentRole.LEADER, reason="bootstrap")
    team = engine_a.form_team(
        task_description="群体协作任务",
        required_capabilities=["compute"],
        team_members=["node_b", "node_c"],
    )
    assert_eq(len(team.members), 2, "团队2成员")
    print(f"  A组队: {team.team_id}")

    # --- 步骤2: A广播leader心跳，B和C发现 ---
    engine_a.run_organization_cycle()
    engine_b.run_organization_cycle()
    engine_c.run_organization_cycle()

    assert_eq(engine_b.get_status()["known_leader"], "node_a", "B知道leader=A")
    assert_eq(engine_c.get_status()["known_leader"], "node_a", "C知道leader=A")
    assert_eq(engine_b.get_role(), AgentRole.FOLLOWER, "B是follower")
    assert_eq(engine_c.get_role(), AgentRole.FOLLOWER, "C是follower")
    print("  B和C发现leader=A")

    # --- 步骤3: A发起共识决策 ---
    decision_result = engine_a.propose_decision(
        decision_id="plan_1",
        proposal={"action": "execute_phase_1", "deadline": "1h"},
        participant_ids=["node_b", "node_c"],
    )
    assert_eq(decision_result["status"], "proposed", "决策已发起")
    print(f"  A发起决策: {decision_result['decision_id']}")

    # --- 步骤4: B和C投票 ---
    vote_b = engine_b.vote("plan_1", True)
    vote_c = engine_c.vote("plan_1", True)
    assert_eq(vote_b["status"], "voted", "B投票完成")
    assert_eq(vote_c["status"], "voted", "C投票完成")
    print("  B和C投票赞成")

    # --- 步骤5: 验证角色历史和统计 ---
    status_a = engine_a.get_status()
    assert_eq(status_a["role"], "leader", "A是leader")
    assert_eq(status_a["total_teams_formed"], 1, "A组队1次")
    assert_true(status_a["total_role_changes"] >= 1, "A至少1次角色变更")

    # B和C的角色历史
    status_b = engine_b.get_status()
    assert_eq(status_b["known_leader"], "node_a", "B的leader=A")
    print("  群体自组织验证通过")


# ============================================================================
# 场景4: 技能进化闭环实战 — 使用→评估→优化→验证→部署→回滚
# ============================================================================

def test_scenario4_skill_evolution_loop():
    """场景4: 技能进化闭环实战"""
    print("\n=== 场景4: 技能进化闭环实战 ===")
    print("  目标: 使用技能→评估→优化→验证→部署→回滚退化版本")

    tmp_dir = tempfile.mkdtemp(prefix="phase7_s4_")
    try:
        lib = SkillLibrary(skills_dir=tmp_dir)
        engine = SkillEvolutionEngine(skill_library=lib)

        # --- 步骤1: 注册一个性能一般的技能 ---
        lib.register(
            name="slow_compute",
            description="慢速计算",
            code='def execute(**kwargs):\n'
                  '    import time\n'
                  '    time.sleep(0.01)\n'
                  '    return sum(kwargs.get("data", []))\n',
        )
        print("  注册slow_compute技能")

        # --- 步骤2: 多次使用积累数据 ---
        for _ in range(8):
            lib.invoke("slow_compute", data=[1, 2, 3])

        # --- 步骤3: 评估技能 ---
        eval1 = engine.evaluate("slow_compute")
        assert_true(eval1 is not None, "评估有结果")
        assert_eq(eval1.success_rate, 1.0, "成功率=1.0")
        assert_true(eval1.invoke_count >= 8, "调用>=8次")
        print(f"  评估v{eval1.version}: score={eval1.score:.2f} verdict={eval1.verdict}")

        # --- 步骤4: 运行进化周期（可能触发优化） ---
        cycle_result = engine.run_evolution_cycle()
        assert_true("evaluated" in cycle_result, "进化周期返回evaluated")
        assert_true(cycle_result["evaluated"] >= 1, "至少评估1个技能")
        print(f"  进化周期: evaluated={cycle_result['evaluated']} "
              f"optimized={cycle_result.get('optimized', 0)}")

        # --- 步骤5: 验证进化历史 ---
        history = engine.get_evolution_history()
        assert_true(len(history) >= 1, "进化历史>=1条")
        print(f"  进化历史: {len(history)}条")

        # --- 步骤6: 注册一个会失败的技能，验证评估能识别问题 ---
        lib.register(
            name="flaky_skill",
            description="不稳定技能",
            code='def execute(**kwargs):\n'
                  '    if kwargs.get("fail", False):\n'
                  '        raise RuntimeError("intentional failure")\n'
                  '    return "ok"\n',
        )
        # 调用：1次成功，4次失败（成功率0.2 < 0.5，触发"成功率低"问题）
        lib.invoke("flaky_skill")
        lib.invoke("flaky_skill", fail=True)
        lib.invoke("flaky_skill", fail=True)
        lib.invoke("flaky_skill", fail=True)
        lib.invoke("flaky_skill", fail=True)

        eval_flaky = engine.evaluate("flaky_skill")
        assert_true(eval_flaky is not None, "flaky评估有结果")
        assert_true(eval_flaky.success_rate < 0.5, "flaky成功率<0.5")
        assert_true("成功率低" in eval_flaky.issues or
                    eval_flaky.verdict in ("needs_improvement", "poor"),
                    "flaky识别为需改进")
        print(f"  flaky评估: success_rate={eval_flaky.success_rate:.2f} "
              f"verdict={eval_flaky.verdict} issues={eval_flaky.issues}")

        # --- 步骤7: 验证引擎状态 ---
        status = engine.get_status()
        assert_true(status["total_evaluations"] >= 2, "至少2次评估")
        print("  技能进化闭环验证通过")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================================
# 场景5: 断点续传实战 — 长任务中断→重启→恢复→完成
# ============================================================================

def test_scenario5_checkpoint_resume():
    """场景5: 断点续传实战"""
    print("\n=== 场景5: 断点续传实战 ===")
    print("  目标: 长任务执行部分步骤→保存断点→新实例恢复→完成剩余步骤")

    tmp_dir = tempfile.mkdtemp(prefix="phase7_s5_")
    ckpt_dir = os.path.join(tmp_dir, "checkpoints")
    skills_dir = os.path.join(tmp_dir, "skills")
    os.makedirs(skills_dir, exist_ok=True)

    try:
        # --- 步骤1: 创建技能库和编排器 ---
        lib = SkillLibrary(skills_dir=skills_dir)
        lib.register(
            name="add_one",
            description="加1",
            code='def execute(**kwargs):\n'
                  '    return kwargs.get("x", 0) + 1\n',
        )

        orchestrator1 = LongTaskOrchestrator(
            agent_id="agent_ckpt",
            skill_library=lib,
            checkpoint_dir=ckpt_dir,
        )

        # --- 步骤2: 启动4步长任务 ---
        phases = [
            [
                {"description": "步骤1", "skill_name": "add_one", "skill_kwargs": {"x": 1}},
                {"description": "步骤2", "skill_name": "add_one", "skill_kwargs": {"x": 2}},
            ],
            [
                {"description": "步骤3", "skill_name": "add_one", "skill_kwargs": {"x": 3}},
                {"description": "步骤4", "skill_name": "add_one", "skill_kwargs": {"x": 4}},
            ],
        ]
        task_id = orchestrator1.start_task(description="断点续传测试", phases=phases)
        print(f"  启动长任务: {task_id}")

        # --- 步骤3: 执行2步后保存断点 ---
        r1 = orchestrator1.execute_next()
        assert_eq(r1["status"], "step_completed", "步骤1执行成功")
        r2 = orchestrator1.execute_next()
        assert_eq(r2["status"], "step_completed", "步骤2执行成功")

        progress_before = orchestrator1.get_progress()
        assert_eq(progress_before["completed_steps"], 2, "完成2步")
        assert_eq(progress_before["current_phase"], 1, "进入阶段1")
        print(f"  执行2步后: progress={progress_before['progress']:.0%}")

        # 保存断点
        orchestrator1.checkpoint()
        assert_true(os.path.exists(ckpt_dir), "断点目录存在")
        ckpt_files = [f for f in os.listdir(ckpt_dir) if f.endswith(".json")]
        assert_true(len(ckpt_files) >= 1, "断点文件已生成")
        print(f"  断点已保存: {len(ckpt_files)}个文件")

        # --- 步骤4: 模拟重启——创建新编排器，从断点恢复 ---
        orchestrator2 = LongTaskOrchestrator(
            agent_id="agent_ckpt",
            skill_library=lib,
            checkpoint_dir=ckpt_dir,
        )
        resumed = orchestrator2.resume(task_id)
        assert_eq(resumed, True, "断点恢复成功")
        print("  新实例从断点恢复")

        # --- 步骤5: 验证恢复后的状态 ---
        progress_resumed = orchestrator2.get_progress()
        assert_eq(progress_resumed["completed_steps"], 2, "恢复后完成2步")
        assert_eq(progress_resumed["current_phase"], 1, "恢复后在阶段1")
        assert_eq(progress_resumed["status"], "running", "恢复后状态=running")
        print(f"  恢复状态: progress={progress_resumed['progress']:.0%}")

        # --- 步骤6: 继续执行剩余步骤 ---
        r3 = orchestrator2.execute_next()
        assert_eq(r3["status"], "step_completed", "步骤3执行成功")
        r4 = orchestrator2.execute_next()
        assert_eq(r4["status"], "step_completed", "步骤4执行成功")

        # --- 步骤7: 验证任务完成 ---
        progress_final = orchestrator2.get_progress()
        assert_eq(progress_final["status"], "completed", "任务完成")
        assert_eq(progress_final["progress"], 1.0, "进度=100%")
        assert_eq(progress_final["completed_steps"], 4, "完成4步")
        print(f"  任务完成: progress={progress_final['progress']:.0%}")

        # --- 步骤8: 再次execute_next应返回task_completed ---
        r5 = orchestrator2.execute_next()
        assert_eq(r5["status"], "task_completed", "完成后返回task_completed")
        print("  断点续传实战验证通过")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================================
# 场景6: 全链路Agent实战 — 目标驱动+技能+协作+自组织+进化
# ============================================================================

def test_scenario6_full_agent_lifecycle():
    """场景6: 全链路Agent生命周期"""
    print("\n=== 场景6: 全链路Agent生命周期 ===")
    print("  目标: Agent设定目标→习得技能→组队→执行长任务→进化技能")

    config = AgentConfig()
    config.agent_name = "agent_full"
    agent = SelfEvolvingAgent(config=config)

    # --- 步骤1: 习得多个技能（显式指定不同技能名，避免同名覆盖） ---
    r1 = agent.learn_skill("compute the sum of numbers", skill_name="sum_skill")
    assert_eq(r1["success"], True, "习得sum技能")
    r2 = agent.learn_skill("compute the maximum of numbers", skill_name="max_skill")
    assert_eq(r2["success"], True, "习得max技能")
    print(f"  习得技能: {r1['skill_name']}, {r2['skill_name']}")

    # --- 步骤2: 设定长任务目标（阶段1目标驱动） ---
    goal_id = agent.set_long_task(
        description="数据处理目标",
        sub_tasks=["采集数据", "计算汇总", "优化资源"],
        priority=0.9,
        deadline_hours=2.0,
        steps_per_subgoal=3,
    )
    assert_true(goal_id.startswith("goal_"), "目标ID格式正确")
    goal_status = agent.get_goal_status()
    assert_true(goal_status["has_active_goal"], "有活跃目标")
    print(f"  设定目标: {goal_id}")

    # --- 步骤3: 组队（阶段6自组织） ---
    team_result = agent.form_team(
        task_description="全链路任务",
        required_capabilities=["compute"],
        team_members=["helper_1", "helper_2"],
    )
    assert_eq(team_result["leader_id"], "agent_full", "自己是leader")
    print(f"  组队: {team_result['team_id']}")

    # --- 步骤4: 启动并执行长任务（阶段4） ---
    phases = [
        [
            {"description": "求和", "skill_name": r1["skill_name"],
             "skill_kwargs": {"x": 10, "y": 20}},
            {"description": "求最大值", "skill_name": r2["skill_name"],
             "skill_kwargs": {"x": 30, "y": 40}},
        ],
    ]
    task_id = agent.start_long_task(description="全链路长任务", phases=phases)
    progress = agent.run_long_task(max_steps=20)
    assert_eq(progress["status"], "completed", "长任务完成")
    print(f"  长任务完成: {progress['progress']:.0%}")

    # --- 步骤5: 技能进化（阶段5） ---
    for _ in range(5):
        agent.use_skill(r1["skill_name"], x=1, y=2)
    eval_result = agent.evaluate_skill(r1["skill_name"])
    assert_true(eval_result is not None, "技能评估有结果")
    assert_eq(eval_result["success_rate"], 1.0, "成功率=1.0")
    print(f"  技能进化: score={eval_result['score']:.2f}")

    # --- 步骤6: 运行自组织周期（阶段6） ---
    org_result = agent.run_organization_cycle()
    assert_eq(org_result["role"], "leader", "角色=leader")
    print(f"  自组织周期: role={org_result['role']}")

    # --- 步骤7: 完整状态验证 ---
    status = agent.get_status()
    assert_true(status["organization_status"]["role"] == "leader", "组织状态leader")
    assert_true(status["skill_stats"]["total_skills"] >= 2, "至少2个技能")
    assert_true(status["long_task_status"]["tasks_completed"] >= 1, "至少完成1个长任务")
    print("  全链路生命周期验证通过")


# ============================================================================
# 场景7: 长任务失败恢复与降级
# ============================================================================

def test_scenario7_failure_recovery_degradation():
    """场景7: 长任务失败恢复与降级"""
    print("\n=== 场景7: 长任务失败恢复与降级 ===")
    print("  目标: 长任务含失败步骤→重试→降级跳过→继续推进→完成")

    tmp_dir = tempfile.mkdtemp(prefix="phase7_s7_")
    skills_dir = os.path.join(tmp_dir, "skills")
    os.makedirs(skills_dir, exist_ok=True)

    try:
        lib = SkillLibrary(skills_dir=skills_dir)
        # 注册一个正常技能
        lib.register(
            name="ok_skill",
            description="正常技能",
            code='def execute(**kwargs):\n    return "ok"\n',
        )
        # 注册一个总是失败的技能
        lib.register(
            name="bad_skill",
            description="失败技能",
            code='def execute(**kwargs):\n    raise RuntimeError("always fails")\n',
            auto_validate=False,  # 跳过验证（因为会失败）
        )

        orchestrator = LongTaskOrchestrator(
            agent_id="agent_fail",
            skill_library=lib,
            checkpoint_dir=os.path.join(tmp_dir, "ckpt"),
        )

        # 启动含失败步骤的长任务
        phases = [
            [
                {"description": "正常步骤1", "skill_name": "ok_skill"},
                {"description": "失败步骤", "skill_name": "bad_skill", "max_retries": 1},
                {"description": "正常步骤2", "skill_name": "ok_skill"},
            ],
        ]
        orchestrator.start_task(description="失败恢复测试", phases=phases)

        # 执行所有步骤
        results = []
        for _ in range(10):
            r = orchestrator.execute_next()
            results.append(r)
            if r["status"] in ("task_completed", "no_task", "not_running"):
                break

        # 验证：任务应完成（失败步骤被降级跳过）
        progress = orchestrator.get_progress()
        assert_eq(progress["status"], "completed", "任务完成（含降级）")
        assert_eq(progress["progress"], 1.0, "进度=100%")
        assert_eq(progress["completed_steps"], 3, "3步都计入（含跳过）")
        print(f"  任务完成: progress={progress['progress']:.0%} (含降级跳过)")

        # 验证有步骤被跳过
        task_dict = orchestrator._current_task.to_dict()
        skipped = [s for phase in task_dict["phases"] for s in phase
                   if s["status"] == "skipped"]
        assert_true(len(skipped) >= 1, "至少1步被降级跳过")
        completed = [s for phase in task_dict["phases"] for s in phase
                     if s["status"] == "completed"]
        assert_eq(len(completed), 2, "2步正常完成")
        print(f"  降级: {len(skipped)}步跳过, {len(completed)}步完成")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ============================================================================
# 主函数
# ============================================================================

def _cleanup_stale_state():
    """清理测试遗留的持久化状态，避免污染其他测试（秩序化阶段1：测试数据隔离）"""
    import os
    import glob
    stale_files = [
        "./data/memory.db",
        "./data/goals_state.json",
    ]
    for f in stale_files:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    for f in glob.glob("./data/checkpoints/*.json"):
        try:
            os.remove(f)
        except OSError:
            pass
    for f in glob.glob("./data/skills/*.py"):
        try:
            os.remove(f)
        except OSError:
            pass


def main():
    # 清理上次运行可能遗留的持久化状态
    _cleanup_stale_state()

    print("=" * 70)
    print("阶段7测试：综合验证与长任务实战 — 端到端集成")
    print("=" * 70)

    tests = [
        test_scenario1_end_to_end_long_task,
        test_scenario2_multi_agent_collaboration,
        test_scenario3_self_organizing_swarm,
        test_scenario4_skill_evolution_loop,
        test_scenario5_checkpoint_resume,
        test_scenario6_full_agent_lifecycle,
        test_scenario7_failure_recovery_degradation,
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

    # 清理本测试产生的持久化状态，避免污染后续测试
    _cleanup_stale_state()

    print("\n" + "=" * 70)
    print(f"测试结果: {passed} passed, {failed} failed")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
