"""
简化Raft节点测试。

覆盖：初始状态、选举发起、投票处理、日志追加、角色转换。
"""

import time

import pytest

from agent_core.distributed.raft_node import RaftNode


class TestRaftNode:
    """RaftNode测试类。"""

    @pytest.fixture
    def node(self):
        """创建Raft节点实例。"""
        return RaftNode("n1", ["n2", "n3"])

    def test_initial_state(self, node):
        """测试初始状态为follower。"""
        assert node.role == "follower"
        assert node.term == 0

    def test_start_election(self, node):
        """测试发起选举。"""
        msg = node.start_election()
        assert node.role == "candidate"
        assert node.term == 1
        assert msg["type"] == "request_vote"
        assert msg["candidate_id"] == "n1"

    def test_handle_request_vote_higher_term(self, node):
        """测试处理更高任期的投票请求。"""
        msg = {"term": 2, "candidate_id": "n2"}
        resp = node.handle_request_vote(msg)
        assert resp["vote_granted"] is True
        assert node.term == 2

    def test_handle_request_vote_already_voted(self, node):
        """测试已投票后拒绝其他候选者。"""
        node.start_election()
        msg = {"term": 1, "candidate_id": "n2"}
        resp = node.handle_request_vote(msg)
        assert resp["vote_granted"] is False

    def test_become_leader(self, node):
        """测试当选为leader。"""
        node.become_leader()
        assert node.role == "leader"

    def test_append_entries_as_leader(self, node):
        """测试leader追加日志。"""
        node.start_election()
        node.become_leader()
        msgs = node.append_entries([{"cmd": "set x=1"}])
        assert len(msgs) == 2
        assert node.get_committed_log() == []

    def test_append_entries_as_follower(self, node):
        """测试follower不能追加日志。"""
        msgs = node.append_entries([{"cmd": "set x=1"}])
        assert msgs == []

    def test_handle_append_entries(self, node):
        """测试处理日志追加。"""
        msg = {
            "term": 1,
            "leader_id": "n2",
            "entries": [{"cmd": "set x=1"}],
            "leader_commit": 0,
        }
        resp = node.handle_append_entries(msg)
        assert resp["success"] is True
        assert node.role == "follower"

    def test_tick_no_election(self, node):
        """测试心跳正常时不发起选举。"""
        result = node.tick()
        assert result is None

    def test_tick_triggers_election(self, node):
        """测试超时后发起选举。"""
        node._last_heartbeat = time.monotonic() - 1.0
        result = node.tick()
        assert result is not None
        assert result["type"] == "request_vote"
