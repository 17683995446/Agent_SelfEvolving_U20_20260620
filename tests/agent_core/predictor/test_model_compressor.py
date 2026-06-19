"""
模型压缩模块测试。

覆盖：剪枝、量化、反量化、压缩比计算。
"""

import numpy as np
import pytest

from agent_core.predictor.model_compressor import ModelCompressor


class TestModelCompressor:
    """ModelCompressor测试类。"""

    @pytest.fixture
    def compressor(self):
        """创建压缩器实例。"""
        return ModelCompressor()

    def test_prune_sparsity(self, compressor):
        """测试剪枝产生稀疏性。"""
        params = [np.array([1.0, 2.0, 3.0, 4.0])]
        pruned = compressor.prune(params, sparsity=0.5)
        zeros = np.sum(pruned[0] == 0)
        assert zeros == 2

    def test_quantize_dequantize(self, compressor):
        """测试量化反量化往返。"""
        params = [np.array([0.0, 1.0, 2.0, 3.0])]
        quantized = compressor.quantize(params, bits=8)
        restored = compressor.dequantize(quantized)
        assert restored[0].shape == params[0].shape
        assert np.allclose(restored[0], params[0], atol=0.1)

    def test_quantize_8bit(self, compressor):
        """测试8位量化值范围。"""
        params = [np.array([0.0, 255.0])]
        quantized = compressor.quantize(params, bits=8)
        assert np.max(quantized[0]["values"]) <= 255
        assert np.min(quantized[0]["values"]) >= 0

    def test_compression_ratio(self, compressor):
        """测试压缩比大于1。"""
        params = [np.ones((100, 100), dtype=np.float64)]
        quantized = compressor.quantize(params, bits=8)
        ratio = compressor.compute_compression_ratio(params, quantized)
        assert ratio > 1.0
