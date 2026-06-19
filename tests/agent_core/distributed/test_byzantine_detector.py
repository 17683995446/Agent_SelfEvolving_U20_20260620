"""
拜占庭容错模块测试。

覆盖：投票偏离检测、行为异常检测、清除历史、无数据时。
"""

import pytest

from agent_core.distributed.byzantine_detector import ByzantineDetector


class TestByzantineDetector:
    """ByzantineDetector测试类。"""

    @pytest.fixture
    def detector(self):
        """创建检测器实例。"""
        return ByzantineDetector(threshold_ratio=0.5)

    def test_no_malicious_empty(self, detector):
        """测试无数据时无恶意节点。"""
        result = detector.detect_malicious(["n1", "n2"])
        assert result == []

    def test_detect_vote_deviation(self, detector):
        """测试投票偏离检测。"""
        for _ in range(5):
            detector.record_vote("n1", "A")
            detector.record_vote("n2", "A")
            detector.record_vote("n3", "B")
        result = detector.detect_malicious(["n1", "n2", "n3"])
        assert "n3" in result
        assert "n1" not in result
        assert "n2" not in result

    def test_detect_behavior_timeout(self, detector):
        """测试超时行为检测。"""
        detector.record_behavior("n1", "timeout_count", 10)
        result = detector.detect_malicious(["n1"])
        assert "n1" in result

    def test_detect_behavior_invalid(self, detector):
        """测试无效消息检测。"""
        detector.record_behavior("n1", "invalid_message_count", 5)
        result = detector.detect_malicious(["n1"])
        assert "n1" in result

    def test_clear_history_single(self, detector):
        """测试清除单个节点历史。"""
        detector.record_vote("n1", "A")
        detector.clear_history("n1")
        assert detector.detect_malicious(["n1"]) == []

    def test_clear_history_all(self, detector):
        """测试清除全部历史。"""
        detector.record_vote("n1", "A")
        detector.record_behavior("n2", "timeout_count", 10)
        detector.clear_history()
        assert detector.detect_malicious(["n1", "n2"]) == []
