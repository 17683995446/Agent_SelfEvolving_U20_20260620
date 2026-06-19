"""
LSTM预测器模块。

基于门控循环单元的序列预测器，负责捕捉非线性长期依赖。

第一性原理：
- 大脑皮层神经元具有门控机制（类似LSTM的遗忘门）
- 序列记忆通过细胞状态长期保持
- 非线性变换捕捉复杂模式

数学原理：
    f_t = sigmoid(W_f * [h_{t-1}, x_t] + b_f)  # 遗忘门
    i_t = sigmoid(W_i * [h_{t-1}, x_t] + b_i)  # 输入门
    o_t = sigmoid(W_o * [h_{t-1}, x_t] + b_o)  # 输出门
    c_t = f_t * c_{t-1} + i_t * tanh(W_c * [h_{t-1}, x_t] + b_c)
    h_t = o_t * tanh(c_t)
"""

from collections import deque
from typing import Optional

import numpy as np

from agent_core.common.interfaces import IPredictionModel
from agent_core.common.logger import get_logger


class LSTMPredictor(IPredictionModel):
    """
    LSTM预测器实现。

    纯NumPy实现，支持在线学习。
    """

    def __init__(
        self,
        feature_dimensions: int,
        hidden_size: int,
        window_size: int,
        learning_rate: float,
    ) -> None:
        self._feature_dimensions = feature_dimensions
        self._hidden_size = hidden_size
        self._window_size = window_size
        self._learning_rate = learning_rate
        self._history: deque = deque(maxlen=window_size)
        self._error_sum = 0.0
        self._error_count = 0
        self._initialized = False
        self._logger = get_logger()

        # 初始化权重
        self._init_weights()

    def _init_weights(self) -> None:
        input_size = self._feature_dimensions + self._hidden_size
        self._W_f = np.random.randn(input_size, self._hidden_size) * 0.01
        self._b_f = np.zeros((1, self._hidden_size))
        self._W_i = np.random.randn(input_size, self._hidden_size) * 0.01
        self._b_i = np.zeros((1, self._hidden_size))
        self._W_o = np.random.randn(input_size, self._hidden_size) * 0.01
        self._b_o = np.zeros((1, self._hidden_size))
        self._W_c = np.random.randn(input_size, self._hidden_size) * 0.01
        self._b_c = np.zeros((1, self._hidden_size))
        self._W_y = np.random.randn(self._hidden_size, self._feature_dimensions) * 0.01
        self._b_y = np.zeros((1, self._feature_dimensions))

    def _sigmoid(self, x: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))

    def _tanh(self, x: np.ndarray) -> np.ndarray:
        return np.tanh(x)

    def predict(self, state: np.ndarray) -> np.ndarray:
        if len(self._history) < 2:
            return np.asarray(state, dtype=np.float32).copy()
        sequence = np.array(list(self._history))
        h_prev = np.zeros((1, self._hidden_size))
        c_prev = np.zeros((1, self._hidden_size))
        for t in range(len(sequence)):
            x_t = sequence[t].reshape(1, -1)
            h_prev, c_prev = self._forward_step(x_t, h_prev, c_prev)
        prediction = np.dot(h_prev, self._W_y) + self._b_y
        return np.clip(prediction.flatten(), 0.0, 1.0)

    def _forward_step(
        self, x_t: np.ndarray, h_prev: np.ndarray, c_prev: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        concat = np.hstack([h_prev, x_t])
        f_t = self._sigmoid(np.dot(concat, self._W_f) + self._b_f)
        i_t = self._sigmoid(np.dot(concat, self._W_i) + self._b_i)
        o_t = self._sigmoid(np.dot(concat, self._W_o) + self._b_o)
        c_tilde = self._tanh(np.dot(concat, self._W_c) + self._b_c)
        c_t = f_t * c_prev + i_t * c_tilde
        h_t = o_t * self._tanh(c_t)
        return h_t, c_t

    def update(self, state: np.ndarray, actual: np.ndarray) -> None:
        actual_arr = np.asarray(actual, dtype=np.float32)
        self._history.append(actual_arr.copy())
        self._initialized = True
        if len(self._history) >= 2:
            pred = self.predict(actual_arr)
            error = float(np.mean(np.abs(actual_arr - pred)))
            self._error_sum += error
            self._error_count += 1
            # 在线梯度下降更新
            self._online_update(actual_arr, pred)

    def _online_update(self, actual: np.ndarray, pred: np.ndarray) -> None:
        if len(self._history) < 2:
            return
        sequence = np.array(list(self._history))
        dy = (pred - actual).reshape(1, -1)
        h_prev = np.zeros((1, self._hidden_size))
        c_prev = np.zeros((1, self._hidden_size))
        for t in range(len(sequence)):
            x_t = sequence[t].reshape(1, -1)
            h_prev, c_prev = self._forward_step(x_t, h_prev, c_prev)
        dW_y = np.dot(h_prev.T, dy)
        db_y = dy
        self._W_y -= self._learning_rate * dW_y
        self._b_y -= self._learning_rate * db_y

    def get_error(self) -> float:
        if self._error_count == 0:
            return 1.0
        return self._error_sum / self._error_count
