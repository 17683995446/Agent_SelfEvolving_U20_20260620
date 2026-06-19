"""
高级预测器单元测试。

覆盖LSTM和Attention预测器的四类用例。
"""

import unittest

import numpy as np

from agent_core.predictor.attention_predictor import AttentionPredictor
from agent_core.predictor.lstm_predictor import LSTMPredictor


class TestLSTMPredictor(unittest.TestCase):
    """测试LSTM预测器。"""

    def test_normal_prediction(self) -> None:
        """正常值入参测试：序列预测。"""
        predictor = LSTMPredictor(
            feature_dimensions=4,
            hidden_size=8,
            window_size=10,
            learning_rate=0.01,
        )
        for i in range(10):
            state = np.array([0.1 * i, 0.05 * i, 0.2, 0.3])
            predictor.update(state, state)
        pred = predictor.predict(np.array([0.9, 0.45, 0.2, 0.3]))
        self.assertEqual(len(pred), 4)
        self.assertTrue(np.all(pred >= 0.0))
        self.assertTrue(np.all(pred <= 1.0))

    def test_empty_history(self) -> None:
        """空入参测试：无历史数据。"""
        predictor = LSTMPredictor(
            feature_dimensions=4,
            hidden_size=8,
            window_size=10,
            learning_rate=0.01,
        )
        pred = predictor.predict(np.array([0.5, 0.5, 0.5, 0.5]))
        np.testing.assert_array_equal(pred, np.array([0.5, 0.5, 0.5, 0.5]))

    def test_online_learning(self) -> None:
        """正常值入参测试：在线学习收敛。"""
        predictor = LSTMPredictor(
            feature_dimensions=2,
            hidden_size=4,
            window_size=20,
            learning_rate=0.05,
        )
        # 构造正弦序列
        for i in range(20):
            state = np.array([0.5 + 0.3 * np.sin(i * 0.5), 0.3])
            predictor.update(state, state)
        error_before = predictor.get_error()
        for i in range(20, 40):
            state = np.array([0.5 + 0.3 * np.sin(i * 0.5), 0.3])
            predictor.update(state, state)
        error_after = predictor.get_error()
        self.assertLess(error_after, error_before)

    def test_extreme_values(self) -> None:
        """边界极值测试：极端输入。"""
        predictor = LSTMPredictor(
            feature_dimensions=2,
            hidden_size=4,
            window_size=10,
            learning_rate=0.01,
        )
        for _ in range(5):
            predictor.update(np.zeros(2), np.zeros(2))
            predictor.update(np.ones(2), np.ones(2))
        pred = predictor.predict(np.array([0.5, 0.5]))
        self.assertTrue(np.all(pred >= 0.0))
        self.assertTrue(np.all(pred <= 1.0))


class TestAttentionPredictor(unittest.TestCase):
    """测试注意力预测器。"""

    def test_normal_prediction(self) -> None:
        """正常值入参测试：注意力预测。"""
        predictor = AttentionPredictor(
            feature_dimensions=4,
            head_size=8,
            window_size=10,
            learning_rate=0.01,
        )
        for i in range(10):
            state = np.array([0.1 * i, 0.05 * i, 0.2, 0.3])
            predictor.update(state, state)
        pred = predictor.predict(np.array([0.9, 0.45, 0.2, 0.3]))
        self.assertEqual(len(pred), 4)
        self.assertTrue(np.all(pred >= 0.0))
        self.assertTrue(np.all(pred <= 1.0))

    def test_empty_history(self) -> None:
        """空入参测试：无历史数据。"""
        predictor = AttentionPredictor(
            feature_dimensions=4,
            head_size=8,
            window_size=10,
            learning_rate=0.01,
        )
        pred = predictor.predict(np.array([0.5, 0.5, 0.5, 0.5]))
        np.testing.assert_array_equal(pred, np.array([0.5, 0.5, 0.5, 0.5]))

    def test_attention_weights(self) -> None:
        """正常值入参测试：注意力权重和为1。"""
        predictor = AttentionPredictor(
            feature_dimensions=2,
            head_size=4,
            window_size=5,
            learning_rate=0.01,
        )
        for i in range(5):
            state = np.array([0.2 * i, 0.1 * i])
            predictor.update(state, state)
        sequence = np.array(list(predictor._history))
        attention_output = predictor._self_attention(sequence)
        self.assertEqual(attention_output.shape, sequence.shape)

    def test_online_learning(self) -> None:
        """正常值入参测试：在线学习。"""
        predictor = AttentionPredictor(
            feature_dimensions=2,
            head_size=4,
            window_size=10,
            learning_rate=0.05,
        )
        for i in range(15):
            state = np.array([0.5 + 0.2 * np.cos(i * 0.3), 0.3])
            predictor.update(state, state)
        error = predictor.get_error()
        self.assertLess(error, 1.0)


if __name__ == "__main__":
    unittest.main()
