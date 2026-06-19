"""
自适应学习率模块测试。

覆盖：Adam步骤、RMSprop步骤、余弦退火、SGD衰减、重置。
"""

import numpy as np
import pytest

from agent_core.predictor.adaptive_lr import AdaptiveLearningRate


class TestAdaptiveLearningRate:
    """AdaptiveLearningRate测试类。"""

    def test_adam_step(self):
        """测试Adam优化步骤。"""
        opt = AdaptiveLearningRate(strategy="adam")
        grad = np.array([1.0, 2.0])
        update = opt.step(grad)
        assert update.shape == grad.shape
        assert opt.learning_rate > 0

    def test_rmsprop_step(self):
        """测试RMSprop优化步骤。"""
        opt = AdaptiveLearningRate(strategy="rmsprop")
        grad = np.array([1.0, 2.0])
        update1 = opt.step(grad)
        update2 = opt.step(grad)
        assert np.all(np.abs(update2) <= np.abs(update1))

    def test_cosine_annealing(self):
        """测试余弦退火降低学习率。"""
        opt = AdaptiveLearningRate(strategy="cosine", initial_lr=0.1)
        grad = np.array([1.0])
        lr1 = opt.learning_rate
        for _ in range(500):
            opt.step(grad)
        lr2 = opt.learning_rate
        assert lr2 < lr1

    def test_sgd_decay(self):
        """测试SGD学习率衰减。"""
        opt = AdaptiveLearningRate(strategy="sgd", initial_lr=0.1, decay_rate=0.9)
        grad = np.array([1.0])
        lr1 = opt.learning_rate
        opt.step(grad)
        lr2 = opt.learning_rate
        assert lr2 < lr1

    def test_min_lr_floor(self):
        """测试学习率下限。"""
        opt = AdaptiveLearningRate(strategy="sgd", initial_lr=1.0, decay_rate=0.1, min_lr=0.01)
        grad = np.array([1.0])
        for _ in range(10):
            opt.step(grad)
        assert opt.learning_rate >= 0.01

    def test_reset(self):
        """测试重置状态。"""
        opt = AdaptiveLearningRate(strategy="adam", initial_lr=0.1)
        grad = np.array([1.0])
        opt.step(grad)
        opt.reset()
        assert opt.learning_rate == 0.1
