"""
协作式自愈模块。

节点宕机时，邻居接管其未完成任务，实现集群级容错。

第一性原理：
- 生物群体中个体故障时，其他个体接管其职责（如蜂群失蜂后工蜂补位）
- 分布式系统通过任务迁移实现节点级容错
- 接管应有序：检测故障 → 迁移任务 → 恢复执行

设计要点：
- 故障检测：基于心跳超时
- 任务迁移：从故障节点提取未完成任务，重新分配
- 接管协调：避免多节点同时接管同一任务（领导节点协调）
- 幂等性：任务迁移可重试，不产生重复执行
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agent_core.common.logger import get_logger
from agent_core.distributed.task_distributor import (
    DistributedTask,
    TaskDistributor,
)

# 心跳超时（秒）：超过此时间未收到心跳视为故障
_HEARTBEAT_TIMEOUT = 8.0
# 故障检测间隔（秒）
_FAILURE_CHECK_INTERVAL = 2.0
# 接管协调锁超时（秒）
_TAKEOVER_LOCK_TIMEOUT = 5.0


@dataclass
class NodeStatus:
    """节点状态。"""

    node_id: str
    last_heartbeat: float
    is_alive: bool = True
    tasks_assigned: List[str] = field(default_factory=list)
    takeover_by: Optional[str] = None  # 接管者节点 ID


class CooperativeHealing:
    """
    协作式自愈管理器。

    监控集群节点健康，故障时协调任务迁移。
    """

    def __init__(self, task_distributor: TaskDistributor) -> None:
        self._logger = get_logger()
        self._distributor = task_distributor
        self._lock = threading.RLock()
        # 节点状态表：{node_id: NodeStatus}
        self._nodes: Dict[str, NodeStatus] = {}
        # 本节点 ID
        self._self_id: Optional[str] = None
        # 接管回调：当本节点接管任务时调用
        self._takeover_callback: Optional[
            Callable[[DistributedTask], Any]
        ] = None
        # 故障事件历史
        self._failure_events: List[Dict[str, Any]] = []
        # 接管记录：{task_id: takeover_node_id}
        self._takeover_records: Dict[str, str] = {}

    def set_self_id(self, node_id: str) -> None:
        """设置本节点 ID。"""
        with self._lock:
            self._self_id = node_id

    def set_takeover_callback(
        self,
        callback: Callable[[DistributedTask], Any],
    ) -> None:
        """设置接管回调（当本节点接管任务时调用）。"""
        self._takeover_callback = callback

    def register_node(self, node_id: str) -> None:
        """注册节点到监控。"""
        with self._lock:
            if node_id not in self._nodes:
                self._nodes[node_id] = NodeStatus(
                    node_id=node_id,
                    last_heartbeat=time.time(),
                )
                self._logger.info(
                    f"[CoopHealing] Node {node_id} registered"
                )

    def heartbeat(self, node_id: str, tasks: Optional[List[str]] = None) -> None:
        """
        更新节点心跳。

        Args:
            node_id: 节点 ID。
            tasks: 该节点当前持有的任务 ID 列表。
        """
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                node = NodeStatus(
                    node_id=node_id,
                    last_heartbeat=time.time(),
                )
                self._nodes[node_id] = node
            node.last_heartbeat = time.time()
            node.is_alive = True
            if tasks is not None:
                node.tasks_assigned = list(tasks)

    def detect_failures(self) -> List[str]:
        """
        检测故障节点。

        Returns:
            故障节点 ID 列表。
        """
        with self._lock:
            now = time.time()
            failed: List[str] = []
            for node_id, node in self._nodes.items():
                if not node.is_alive:
                    continue
                if now - node.last_heartbeat > _HEARTBEAT_TIMEOUT:
                    node.is_alive = False
                    failed.append(node_id)
                    self._failure_events.append(
                        {
                            "node_id": node_id,
                            "timestamp": now,
                            "last_heartbeat": node.last_heartbeat,
                            "tasks_lost": list(node.tasks_assigned),
                        }
                    )
                    self._logger.warning(
                        f"[CoopHealing] Node {node_id} detected as failed "
                        f"(last heartbeat {now - node.last_heartbeat:.1f}s ago, "
                        f"{len(node.tasks_assigned)} tasks affected)"
                    )
            return failed

    def handle_failure(self, failed_node_id: str) -> List[str]:
        """
        处理节点故障：迁移其未完成任务。

        Args:
            failed_node_id: 故障节点 ID。

        Returns:
            成功迁移的任务 ID 列表。
        """
        with self._lock:
            node = self._nodes.get(failed_node_id)
            if node is None:
                return []
            migrated: List[str] = []
            # 将故障节点的任务在分发器中重新入池
            # TaskDistributor.unregister_agent 会自动重新入池
            self._distributor.unregister_agent(failed_node_id)
            # 记录接管
            for task_id in node.tasks_assigned:
                self._takeover_records[task_id] = (
                    self._self_id or "unknown"
                )
                migrated.append(task_id)
            node.tasks_assigned.clear()
            self._logger.info(
                f"[CoopHealing] Handled failure of {failed_node_id}, "
                f"migrated {len(migrated)} tasks"
            )
            return migrated

    def attempt_takeover(self) -> List[DistributedTask]:
        """
        本节点尝试接管故障节点的任务。

        从分发器分配任务，执行接管回调。
        回调失败的任务标记失败后不再重新分配（避免无限循环）。

        Returns:
            本节点接管的任务列表。
        """
        if self._self_id is None:
            return []
        taken_over: List[DistributedTask] = []
        # 持续分配直到无可用任务
        while True:
            task = self._distributor.assign_task(self._self_id)
            if task is None:
                break
            if self._takeover_callback is not None:
                try:
                    self._takeover_callback(task)
                    taken_over.append(task)
                except Exception as exc:
                    self._logger.error(
                        f"[CoopHealing] Takeover callback failed "
                        f"for task {task.task_id}: {exc}"
                    )
                    # 标记失败但不重新入池（避免无限循环）
                    # 直接从 assigned 移除并记入 completed（失败状态）
                    with self._distributor._lock:
                        failed_task = self._distributor._assigned.pop(
                            task.task_id, None
                        )
                        if failed_task is not None:
                            failed_task.failed = True
                            failed_task.retry_count += 1
                            self._distributor._completed.append(failed_task)
                            # 减少负载
                            if failed_task.assigned_to:
                                current = self._distributor._loads.get(
                                    failed_task.assigned_to, 0
                                )
                                self._distributor._loads[
                                    failed_task.assigned_to
                                ] = max(0, current - 1)
            else:
                taken_over.append(task)
        if taken_over:
            self._logger.info(
                f"[CoopHealing] Node {self._self_id} took over "
                f"{len(taken_over)} tasks"
            )
        return taken_over

    def get_node_status(self, node_id: str) -> Optional[NodeStatus]:
        """获取节点状态。"""
        with self._lock:
            return self._nodes.get(node_id)

    def get_alive_nodes(self) -> List[str]:
        """获取存活节点列表。"""
        with self._lock:
            return [
                nid for nid, node in self._nodes.items() if node.is_alive
            ]

    def get_failed_nodes(self) -> List[str]:
        """获取故障节点列表。"""
        with self._lock:
            return [
                nid for nid, node in self._nodes.items() if not node.is_alive
            ]

    def get_failure_events(self) -> List[Dict[str, Any]]:
        """获取故障事件历史。"""
        with self._lock:
            return list(self._failure_events)

    def get_takeover_records(self) -> Dict[str, str]:
        """获取接管记录。"""
        with self._lock:
            return dict(self._takeover_records)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息。"""
        with self._lock:
            return {
                "total_nodes": len(self._nodes),
                "alive_nodes": sum(
                    1 for n in self._nodes.values() if n.is_alive
                ),
                "failed_nodes": sum(
                    1 for n in self._nodes.values() if not n.is_alive
                ),
                "failure_events": len(self._failure_events),
                "takeovers": len(self._takeover_records),
            }
