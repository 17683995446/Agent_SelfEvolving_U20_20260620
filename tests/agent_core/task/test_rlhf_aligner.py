"""
价值对齐模块测试。

覆盖：偏好对、奖励模型训练、RLHF奖励计算。
"""

import numpy as np
import pytest

from agent_core.task.rlhf_aligner import (
    PreferencePair,
    RewardModel,
    RLHFAligner,
)


class TestPreferencePair:
    """PreferencePair测试类。"""

    def test_getters(self):
        """测试获取器。"""
        pair = PreferencePair("prompt", "chosen", "rejected")
        assert pair.get_prompt() == "prompt"
        assert pair.get_chosen() == "chosen"
        assert pair.get_rejected() == "rejected"


class TestRewardModel:
    """RewardModel测试类。"""

    def test_initial_score(self):
        """测试初始分数。"""
        model = RewardModel(4)
        features = np.array([1.0, 2.0, 3.0, 4.0])
        assert model.score(features) == 0.0

    def test_score_wrong_dim(self):
        """测试维度错误返回0。"""
        model = RewardModel(4)
        assert model.score(np.array([1.0, 2.0])) == 0.0

    def test_update_increases_chosen_score(self):
        """测试更新后优选分数提高。"""
        model = RewardModel(4)
        chosen = np.array([1.0, 0.0, 0.0, 0.0])
        rejected = np.array([0.0, 0.0, 0.0, 0.0])
        before_chosen = model.score(chosen)
        model.update(chosen, rejected, 0.1)
        after_chosen = model.score(chosen)
        assert after_chosen > before_chosen

    def test_update_loss_decreases(self):
        """测试重复更新降低损失。"""
        model = RewardModel(4)
        chosen = np.array([1.0, 0.0, 0.0, 0.0])
        rejected = np.array([0.0, 0.0, 0.0, 0.0])
        loss1 = model.update(chosen, rejected, 0.1)
        loss2 = model.update(chosen, rejected, 0.1)
        assert loss2 <= loss1

    def test_get_weights(self):
        """测试获取权重副本。"""
        model = RewardModel(2)
        weights = model.get_weights()
        weights[0] = 1.0
        assert model.get_weights()[0] == 0.0


class TestRLHFAligner:
    """RLHFAligner测试类。"""

    @pytest.fixture
    def aligner(self):
        """创建对齐器实例。"""
        return RLHFAligner()

    def test_add_preference(self, aligner):
        """测试添加偏好对。"""
        aligner.add_preference("p", "c", "r")
        assert aligner.get_preference_count() == 1

    def test_train_reward_model(self, aligner):
        """测试训练奖励模型。"""
        aligner.add_preference("p1", "good", "bad")
        aligner.add_preference("p2", "better", "worse")

        def extractor(text):
            vec = np.zeros(64)
            for i, ch in enumerate(text[:64]):
                vec[i] = ord(ch) / 255.0
            return vec

        stats = aligner.train_reward_model(extractor, epochs=2)
        assert "loss" in stats
        assert stats["samples"] == 4

    def test_compute_rlhf_reward(self, aligner):
        """测试RLHF奖励计算。"""
        features = np.zeros(64)
        reward = aligner.compute_rlhf_reward(features, 0.0)
        assert isinstance(reward, float)

    def test_clear_preferences(self, aligner):
        """测试清空偏好。"""
        aligner.add_preference("p", "c", "r")
        aligner.clear_preferences()
        assert aligner.get_preference_count() == 0

    def test_get_reward_model(self, aligner):
        """测试获取奖励模型。"""
        model = aligner.get_reward_model()
        assert isinstance(model, RewardModel)
