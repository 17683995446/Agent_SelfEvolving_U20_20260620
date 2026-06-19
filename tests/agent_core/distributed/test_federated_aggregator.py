"""
联邦学习聚合模块测试。

覆盖：单节点聚合、多节点加权聚合、异常检测、清空。
"""

import numpy as np
import pytest

from agent_core.distributed.federated_aggregator import FederatedAggregator


class TestFederatedAggregator:
    """FederatedAggregator测试类。"""

    @pytest.fixture
    def aggregator(self):
        """创建聚合器实例。"""
        return FederatedAggregator()

    def test_aggregate_single_node(self, aggregator):
        """测试单节点聚合返回原参数。"""
        params = [np.array([1.0, 2.0])]
        aggregator.submit_update("n1", params, weight=1.0)
        result = aggregator.aggregate()
        assert result is not None
        assert np.allclose(result[0], np.array([1.0, 2.0]))

    def test_aggregate_multiple_nodes(self, aggregator):
        """测试多节点加权平均。"""
        aggregator.submit_update("n1", [np.array([0.0, 0.0])], weight=1.0)
        aggregator.submit_update("n2", [np.array([2.0, 4.0])], weight=1.0)
        result = aggregator.aggregate()
        assert result is not None
        assert np.allclose(result[0], np.array([1.0, 2.0]))

    def test_aggregate_weighted(self, aggregator):
        """测试不同权重聚合。"""
        aggregator.submit_update("n1", [np.array([0.0])], weight=1.0)
        aggregator.submit_update("n2", [np.array([3.0])], weight=2.0)
        result = aggregator.aggregate()
        assert result is not None
        assert np.allclose(result[0], np.array([2.0]))

    def test_aggregate_empty(self, aggregator):
        """测试空聚合返回None。"""
        result = aggregator.aggregate()
        assert result is None

    def test_clear(self, aggregator):
        """测试清空。"""
        aggregator.submit_update("n1", [np.array([1.0])])
        aggregator.clear()
        assert aggregator.aggregate() is None

    def test_detect_outliers(self, aggregator):
        """测试异常节点检测。"""
        aggregator.submit_update("n1", [np.array([1.0, 1.0])])
        aggregator.submit_update("n2", [np.array([1.1, 1.1])])
        aggregator.submit_update("n3", [np.array([1.2, 1.2])])
        aggregator.submit_update("n4", [np.array([10.0, 10.0])])
        outliers = aggregator.detect_outliers(threshold=1.5)
        assert "n4" in outliers

    def test_detect_outliers_insufficient(self, aggregator):
        """测试节点不足时不检测。"""
        aggregator.submit_update("n1", [np.array([1.0])])
        outliers = aggregator.detect_outliers()
        assert outliers == []
