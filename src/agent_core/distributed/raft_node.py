"""
简化Raft共识模块。

实现领导者选举和日志复制的基础功能。

第一性原理：
- 多数派决定系统状态
- 领导者是唯一写入入口
- 日志必须按顺序一致复制
"""

import random
import time
from typing import Any, Dict, List, Optional

from agent_core.common.logger import get_logger


class RaftNode:
    """
    简化Raft节点。

    支持Follower/Candidate/Leader三种角色转换。
    """

    def __init__(self, node_id: str, peers: List[str]) -> None:
        self._id = node_id
        self._peers = peers
        self._term = 0
        self._role = "follower"
        self._voted_for: Optional[str] = None
        self._leader_id: Optional[str] = None
        self._log: List[Dict[str, Any]] = []
        self._commit_index = -1
        self._last_heartbeat = time.monotonic()
        self._election_timeout = random.uniform(0.15, 0.3)
        self._logger = get_logger()

    @property
    def node_id(self) -> str:
        return self._id

    @property
    def role(self) -> str:
        return self._role

    @property
    def term(self) -> int:
        return self._term

    def _reset_election_timer(self) -> None:
        """重置选举定时器。"""
        self._last_heartbeat = time.monotonic()
        self._election_timeout = random.uniform(0.15, 0.3)

    def _should_start_election(self) -> bool:
        """检查是否应该发起选举。"""
        elapsed = time.monotonic() - self._last_heartbeat
        return self._role != "leader" and elapsed > self._election_timeout

    def start_election(self) -> Dict[str, Any]:
        """
        发起选举。

        Returns:
            请求投票消息。
        """
        self._term += 1
        self._role = "candidate"
        self._voted_for = self._id
        self._reset_election_timer()
        self._logger.info(f"[RaftNode {self._id}] Started election for term {self._term}")
        return {
            "type": "request_vote",
            "term": self._term,
            "candidate_id": self._id,
            "last_log_index": len(self._log) - 1,
            "last_log_term": self._log[-1]["term"] if self._log else 0,
        }

    def handle_request_vote(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理投票请求。

        Args:
            msg: 投票请求消息。

        Returns:
            投票响应。
        """
        term = msg.get("term", 0)
        candidate_id = msg.get("candidate_id", "")
        if term > self._term:
            self._term = term
            self._role = "follower"
            self._voted_for = None
        vote_granted = False
        if term == self._term and (
            self._voted_for is None or self._voted_for == candidate_id
        ):
            self._voted_for = candidate_id
            vote_granted = True
            self._reset_election_timer()
        return {"type": "vote_response", "term": self._term, "vote_granted": vote_granted}

    def handle_append_entries(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理日志追加请求。

        Args:
            msg: 日志追加消息。

        Returns:
            响应消息。
        """
        term = msg.get("term", 0)
        leader_id = msg.get("leader_id", "")
        if term >= self._term:
            self._term = term
            self._role = "follower"
            self._leader_id = leader_id
            self._reset_election_timer()
        entries = msg.get("entries", [])
        for entry in entries:
            self._log.append(entry)
        leader_commit = msg.get("leader_commit", -1)
        if leader_commit > self._commit_index:
            self._commit_index = min(leader_commit, len(self._log) - 1)
        return {"type": "append_response", "term": self._term, "success": True}

    def append_entries(self, entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        领导者追加日志条目。

        Args:
            entries: 日志条目列表。

        Returns:
            要发送给追随者的消息列表。
        """
        if self._role != "leader":
            return []
        for entry in entries:
            entry["term"] = self._term
            self._log.append(entry)
        messages = []
        for peer in self._peers:
            messages.append({
                "type": "append_entries",
                "term": self._term,
                "leader_id": self._id,
                "leader_commit": self._commit_index,
                "entries": entries,
                "target": peer,
            })
        return messages

    def become_leader(self) -> None:
        """当选为领导者。"""
        self._role = "leader"
        self._leader_id = self._id
        self._logger.info(f"[RaftNode {self._id}] Became leader for term {self._term}")

    def tick(self) -> Optional[Dict[str, Any]]:
        """
        时间滴答，检查是否需要发起选举。

        Returns:
            需要发起选举时返回投票请求消息。
        """
        if self._should_start_election():
            return self.start_election()
        return None

    def get_committed_log(self) -> List[Dict[str, Any]]:
        """获取已提交的日志。"""
        return self._log[: self._commit_index + 1]
