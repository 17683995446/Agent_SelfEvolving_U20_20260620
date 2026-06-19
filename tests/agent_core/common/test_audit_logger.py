"""
审计日志模块测试。

覆盖：记录事件、查询过滤、完整性验证、导出功能。
"""

import json
import os
import tempfile

import pytest

from agent_core.common.audit_logger import AuditEvent, AuditLogger


class TestAuditLogger:
    """AuditLogger测试类。"""

    @pytest.fixture
    def logger(self):
        """创建审计日志实例。"""
        return AuditLogger()

    def test_log_event(self, logger):
        """测试记录事件。"""
        logger.log("user1", "login", "system", "success")
        events = logger.get_events()
        assert len(events) == 1
        assert events[0].actor == "user1"
        assert events[0].action == "login"
        assert events[0].result == "success"

    def test_log_with_details(self, logger):
        """测试记录带详情的事件。"""
        logger.log("mod", "config_change", "file.py", "success", {"key": "val"})
        events = logger.get_events()
        assert events[0].details == {"key": "val"}

    def test_get_events_filter_actor(self, logger):
        """测试按操作者过滤。"""
        logger.log("a", "act", "res", "ok")
        logger.log("b", "act", "res", "ok")
        events = logger.get_events(actor="a")
        assert len(events) == 1
        assert events[0].actor == "a"

    def test_get_events_filter_action(self, logger):
        """测试按操作类型过滤。"""
        logger.log("a", "login", "res", "ok")
        logger.log("a", "logout", "res", "ok")
        events = logger.get_events(action="login")
        assert len(events) == 1
        assert events[0].action == "login"

    def test_get_events_limit(self, logger):
        """测试返回数量限制。"""
        for i in range(5):
            logger.log("a", "act", "res", "ok")
        events = logger.get_events(limit=3)
        assert len(events) == 3

    def test_integrity_valid(self, logger):
        """测试未篡改时完整性验证通过。"""
        logger.log("a", "act", "res", "ok")
        logger.log("b", "act", "res", "ok")
        assert logger.verify_integrity() is True

    def test_integrity_tampered(self, logger):
        """测试篡改后完整性验证失败。"""
        logger.log("a", "act", "res", "ok")
        logger._events[0] = AuditEvent(
            timestamp=0.0, actor="x", action="x", resource="x", result="x", details={}
        )
        assert logger.verify_integrity() is False

    def test_export_json(self, logger):
        """测试导出JSON。"""
        logger.log("a", "act", "res", "ok")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            path = f.name
        try:
            result = logger.export_json(path)
            assert result is True
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["actor"] == "a"
        finally:
            os.unlink(path)

    def test_hash_chain(self, logger):
        """测试哈希链变化。"""
        initial = logger._last_hash
        logger.log("a", "act", "res", "ok")
        after_first = logger._last_hash
        logger.log("b", "act", "res", "ok")
        after_second = logger._last_hash
        assert initial != after_first
        assert after_first != after_second
