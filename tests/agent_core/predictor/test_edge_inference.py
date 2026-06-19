"""
边缘推理优化模块测试。

覆盖：单条推理、批量推理、缓存命中、缓存预热、统计。
"""

import numpy as np
import pytest

from agent_core.predictor.edge_inference import EdgeInference


class TestEdgeInference:
    """EdgeInference测试类。"""

    @pytest.fixture
    def engine(self):
        """创建推理引擎实例。"""
        def fn(x):
            return x * 2
        return EdgeInference(fn, batch_size=2)

    def test_predict(self, engine):
        """测试单条推理。"""
        inp = np.array([1.0, 2.0])
        out = engine.predict(inp)
        assert np.allclose(out, np.array([2.0, 4.0]))

    def test_predict_batch(self, engine):
        """测试批量推理。"""
        inputs = [np.array([1.0]), np.array([2.0]), np.array([3.0])]
        outputs = engine.predict_batch(inputs)
        assert len(outputs) == 3
        assert np.allclose(outputs[0], np.array([2.0]))
        assert np.allclose(outputs[1], np.array([4.0]))
        assert np.allclose(outputs[2], np.array([6.0]))

    def test_cache_hit(self, engine):
        """测试缓存命中。"""
        inp = np.array([1.0, 2.0])
        out1 = engine.predict(inp)
        out2 = engine.predict(inp)
        assert np.allclose(out1, out2)
        assert engine.get_cache_stats()["cache_size"] == 1

    def test_warm_cache(self, engine):
        """测试缓存预热。"""
        samples = [np.array([1.0]), np.array([2.0])]
        engine.warm_cache(samples)
        assert engine.get_cache_stats()["cache_size"] == 2
