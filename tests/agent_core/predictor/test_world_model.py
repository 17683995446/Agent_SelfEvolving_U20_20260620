"""
世界模型模块测试。

覆盖：状态转移观察、预测、不确定性、多步推演、统计。
"""

import numpy as np
import pytest

from agent_core.predictor.world_model import WorldModel


class TestWorldModel:
    """WorldModel测试类。"""

    @pytest.fixture
    def model(self):
        """创建世界模型实例。"""
        return WorldModel(state_dim=2, action_dim=1)

    def test_predict_unknown_action(self, model):
        """测试未知动作预测状态不变。"""
        state = np.array([1.0, 2.0])
        action = np.array([0.0])
        pred = model.predict(state, action)
        assert np.allclose(pred, state)

    def test_observe_and_predict(self, model):
        """测试观察后预测。"""
        state = np.array([0.0, 0.0])
        action = np.array([1.0])
        next_state = np.array([1.0, 2.0])
        model.observe_transition(state, action, next_state)
        pred = model.predict(state, action)
        assert np.allclose(pred, next_state)

    def test_predict_average(self, model):
        """测试多次观察后取平均。"""
        action = np.array([1.0])
        model.observe_transition(np.array([0.0, 0.0]), action, np.array([1.0, 2.0]))
        model.observe_transition(np.array([0.0, 0.0]), action, np.array([3.0, 4.0]))
        pred = model.predict(np.array([0.0, 0.0]), action)
        assert np.allclose(pred, np.array([2.0, 3.0]))

    def test_predict_uncertainty_high(self, model):
        """测试少样本时不确定性高。"""
        state = np.array([0.0])
        action = np.array([1.0])
        model.observe_transition(state, action, np.array([1.0]))
        _, unc = model.predict_uncertainty(state, action)
        assert unc == 1.0

    def test_predict_uncertainty_low(self, model):
        """测试多样本时不确定性低。"""
        action = np.array([1.0])
        for _ in range(10):
            model.observe_transition(np.array([0.0]), action, np.array([1.0]))
        _, unc = model.predict_uncertainty(np.array([0.0]), action)
        assert unc < 0.1

    def test_rollout(self, model):
        """测试多步推演。"""
        action = np.array([1.0])
        model.observe_transition(np.array([0.0]), action, np.array([1.0]))
        states = model.rollout(np.array([0.0]), [action, action])
        assert len(states) == 3
        assert np.allclose(states[0], np.array([0.0]))
        assert np.allclose(states[1], np.array([1.0]))
        assert np.allclose(states[2], np.array([2.0]))

    def test_get_stats(self, model):
        """测试统计信息。"""
        model.observe_transition(np.array([0.0]), np.array([1.0]), np.array([1.0]))
        stats = model.get_stats()
        assert stats["transitions"] == 1
        assert stats["unique_actions"] == 1
