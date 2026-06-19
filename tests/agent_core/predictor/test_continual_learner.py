"""
持续学习模块测试。

覆盖：知识巩固、EWC损失、EWC梯度、受保护参数、重置。
"""

import numpy as np
import pytest

from agent_core.predictor.continual_learner import ContinualLearner


class TestContinualLearner:
    """ContinualLearner测试类。"""

    @pytest.fixture
    def learner(self):
        """创建持续学习器实例。"""
        return ContinualLearner(lambda_ewc=10.0)

    def test_consolidate(self, learner):
        """测试知识巩固。"""
        params = {"w": np.array([1.0, 2.0])}
        grads = {"w": np.array([0.1, 0.2])}
        learner.consolidate(params, grads)
        assert "w" in learner.get_protected_params()

    def test_ewc_loss_zero_at_optimal(self, learner):
        """测试最优参数处EWC损失为零。"""
        params = {"w": np.array([1.0, 2.0])}
        grads = {"w": np.array([0.1, 0.2])}
        learner.consolidate(params, grads)
        loss = learner.compute_ewc_loss(params)
        assert loss == 0.0

    def test_ewc_loss_increases_with_deviation(self, learner):
        """测试偏离最优时EWC损失增加。"""
        params = {"w": np.array([1.0, 2.0])}
        grads = {"w": np.array([1.0, 1.0])}
        learner.consolidate(params, grads)
        new_params = {"w": np.array([2.0, 3.0])}
        loss = learner.compute_ewc_loss(new_params)
        assert loss > 0.0

    def test_ewc_gradient_direction(self, learner):
        """测试EWC梯度指向旧最优。"""
        params = {"w": np.array([1.0])}
        grads = {"w": np.array([1.0])}
        learner.consolidate(params, grads)
        new_params = {"w": np.array([2.0])}
        ewc_grad = learner.compute_ewc_gradient(new_params)
        assert ewc_grad["w"] > 0

    def test_reset(self, learner):
        """测试重置清除知识。"""
        params = {"w": np.array([1.0])}
        grads = {"w": np.array([0.1])}
        learner.consolidate(params, grads)
        learner.reset()
        assert learner.get_protected_params() == []
