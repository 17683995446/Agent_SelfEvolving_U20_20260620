"""
多Agent协作器（阶段3：从单agent到多agent协作）

第一性原理：社会性生物通过"通信→发现→分派→共识"四要素协作。
  - 通信：MessageBus 统一消息中继
  - 发现：AgentDiscovery 心跳维护邻居表
  - 分派：TaskDispatcher 按能力+负载分派任务
  - 共识：ConsensusEngine 2PC达成群体决策

MultiAgentCollaborator 封装 communication/ 栈，提供简洁接口：
  1. register_capability() — 注册本agent能处理的任务类型
  2. broadcast_heartbeat() — 广播心跳（让邻居发现自己）
  3. dispatch_task() — 分派任务到最佳邻居
  4. process_messages() — 处理收到的消息（心跳/任务/结果/共识）
  5. propose_consensus() — 发起共识提案
  6. get_status() — 协作状态

与agent.py的关系：
  - agent.collaborator 是 MultiAgentCollaborator 实例
  - agent.register_capability(task_type, handler) — 注册能力
  - agent.collaborate(task_type, payload) — 分派任务给邻居
  - agent.process_collaboration() — 处理协作消息（在_step中调用）
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from communication import (
    AgentMessage, MessageType,
    MessageBus, AgentDiscovery, NeighborInfo,
    TaskDispatcher, TaskRecord, TaskStatus,
    ConsensusEngine, Proposal, ConsensusState,
)
from core.interfaces import ICollaborator


class MultiAgentCollaborator(ICollaborator):
    """
    多Agent协作器

    封装 communication/ 栈，让单个 Agent 能：
    - 发现邻居（心跳）
    - 分派任务（按能力+负载）
    - 处理收到的任务
    - 参与共识

    核心方法（<=7个）：
    1. register_capability() — 注册能力
    2. broadcast_heartbeat() — 广播心跳
    3. dispatch_task() — 分派任务
    4. process_messages() — 处理收到的消息
    5. propose_consensus() — 发起共识
    6. get_status() — 状态
    7. get_capabilities() — 本agent能力列表
    """

    def __init__(self,
                 agent_id: str,
                 message_bus: Optional[MessageBus] = None,
                 heartbeat_interval_seconds: float = 3.0,
                 logger=None):
        """
        Args:
            agent_id: 本agent ID
            message_bus: 共享消息总线（多agent共用同一实例）
            heartbeat_interval_seconds: 心跳间隔
            logger: 日志器
        """
        self.agent_id = agent_id
        self.message_bus = message_bus or MessageBus()
        self.logger = logger

        # 通信栈组件
        self.discovery = AgentDiscovery(
            agent_id=agent_id,
            heartbeat_interval_seconds=heartbeat_interval_seconds,
        )
        self.dispatcher = TaskDispatcher(
            agent_id=agent_id,
            discovery=self.discovery,
        )
        self.consensus = ConsensusEngine(agent_id=agent_id)

        # 任务处理器：task_type → handler(payload) → result
        self._task_handlers: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        # 结果回调：task_id → callback(result_dict)
        self._result_callbacks: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        # 共识提案参与者数：proposal_id → total_participants
        self._proposal_participants: Dict[str, int] = {}

        # 订阅消息总线
        self._subscribe_to_bus()

        # 统计
        self._total_heartbeats_sent = 0
        self._total_tasks_dispatched = 0
        self._total_tasks_received = 0
        self._total_tasks_completed = 0

    # ========================================================================
    # 公开方法
    # ========================================================================

    def register_capability(self, task_type: str,
                            handler: Callable[[Dict[str, Any]], Any]) -> None:
        """
        注册本agent能处理的任务类型

        第一性原理：个体声明自己的专长，群体据此分派任务。
        """
        self._task_handlers[task_type] = handler
        if self.logger:
            self.logger.info(f"Capability registered: {task_type}")

    def get_capabilities(self) -> List[str]:
        """本agent能力列表"""
        return list(self._task_handlers.keys())

    def broadcast_heartbeat(self, load_score: float = 0.0,
                            metadata: Optional[Dict[str, Any]] = None) -> Optional[AgentMessage]:
        """
        广播心跳（让邻居发现自己）

        第一性原理：生物群体通过周期性信号维持群体结构。
        心跳携带能力列表和负载，供邻居决策分派。

        Args:
            load_score: 当前负载 0-1
            metadata: 额外元数据

        Returns:
            心跳消息（若到达间隔），否则None
        """
        msg = self.discovery.heartbeat(
            capabilities=self.get_capabilities(),
            load_score=load_score,
            metadata=metadata,
        )
        if msg is not None:
            self.message_bus.publish(msg)
            self._total_heartbeats_sent += 1
        return msg

    def dispatch_task(self,
                      task_type: str,
                      payload: Dict[str, Any],
                      required_capability: Optional[str] = None,
                      on_result: Optional[Callable[[Dict[str, Any]], None]] = None) -> Tuple[str, Optional[AgentMessage]]:
        """
        分派任务到最佳邻居

        第一性原理：蚁群根据距离和食物量动态调整采集路径。
        TaskDispatcher 根据邻居负载和能力选择最佳执行者。

        Args:
            task_type: 任务类型
            payload: 任务数据
            required_capability: 所需能力（None则不限制）
            on_result: 结果回调

        Returns:
            (task_id, dispatch_message) — 若无可用邻居，dispatch_message为None
        """
        task_id = f"task_{self.agent_id}_{int(time.time() * 1000)}"

        if required_capability:
            payload = {**payload, "required_capability": required_capability}

        self.dispatcher.submit_task(
            task_id=task_id,
            task_type=task_type,
            payload=payload,
        )

        if on_result:
            self._result_callbacks[task_id] = on_result

        msg = self.dispatcher.dispatch(task_id)
        self._total_tasks_dispatched += 1

        # 把分派消息发布到总线，让目标agent接收
        if msg is not None:
            self.message_bus.publish(msg)
        elif self.logger:
            self.logger.warning(
                f"Dispatch failed (no candidate): task_id={task_id} type={task_type}"
            )

        return task_id, msg

    def process_messages(self, max_messages: int = 100) -> int:
        """
        处理收到的消息

        第一性原理：神经系统的反射弧——感觉输入→处理→运动输出。
        MessageBus.deliver() 把待处理消息分发给已订阅的处理器。

        Returns:
            实际处理的消息数
        """
        # 清理过期邻居和提案
        self.discovery.prune_stale()
        self.consensus.prune_expired()

        # 检查超时任务，重分派
        retry_ids = self.dispatcher.check_timeouts()
        for tid in retry_ids:
            self.dispatcher.dispatch(tid)
            if self.logger:
                self.logger.info(f"Task re-dispatched (timeout): {tid}")

        # 分发消息
        return self.message_bus.deliver(max_messages=max_messages)

    def propose_consensus(self,
                          proposal_id: str,
                          value: Dict[str, Any],
                          participant_ids: List[str],
                          on_commit: Optional[Callable[[Dict[str, Any]], None]] = None) -> AgentMessage:
        """
        发起共识提案

        第一性原理：蜂群通过舞蹈共识选择最佳筑巢地点。
        ConsensusEngine 实现简化版2PC，让多Agent对决策达成一致。

        Args:
            proposal_id: 提案ID（唯一）
            value: 提案内容
            participant_ids: 参与者ID列表
            on_commit: 通过后的回调

        Returns:
            prepare 消息（广播给所有参与者）
        """
        if on_commit:
            self.consensus.register_commit_callback(proposal_id, on_commit)

        # 记录参与者数（含发起者自己），供record_vote计算quorum
        self._proposal_participants[proposal_id] = len(participant_ids) + 1

        msg = self.consensus.propose(
            proposal_id=proposal_id,
            value=value,
            participant_ids=participant_ids,
        )
        self.message_bus.publish(msg)
        return msg

    def get_status(self) -> Dict[str, Any]:
        """协作状态"""
        return {
            "agent_id": self.agent_id,
            "capabilities": self.get_capabilities(),
            "neighbors": self.discovery.get_stats(),
            "tasks": self.dispatcher.get_stats(),
            "message_bus": self.message_bus.get_stats(),
            "heartbeats_sent": self._total_heartbeats_sent,
            "tasks_dispatched": self._total_tasks_dispatched,
            "tasks_received": self._total_tasks_received,
            "tasks_completed": self._total_tasks_completed,
        }

    # ========================================================================
    # 内部方法
    # ========================================================================

    def _subscribe_to_bus(self) -> None:
        """订阅消息总线各类型消息"""
        self.message_bus.subscribe(MessageType.HEARTBEAT, self._on_heartbeat)
        self.message_bus.subscribe(MessageType.TASK, self._on_task)
        self.message_bus.subscribe(MessageType.RESULT, self._on_result)
        self.message_bus.subscribe(MessageType.COORDINATE, self._on_coordinate)
        self.message_bus.subscribe(MessageType.STATE, self._on_state)

    def _on_heartbeat(self, msg: AgentMessage) -> None:
        """处理心跳消息"""
        self.discovery.on_message(msg)

    def _on_task(self, msg: AgentMessage) -> None:
        """处理收到的任务消息"""
        # 忽略自己发出的任务
        if msg.sender_id == self.agent_id:
            return
        # 只处理发给自己的（点对点）
        if msg.target_id is not None and msg.target_id != self.agent_id:
            return

        self._total_tasks_received += 1

        task_type = msg.payload.get("task_type")
        task_payload = msg.payload.get("payload", {})
        task_id = msg.payload.get("task_id")

        handler = self._task_handlers.get(task_type)
        success = False
        result = None
        error = None

        if handler is None:
            error = f"无能力处理任务类型: {task_type}"
        else:
            try:
                result = handler(task_payload)
                success = True
            except Exception as e:
                error = f"{type(e).__name__}: {e}"

        # 发送结果消息
        result_msg = AgentMessage(
            sender_id=self.agent_id,
            msg_type=MessageType.RESULT,
            target_id=msg.sender_id,
            payload={
                "task_id": task_id,
                "success": success,
                "result": result,
                "error": error,
            },
        )
        self.message_bus.publish(result_msg)

        if self.logger:
            self.logger.info(
                f"Task handled: id={task_id} type={task_type} success={success}"
            )

    def _on_result(self, msg: AgentMessage) -> None:
        """处理任务结果消息"""
        # 忽略自己发出的结果
        if msg.sender_id == self.agent_id:
            return
        # 只处理发给自己的
        if msg.target_id is not None and msg.target_id != self.agent_id:
            return

        task_id = msg.payload.get("task_id")
        success = msg.payload.get("success", False)

        # 更新dispatcher记录
        self.dispatcher.on_result(msg)

        # 触发回调
        cb = self._result_callbacks.pop(task_id, None)
        if cb:
            try:
                cb(msg.payload)
            except Exception:
                pass

        if success:
            self._total_tasks_completed += 1

    def _on_coordinate(self, msg: AgentMessage) -> None:
        """处理共识协调消息"""
        if msg.sender_id == self.agent_id:
            return

        phase = msg.payload.get("phase")

        if phase == "prepare":
            # 收到prepare请求，回复投票
            ack_msg = self.consensus.on_prepare(msg)
            ack_msg.target_id = msg.sender_id
            self.message_bus.publish(ack_msg)

        elif phase == "prepare_ack":
            # 收到投票，记录
            proposal_id = msg.payload.get("proposal_id")
            vote = msg.payload.get("vote", False)
            # 从本地记录获取参与者总数
            total = self._proposal_participants.get(proposal_id, 1)
            commit_msg = self.consensus.record_vote(
                proposal_id=proposal_id,
                voter_id=msg.sender_id,
                vote=vote,
                total_participants=total,
            )
            if commit_msg:
                # 广播commit给其他参与者
                self.message_bus.publish(commit_msg)
                # 发起者自己直接触发on_commit（避免自过滤）
                self.consensus.on_commit(commit_msg)

        elif phase == "commit":
            self.consensus.on_commit(msg)

        elif phase == "abort":
            proposal_id = msg.payload.get("proposal_id")
            prop = self.consensus.get_proposal(proposal_id)
            if prop:
                prop.state = ConsensusState.ABORTED

    def _on_state(self, msg: AgentMessage) -> None:
        """处理状态广播消息（更新邻居last_seen）"""
        self.discovery.on_message(msg)
