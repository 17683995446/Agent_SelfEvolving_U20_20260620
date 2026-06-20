"""
任务分发与负载均衡模块。

支持多 Agent 间任务分配，基于能力声明与当前负载。

第一性原理：
- 社会性昆虫通过信息素协调分工，个体根据自身能力与群体需求选择任务
- 负载均衡避免单点过载，提升集群整体吞吐
- 任务分发应考虑 Agent 能力声明（capability）与当前负载（load）

设计要点：
- 线程安全：任务池可能被多个 Agent 并发访问
- 能力匹配：任务类型与 Agent 能力声明匹配
- 负载感知：优先分配给负载最低的合格 Agent
- 公平性：避免任务饥饿（FIFO 基础上叠加负载均衡）
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional

from agent_core.common.logger import get_logger

# 负载过期时间（秒）：Agent 负载信息超过此时间视为陈旧
_LOAD_TTL_SECONDS = 15.0
# 任务超时时间（秒）：分配后未确认完成则视为失败
_TASK_TIMEOUT_SECONDS = 30.0
# 最大重试次数
_MAX_RETRIES = 3


@dataclass
class AgentCapability:
    """Agent 能力声明。"""

    agent_id: str
    capabilities: List[str]  # 支持的任务类型列表
    max_load: int = 5  # 最大并发任务数
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DistributedTask:
    """分布式任务条目。"""

    task_id: str
    task_type: str
    payload: Dict[str, Any]
    created_at: float
    assigned_to: Optional[str] = None
    assigned_at: Optional[float] = None
    completed: bool = False
    failed: bool = False
    retry_count: int = 0
    result: Optional[Dict[str, Any]] = None


class TaskDistributor:
    """
    任务分发器。

    管理待分配任务池，基于 Agent 能力与负载进行分配。
    """

    def __init__(self) -> None:
        self._logger = get_logger()
        self._lock = threading.RLock()
        # 任务池：FIFO 队列
        self._pending: Deque[DistributedTask] = deque()
        # 已分配任务：{task_id: DistributedTask}
        self._assigned: Dict[str, DistributedTask] = {}
        # 已完成任务（历史记录，限制数量）
        self._completed: Deque[DistributedTask] = deque(maxlen=100)
        # Agent 能力注册表：{agent_id: AgentCapability}
        self._agents: Dict[str, AgentCapability] = {}
        # Agent 当前负载：{agent_id: load_count}
        self._loads: Dict[str, int] = defaultdict(int)
        # Agent 负载更新时间：{agent_id: timestamp}
        self._load_timestamps: Dict[str, float] = {}
        # 任务 ID 计数器
        self._task_counter = 0

    def register_agent(self, capability: AgentCapability) -> None:
        """注册 Agent 能力。"""
        with self._lock:
            self._agents[capability.agent_id] = capability
            self._loads.setdefault(capability.agent_id, 0)
            self._load_timestamps[capability.agent_id] = time.time()
        self._logger.info(
            f"[TaskDistributor] Agent {capability.agent_id} registered "
            f"with capabilities {capability.capabilities}"
        )

    def unregister_agent(self, agent_id: str) -> None:
        """注销 Agent，其已分配任务重新入池。"""
        with self._lock:
            if agent_id not in self._agents:
                return
            del self._agents[agent_id]
            self._loads.pop(agent_id, None)
            self._load_timestamps.pop(agent_id, None)
            # 该 Agent 的已分配任务重新入池
            reassigned = []
            for tid, task in list(self._assigned.items()):
                if task.assigned_to == agent_id:
                    task.assigned_to = None
                    task.assigned_at = None
                    task.retry_count += 1
                    if task.retry_count <= _MAX_RETRIES:
                        self._pending.append(task)
                        reassigned.append(tid)
                    else:
                        task.failed = True
                        self._completed.append(task)
                    del self._assigned[tid]
            if reassigned:
                self._logger.info(
                    f"[TaskDistributor] Agent {agent_id} unregistered, "
                    f"reassigned {len(reassigned)} tasks"
                )

    def submit_task(
        self,
        task_type: str,
        payload: Dict[str, Any],
    ) -> str:
        """
        提交任务到分发器。

        Args:
            task_type: 任务类型。
            payload: 任务负载数据。

        Returns:
            任务 ID。
        """
        with self._lock:
            self._task_counter += 1
            task_id = f"task_{self._task_counter}"
            task = DistributedTask(
                task_id=task_id,
                task_type=task_type,
                payload=payload,
                created_at=time.time(),
            )
            self._pending.append(task)
        self._logger.debug(
            f"[TaskDistributor] Task {task_id} submitted (type={task_type})"
        )
        return task_id

    def assign_task(self, agent_id: str) -> Optional[DistributedTask]:
        """
        为指定 Agent 分配一个任务。

        选择逻辑：
        1. 过滤出该 Agent 能力匹配的待分配任务
        2. 检查 Agent 负载是否已达上限
        3. FIFO 选择最早的任务

        Args:
            agent_id: 请求任务的 Agent ID。

        Returns:
            分配的任务，无可用则返回 None。
        """
        with self._lock:
            capability = self._agents.get(agent_id)
            if capability is None:
                return None
            # 负载检查
            current_load = self._loads.get(agent_id, 0)
            if current_load >= capability.max_load:
                return None
            # 负载陈旧检查
            self._refresh_load(agent_id)
            # FIFO 查找能力匹配的任务
            for _ in range(len(self._pending)):
                task = self._pending.popleft()
                if task.task_type in capability.capabilities:
                    task.assigned_to = agent_id
                    task.assigned_at = time.time()
                    self._assigned[task.task_id] = task
                    self._loads[agent_id] = current_load + 1
                    self._load_timestamps[agent_id] = time.time()
                    self._logger.debug(
                        f"[TaskDistributor] Task {task.task_id} "
                        f"assigned to {agent_id}"
                    )
                    return task
                else:
                    # 不匹配，放回队列末尾
                    self._pending.append(task)
            return None

    def complete_task(
        self,
        task_id: str,
        result: Dict[str, Any],
    ) -> bool:
        """
        标记任务完成。

        Args:
            task_id: 任务 ID。
            result: 任务结果。

        Returns:
            成功标记返回 True，任务不存在或未分配返回 False。
        """
        with self._lock:
            task = self._assigned.pop(task_id, None)
            if task is None:
                return False
            task.completed = True
            task.result = result
            self._completed.append(task)
            # 减少负载
            if task.assigned_to:
                current = self._loads.get(task.assigned_to, 0)
                self._loads[task.assigned_to] = max(0, current - 1)
            self._logger.debug(
                f"[TaskDistributor] Task {task_id} completed by {task.assigned_to}"
            )
            return True

    def fail_task(self, task_id: str, reason: str = "") -> bool:
        """
        标记任务失败，若未超重试次数则重新入池。

        Args:
            task_id: 任务 ID。
            reason: 失败原因。

        Returns:
            重新入池返回 True，彻底失败返回 False。
        """
        with self._lock:
            task = self._assigned.pop(task_id, None)
            if task is None:
                return False
            # 减少负载
            if task.assigned_to:
                current = self._loads.get(task.assigned_to, 0)
                self._loads[task.assigned_to] = max(0, current - 1)
            task.retry_count += 1
            if task.retry_count <= _MAX_RETRIES:
                task.assigned_to = None
                task.assigned_at = None
                self._pending.append(task)
                self._logger.info(
                    f"[TaskDistributor] Task {task_id} failed (attempt "
                    f"{task.retry_count}), requeued: {reason}"
                )
                return True
            else:
                task.failed = True
                self._completed.append(task)
                self._logger.warning(
                    f"[TaskDistributor] Task {task_id} permanently failed "
                    f"after {task.retry_count} attempts: {reason}"
                )
                return False

    def _refresh_load(self, agent_id: str) -> None:
        """刷新负载（清理超时任务的负载计数）。"""
        last_update = self._load_timestamps.get(agent_id, 0.0)
        if time.time() - last_update > _LOAD_TTL_SECONDS:
            # 负载信息陈旧，重置为 0
            self._loads[agent_id] = 0

    def cleanup_timeouts(self) -> List[str]:
        """
        清理超时任务，返回超时任务 ID 列表。

        超时任务被标记为失败并重新入池（若未超重试次数）。
        """
        with self._lock:
            now = time.time()
            timed_out: List[str] = []
            for tid, task in list(self._assigned.items()):
                if task.assigned_at and (now - task.assigned_at) > _TASK_TIMEOUT_SECONDS:
                    timed_out.append(tid)
                    self.fail_task(tid, "timeout")
            return timed_out

    def get_pending_count(self) -> int:
        """获取待分配任务数。"""
        with self._lock:
            return len(self._pending)

    def get_assigned_count(self) -> int:
        """获取已分配任务数。"""
        with self._lock:
            return len(self._assigned)

    def get_agent_load(self, agent_id: str) -> int:
        """获取 Agent 当前负载。"""
        with self._lock:
            return self._loads.get(agent_id, 0)

    def get_agent_count(self) -> int:
        """获取已注册 Agent 数。"""
        with self._lock:
            return len(self._agents)

    def get_stats(self) -> Dict[str, Any]:
        """获取分发器统计。"""
        with self._lock:
            return {
                "pending": len(self._pending),
                "assigned": len(self._assigned),
                "completed": len(self._completed),
                "agents": len(self._agents),
                "loads": dict(self._loads),
            }

    def find_best_agent(self, task_type: str) -> Optional[str]:
        """
        为指定任务类型寻找最佳 Agent（负载最低的能力匹配 Agent）。

        Args:
            task_type: 任务类型。

        Returns:
            最佳 Agent ID，无可用则 None。
        """
        with self._lock:
            candidates: List[tuple] = []  # (load, agent_id)
            for agent_id, cap in self._agents.items():
                if task_type not in cap.capabilities:
                    continue
                self._refresh_load(agent_id)
                current_load = self._loads.get(agent_id, 0)
                if current_load >= cap.max_load:
                    continue
                candidates.append((current_load, agent_id))
            if not candidates:
                return None
            # 按负载升序，选负载最低的
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]
