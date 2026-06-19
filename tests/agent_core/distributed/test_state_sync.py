"""
状态同步优化模块测试。

覆盖：增量计算、增量应用、冲突解决、版本递增。
"""

import pytest

from agent_core.distributed.state_sync import StateSync


class TestStateSync:
    """StateSync测试类。"""

    @pytest.fixture
    def sync(self):
        """创建状态同步器实例。"""
        return StateSync()

    def test_compute_delta_new_keys(self, sync):
        """测试检测新增键。"""
        sync.commit_sync({"a": 1})
        delta = sync.compute_delta({"a": 1, "b": 2})
        assert delta == {"b": 2}

    def test_compute_delta_changed_keys(self, sync):
        """测试检测变更键。"""
        sync.commit_sync({"a": 1})
        delta = sync.compute_delta({"a": 2})
        assert delta == {"a": 2}

    def test_compute_delta_deleted_keys(self, sync):
        """测试检测删除键。"""
        sync.commit_sync({"a": 1, "b": 2})
        delta = sync.compute_delta({"a": 1})
        assert delta == {"b": None}

    def test_compute_delta_no_change(self, sync):
        """测试无变化。"""
        sync.commit_sync({"a": 1})
        delta = sync.compute_delta({"a": 1})
        assert delta == {}

    def test_apply_delta(self, sync):
        """测试应用增量。"""
        sync.commit_sync({"a": 1})
        state = sync.apply_delta({"b": 2})
        assert state == {"a": 1, "b": 2}

    def test_apply_delta_delete(self, sync):
        """测试应用删除增量。"""
        sync.commit_sync({"a": 1, "b": 2})
        state = sync.apply_delta({"b": None})
        assert state == {"a": 1}

    def test_resolve_conflict_last_write(self, sync):
        """测试最后写入优先。"""
        merged = sync.resolve_conflict({"a": 1}, {"a": 2})
        assert merged == {"a": 2}

    def test_resolve_conflict_merge_lists(self, sync):
        """测试列表合并策略。"""
        local = {"tags": ["a", "b"]}
        remote = {"tags": ["b", "c"]}
        merged = sync.resolve_conflict(local, remote, strategy="merge_lists")
        assert set(merged["tags"]) == {"a", "b", "c"}

    def test_version_increment(self, sync):
        """测试版本号递增。"""
        assert sync.version == 0
        sync.commit_sync({"a": 1})
        assert sync.version == 1
