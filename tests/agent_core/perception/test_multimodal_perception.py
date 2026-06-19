"""
多模态感知模块测试。

覆盖：文本感知、图像感知、音频感知、特征融合、统一入口、缺失模态。
"""

import numpy as np
import pytest

from agent_core.perception.multimodal_perception import MultimodalPerception


class TestMultimodalPerception:
    """MultimodalPerception测试类。"""

    @pytest.fixture
    def perception(self):
        """创建多模态感知器实例。"""
        return MultimodalPerception(feature_dim=64)

    def test_perceive_text_shape(self, perception):
        """测试文本特征维度。"""
        feat = perception.perceive_text("hello")
        assert feat.shape == (64,)
        assert feat.dtype == np.float32

    def test_perceive_text_deterministic(self, perception):
        """测试相同文本产生相同特征。"""
        feat1 = perception.perceive_text("test")
        feat2 = perception.perceive_text("test")
        assert np.allclose(feat1, feat2)

    def test_perceive_image_shape(self, perception):
        """测试图像特征维度。"""
        img = np.random.rand(32, 32, 3)
        feat = perception.perceive_image(img)
        assert feat.shape == (64,)
        assert feat.dtype == np.float32

    def test_perceive_audio_shape(self, perception):
        """测试音频特征维度。"""
        audio = np.random.randn(16000)
        feat = perception.perceive_audio(audio)
        assert feat.shape == (64,)
        assert feat.dtype == np.float32

    def test_fuse_equal_weights(self, perception):
        """测试等权重融合。"""
        features = {
            "a": np.ones(64),
            "b": np.ones(64),
        }
        fused = perception.fuse(features)
        assert fused.shape == (64,)
        assert np.isclose(np.linalg.norm(fused), 1.0)

    def test_fuse_weighted(self, perception):
        """测试加权融合。"""
        features = {
            "a": np.array([1.0] + [0.0] * 63),
            "b": np.array([0.0] + [1.0] * 63),
        }
        weights = {"a": 1.0, "b": 0.0}
        fused = perception.fuse(features, weights)
        expected = features["a"] / np.linalg.norm(features["a"])
        assert np.allclose(fused, expected)

    def test_fuse_empty(self, perception):
        """测试空特征融合返回零。"""
        fused = perception.fuse({})
        assert np.all(fused == 0)

    def test_perceive_all_modalities(self, perception):
        """测试统一入口处理多模态。"""
        result = perception.perceive(
            text="hello",
            image=np.random.rand(16, 16, 3),
            audio=np.random.randn(1000),
        )
        assert set(result["active_modalities"]) == {"text", "image", "audio"}
        assert "fused" in result
        assert result["fused"].shape == (64,)

    def test_perceive_partial(self, perception):
        """测试部分模态输入。"""
        result = perception.perceive(text="only text")
        assert result["active_modalities"] == ["text"]
        assert result["fused"].shape == (64,)
