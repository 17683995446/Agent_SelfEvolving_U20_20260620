"""
C-10超复杂场景测试：分布式扩展与多Agent协作。

验证C-10新增能力在极端复杂场景下的正确性：
- 任务分发与负载均衡：能力匹配、负载感知、FIFO+负载均衡
- 任务生命周期：提交/分配/完成/失败/重试/超时
- 协作式自愈：故障检测、任务迁移、邻居接管
- 多节点集群：3节点宕机场景任务零丢失
- 并发安全：多 Agent 并发分配无冲突
"""

import threading
import time
import unittest
from typing import List

from agent_core.distributed.cooperative_healing import CooperativeHealing
from agent_core.distributed.task_distributor import (
    AgentCapability,
    DistributedTask,
    TaskDistributor,
)


class TestTaskDistributorBasics(unittest.TestCase):
    """任务分发器基础功能验证。"""

    def test_register_agent(self) -> None:
        """注册 Agent 后可分配任务。"""
        dist = TaskDistributor()
        dist.register_agent(
            AgentCapability(
                agent_id="agent_1",
                capabilities=["safety", "gain"],
            )
        )
        self.assertEqual(dist.get_agent_count(), 1)

    def test_unregister_agent(self) -> None:
        """注销 Agent 后任务重新入池。"""
        dist = TaskDistributor()
        dist.register_agent(
            AgentCapability(
                agent_id="agent_1",
                capabilities=["safety"],
            )
        )
        task_id = dist.submit_task("safety", {"data": "test"})
        dist.assign_task("agent_1")
        self.assertEqual(dist.get_assigned_count(), 1)
        # 注销 Agent，任务应重新入池
        dist.unregister_agent("agent_1")
        self.assertEqual(dist.get_pending_count(), 1)
        self.assertEqual(dist.get_assigned_count(), 0)

    def test_submit_task(self) -> None:
        """提交任务返回任务 ID。"""
        dist = TaskDistributor()
        task_id = dist.submit_task("safety", {"data": "test"})
        self.assertTrue(task_id.startswith("task_"))
        self.assertEqual(dist.get_pending_count(), 1)

    def test_assign_no_capability_match(self) -> None:
        """Agent 能力不匹配时不分配。"""
        dist = TaskDistributor()
        dist.register_agent(
            AgentCapability(
                agent_id="agent_1",
                capabilities=["safety"],
            )
        )
        dist.submit_task("gain", {"data": "test"})
        task = dist.assign_task("agent_1")
        self.assertIsNone(task)
        # 任务仍在待分配队列
        self.assertEqual(dist.get_pending_count(), 1)

    def test_assign_unknown_agent(self) -> None:
        """未知 Agent 分配返回 None。"""
        dist = TaskDistributor()
        dist.submit_task("safety", {})
        task = dist.assign_task("nonexistent")
        self.assertIsNone(task)


class TestTaskDistributorLoadBalance(unittest.TestCase):
    """负载均衡验证。"""

    def test_load_limit_respected(self) -> None:
        """Agent 负载达上限后不再分配。"""
        dist = TaskDistributor()
        dist.register_agent(
            AgentCapability(
                agent_id="agent_1",
                capabilities=["safety"],
                max_load=2,
            )
        )
        dist.submit_task("safety", {})
        dist.submit_task("safety", {})
        dist.submit_task("safety", {})
        # 分配两个任务达到上限
        t1 = dist.assign_task("agent_1")
        t2 = dist.assign_task("agent_1")
        self.assertIsNotNone(t1)
        self.assertIsNotNone(t2)
        # 第三个不应分配
        t3 = dist.assign_task("agent_1")
        self.assertIsNone(t3)
        self.assertEqual(dist.get_agent_load("agent_1"), 2)

    def test_find_best_agent_lowest_load(self) -> None:
        """find_best_agent 返回负载最低的 Agent。"""
        dist = TaskDistributor()
        dist.register_agent(
            AgentCapability(
                agent_id="agent_1",
                capabilities=["safety"],
                max_load=5,
            )
        )
        dist.register_agent(
            AgentCapability(
                agent_id="agent_2",
                capabilities=["safety"],
                max_load=5,
            )
        )
        # agent_1 分配 2 个任务，agent_2 分配 0 个
        dist.submit_task("safety", {})
        dist.submit_task("safety", {})
        dist.assign_task("agent_1")
        dist.assign_task("agent_1")
        # 最佳应是 agent_2（负载更低）
        best = dist.find_best_agent("safety")
        self.assertEqual(best, "agent_2")

    def test_find_best_agent_no_match(self) -> None:
        """无能力匹配 Agent 时返回 None。"""
        dist = TaskDistributor()
        dist.register_agent(
            AgentCapability(
                agent_id="agent_1",
                capabilities=["safety"],
            )
        )
        best = dist.find_best_agent("gain")
        self.assertIsNone(best)

    def test_find_best_agent_all_overloaded(self) -> None:
        """所有 Agent 过载时返回 None。"""
        dist = TaskDistributor()
        dist.register_agent(
            AgentCapability(
                agent_id="agent_1",
                capabilities=["safety"],
                max_load=1,
            )
        )
        dist.submit_task("safety", {})
        dist.assign_task("agent_1")
        best = dist.find_best_agent("safety")
        self.assertIsNone(best)


class TestTaskLifecycle(unittest.TestCase):
    """任务生命周期验证。"""

    def test_complete_task(self) -> None:
        """完成任务后负载减少。"""
        dist = TaskDistributor()
        dist.register_agent(
            AgentCapability(
                agent_id="agent_1",
                capabilities=["safety"],
            )
        )
        task_id = dist.submit_task("safety", {})
        dist.assign_task("agent_1")
        self.assertEqual(dist.get_agent_load("agent_1"), 1)
        result = dist.complete_task(task_id, {"status": "done"})
        self.assertTrue(result)
        self.assertEqual(dist.get_agent_load("agent_1"), 0)
        self.assertEqual(dist.get_assigned_count(), 0)

    def test_complete_unknown_task(self) -> None:
        """完成未知任务返回 False。"""
        dist = TaskDistributor()
        result = dist.complete_task("nonexistent", {})
        self.assertFalse(result)

    def test_fail_task_requeue(self) -> None:
        """任务失败后重新入池（未超重试次数）。"""
        dist = TaskDistributor()
        dist.register_agent(
            AgentCapability(
                agent_id="agent_1",
                capabilities=["safety"],
            )
        )
        task_id = dist.submit_task("safety", {})
        dist.assign_task("agent_1")
        requeued = dist.fail_task(task_id, "test failure")
        self.assertTrue(requeued)
        self.assertEqual(dist.get_pending_count(), 1)
        self.assertEqual(dist.get_assigned_count(), 0)

    def test_fail_task_permanent_after_max_retries(self) -> None:
        """超过最大重试次数后任务永久失败。"""
        dist = TaskDistributor()
        dist.register_agent(
            AgentCapability(
                agent_id="agent_1",
                capabilities=["safety"],
            )
        )
        task_id = dist.submit_task("safety", {})
        # 失败 4 次（超过 _MAX_RETRIES=3）
        for _ in range(4):
            dist.assign_task("agent_1")
            dist.fail_task(task_id, "repeated failure")
        # 任务应已永久失败（不在 pending 也不在 assigned）
        self.assertEqual(dist.get_pending_count(), 0)
        self.assertEqual(dist.get_assigned_count(), 0)

    def test_cleanup_timeouts(self) -> None:
        """超时任务被清理。"""
        dist = TaskDistributor()
        dist.register_agent(
            AgentCapability(
                agent_id="agent_1",
                capabilities=["safety"],
            )
        )
        task_id = dist.submit_task("safety", {})
        dist.assign_task("agent_1")
        # 手动设置分配时间为很久以前
        with dist._lock:
            dist._assigned[task_id].assigned_at = time.time() - 100
        timed_out = dist.cleanup_timeouts()
        self.assertIn(task_id, timed_out)
        # 超时任务应重新入池
        self.assertEqual(dist.get_pending_count(), 1)


class TestCooperativeHealing(unittest.TestCase):
    """协作式自愈验证。"""

    def test_register_node(self) -> None:
        """注册节点。"""
        dist = TaskDistributor()
        healing = CooperativeHealing(dist)
        healing.register_node("node_1")
        self.assertIsNotNone(healing.get_node_status("node_1"))

    def test_heartbeat_updates(self) -> None:
        """心跳更新节点状态。"""
        dist = TaskDistributor()
        healing = CooperativeHealing(dist)
        healing.register_node("node_1")
        healing.heartbeat("node_1", ["task_1", "task_2"])
        node = healing.get_node_status("node_1")
        assert node is not None
        self.assertTrue(node.is_alive)
        self.assertEqual(len(node.tasks_assigned), 2)

    def test_detect_failure(self) -> None:
        """心跳超时检测故障。"""
        dist = TaskDistributor()
        healing = CooperativeHealing(dist)
        healing.register_node("node_1")
        # 手动设置心跳为很久以前
        with healing._lock:
            healing._nodes["node_1"].last_heartbeat = time.time() - 100
        failed = healing.detect_failures()
        self.assertIn("node_1", failed)
        self.assertIn("node_1", healing.get_failed_nodes())

    def test_no_false_positive_failure(self) -> None:
        """正常心跳不误报故障。"""
        dist = TaskDistributor()
        healing = CooperativeHealing(dist)
        healing.register_node("node_1")
        healing.heartbeat("node_1")
        failed = healing.detect_failures()
        self.assertEqual(failed, [])
        self.assertIn("node_1", healing.get_alive_nodes())

    def test_handle_failure_migrates_tasks(self) -> None:
        """故障处理迁移任务。"""
        dist = TaskDistributor()
        healing = CooperativeHealing(dist)
        # 注册故障节点
        dist.register_agent(
            AgentCapability(
                agent_id="node_1",
                capabilities=["safety"],
            )
        )
        healing.register_node("node_1")
        # 分配任务给故障节点
        task_id = dist.submit_task("safety", {})
        dist.assign_task("node_1")
        healing.heartbeat("node_1", [task_id])
        # 模拟故障
        with healing._lock:
            healing._nodes["node_1"].last_heartbeat = time.time() - 100
        healing.detect_failures()
        # 处理故障
        migrated = healing.handle_failure("node_1")
        self.assertIn(task_id, migrated)
        # 任务应重新入池
        self.assertEqual(dist.get_pending_count(), 1)

    def test_attempt_takeover(self) -> None:
        """本节点接管故障节点任务。"""
        dist = TaskDistributor()
        healing = CooperativeHealing(dist)
        healing.set_self_id("node_2")
        # 注册接管节点
        dist.register_agent(
            AgentCapability(
                agent_id="node_2",
                capabilities=["safety"],
            )
        )
        healing.register_node("node_2")
        # 提交任务
        dist.submit_task("safety", {"data": "orphan"})
        # 接管
        taken = healing.attempt_takeover()
        self.assertEqual(len(taken), 1)
        self.assertEqual(taken[0].assigned_to, "node_2")

    def test_takeover_callback_invoked(self) -> None:
        """接管回调被调用。"""
        dist = TaskDistributor()
        healing = CooperativeHealing(dist)
        healing.set_self_id("node_2")
        dist.register_agent(
            AgentCapability(
                agent_id="node_2",
                capabilities=["safety"],
            )
        )
        callback_calls: List[DistributedTask] = []

        def callback(task: DistributedTask) -> None:
            callback_calls.append(task)

        healing.set_takeover_callback(callback)
        dist.submit_task("safety", {})
        healing.attempt_takeover()
        self.assertEqual(len(callback_calls), 1)

    def test_takeover_callback_failure_handled(self) -> None:
        """接管回调失败不崩溃且任务标记失败（不重新入池避免无限循环）。"""
        dist = TaskDistributor()
        healing = CooperativeHealing(dist)
        healing.set_self_id("node_2")
        dist.register_agent(
            AgentCapability(
                agent_id="node_2",
                capabilities=["safety"],
            )
        )

        def failing_callback(task: DistributedTask) -> None:
            raise RuntimeError("callback failed")

        healing.set_takeover_callback(failing_callback)
        dist.submit_task("safety", {})
        taken = healing.attempt_takeover()
        # 回调失败的任务不计入接管列表
        self.assertEqual(len(taken), 0)
        # 任务应被标记失败（不在 pending 也不在 assigned）
        self.assertEqual(dist.get_pending_count(), 0)
        self.assertEqual(dist.get_assigned_count(), 0)

    def test_get_stats(self) -> None:
        """统计信息正确。"""
        dist = TaskDistributor()
        healing = CooperativeHealing(dist)
        healing.register_node("node_1")
        healing.register_node("node_2")
        with healing._lock:
            healing._nodes["node_1"].last_heartbeat = time.time() - 100
        healing.detect_failures()
        stats = healing.get_stats()
        self.assertEqual(stats["total_nodes"], 2)
        self.assertEqual(stats["alive_nodes"], 1)
        self.assertEqual(stats["failed_nodes"], 1)
        self.assertGreaterEqual(stats["failure_events"], 1)


class TestMultiNodeCluster(unittest.TestCase):
    """多节点集群场景验证。"""

    def test_three_node_failover_zero_task_loss(self) -> None:
        """3节点集群，1节点宕机，任务零丢失。"""
        dist = TaskDistributor()
        healing = CooperativeHealing(dist)
        # 注册3个节点
        for nid in ["node_1", "node_2", "node_3"]:
            dist.register_agent(
                AgentCapability(
                    agent_id=nid,
                    capabilities=["safety", "gain"],
                    max_load=10,
                )
            )
            healing.register_node(nid)
        healing.set_self_id("node_2")
        # node_1 接收 3 个任务
        task_ids = []
        for i in range(3):
            tid = dist.submit_task("safety", {"idx": i})
            task_ids.append(tid)
            dist.assign_task("node_1")
        healing.heartbeat("node_1", list(task_ids))
        self.assertEqual(dist.get_agent_load("node_1"), 3)
        # node_1 宕机
        with healing._lock:
            healing._nodes["node_1"].last_heartbeat = time.time() - 100
        healing.detect_failures()
        migrated = healing.handle_failure("node_1")
        # 3个任务都被迁移
        self.assertEqual(len(migrated), 3)
        # 任务重新入池
        self.assertEqual(dist.get_pending_count(), 3)
        # node_2 接管
        taken = healing.attempt_takeover()
        self.assertEqual(len(taken), 3)
        # 零丢失：所有任务都被 node_2 接管
        for task in taken:
            self.assertEqual(task.assigned_to, "node_2")
        self.assertEqual(dist.get_agent_load("node_2"), 3)

    def test_concurrent_assignment_no_conflict(self) -> None:
        """多 Agent 并发分配无冲突（线程安全）。"""
        dist = TaskDistributor()
        # 注册多个 Agent
        for i in range(5):
            dist.register_agent(
                AgentCapability(
                    agent_id=f"agent_{i}",
                    capabilities=["safety"],
                    max_load=100,
                )
            )
        # 提交 50 个任务
        for i in range(50):
            dist.submit_task("safety", {"idx": i})
        # 并发分配
        assigned_tasks: List[str] = []
        lock = threading.Lock()

        def assign(agent_id: str) -> None:
            while True:
                task = dist.assign_task(agent_id)
                if task is None:
                    break
                with lock:
                    assigned_tasks.append(task.task_id)

        threads = [
            threading.Thread(target=assign, args=(f"agent_{i}",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 50 个任务都被分配，无重复
        self.assertEqual(len(assigned_tasks), 50)
        self.assertEqual(len(set(assigned_tasks)), 50)  # 无重复
        self.assertEqual(dist.get_pending_count(), 0)

    def test_cascading_failover(self) -> None:
        """级联故障：node_1 宕机→node_2 接管→node_2 宕机→node_3 接管。"""
        dist = TaskDistributor()
        healing = CooperativeHealing(dist)
        for nid in ["node_1", "node_2", "node_3"]:
            dist.register_agent(
                AgentCapability(
                    agent_id=nid,
                    capabilities=["safety"],
                    max_load=10,
                )
            )
            healing.register_node(nid)
        # node_1 持有任务
        task_id = dist.submit_task("safety", {"data": "important"})
        dist.assign_task("node_1")
        healing.heartbeat("node_1", [task_id])
        # node_1 宕机
        with healing._lock:
            healing._nodes["node_1"].last_heartbeat = time.time() - 100
        healing.detect_failures()
        healing.handle_failure("node_1")
        # node_2 接管
        healing.set_self_id("node_2")
        taken = healing.attempt_takeover()
        self.assertEqual(len(taken), 1)
        self.assertEqual(taken[0].task_id, task_id)
        # node_2 宕机
        healing.heartbeat("node_2", [task_id])
        with healing._lock:
            healing._nodes["node_2"].last_heartbeat = time.time() - 100
        healing.detect_failures()
        healing.handle_failure("node_2")
        # node_3 接管
        healing.set_self_id("node_3")
        taken2 = healing.attempt_takeover()
        self.assertEqual(len(taken2), 1)
        self.assertEqual(taken2[0].task_id, task_id)
        # 任务最终被 node_3 持有
        self.assertEqual(taken2[0].assigned_to, "node_3")

    def test_load_distribution_across_nodes(self) -> None:
        """任务在多节点间均衡分布。"""
        dist = TaskDistributor()
        for i in range(3):
            dist.register_agent(
                AgentCapability(
                    agent_id=f"node_{i}",
                    capabilities=["safety"],
                    max_load=100,
                )
            )
        # 提交 9 个任务
        for i in range(9):
            dist.submit_task("safety", {"idx": i})
        # 轮流分配
        assigned_counts = {f"node_{i}": 0 for i in range(3)}
        for i in range(9):
            agent_id = f"node_{i % 3}"
            task = dist.assign_task(agent_id)
            if task:
                assigned_counts[agent_id] += 1
        # 每个节点分配 3 个
        for count in assigned_counts.values():
            self.assertEqual(count, 3)


class TestDistributedAgentIntegration(unittest.TestCase):
    """分布式 Agent 集成验证。"""

    def test_task_distributor_with_cooperative_healing(self) -> None:
        """任务分发器与协作式自愈集成。"""
        dist = TaskDistributor()
        healing = CooperativeHealing(dist)
        # 注册3节点
        for nid in ["A", "B", "C"]:
            dist.register_agent(
                AgentCapability(
                    agent_id=nid,
                    capabilities=["safety", "gain"],
                    max_load=5,
                )
            )
            healing.register_node(nid)
        # A 持有任务
        tid = dist.submit_task("safety", {})
        dist.assign_task("A")
        healing.heartbeat("A", [tid])
        # A 宕机
        with healing._lock:
            healing._nodes["A"].last_heartbeat = time.time() - 100
        healing.detect_failures()
        healing.handle_failure("A")
        # B 接管
        healing.set_self_id("B")
        taken = healing.attempt_takeover()
        self.assertEqual(len(taken), 1)
        # 验证接管记录
        records = healing.get_takeover_records()
        self.assertIn(tid, records)

    def test_failure_event_history(self) -> None:
        """故障事件被记录到历史。"""
        dist = TaskDistributor()
        healing = CooperativeHealing(dist)
        healing.register_node("X")
        with healing._lock:
            healing._nodes["X"].last_heartbeat = time.time() - 100
        healing.detect_failures()
        events = healing.get_failure_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["node_id"], "X")
        self.assertIn("timestamp", events[0])
        self.assertIn("last_heartbeat", events[0])


if __name__ == "__main__":
    unittest.main()
