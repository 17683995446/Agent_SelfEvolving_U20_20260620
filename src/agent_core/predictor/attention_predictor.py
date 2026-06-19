"""
注意力预测器模块。

基于自注意力机制的序列预测器，负责捕捉全局依赖关系。

第一性原理：
- 大脑注意机制选择性聚焦重要信息
- 自注意力计算序列中所有位置间的相关性
- 多头注意力并行捕捉不同子空间模式

数学原理：
    Q = X * W_q, K = X * W_k, V = X * W_v
    Attention(Q, K, V) = softmax(Q * K^T / sqrt(d_k)) * V
"""

from collections import deque

import numpy as np

from agent_core.common.interfaces import IPredictionModel
from agent_core.common.logger import get_logger


class AttentionPredictor(IPredictionModel):
    """
    自注意力预测器实现。

    纯NumPy实现，支持在线学习。
    """

    def __init__(
        self,
        feature_dimensions: int,
        head_size: int,
        window_size: int,
        learning_rate: float,
    ) -> None:
        self._feature_dimensions = feature_dimensions
        self._head_size = head_size
        self._window_size = window_size
        self._learning_rate = learning_rate
        self._history: deque = deque(maxlen=window_size)
        self._error_sum = 0.0
        self._error_count = 0
        self._initialized = False
        self._logger = get_logger()
        self._init_weights()

    def _init_weights(self) -> None:
        self._W_q = np.random.randn(
            self._feature_dimensions, self._head_size
        ) * 0.01
        self._W_k = np.random.randn(
            self._feature_dimensions, self._head_size
        ) * 0.01
        self._W_v = np.random.randn(
            self._feature_dimensions, self._feature_dimensions
        ) * 0.01
        self._W_o = np.random.randn(
            self._feature_dimensions, self._feature_dimensions
        ) * 0.01

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        exp_x = np.exp(x - np.max(x, axis=-1, keepdims=True))
        return exp_x / np.sum(exp_x, axis=-1, keepdims=True)

    def predict(self, state: np.ndarray) -> np.ndarray:
        if len(self._history) < 2:
            return np.asarray(state, dtype=np.float32).copy()
        sequence = np.array(list(self._history))
        attention_output = self._self_attention(sequence)
        prediction = np.dot(attention_output[-1], self._W_o)
        return np.clip(prediction, 0.0, 1.0)

    def _self_attention(self, sequence: np.ndarray) -> np.ndarray:
        Q = np.dot(sequence, self._W_q)
        K = np.dot(sequence, self._W_k)
        V = np.dot(sequence, self._W_v)
        scores = np.dot(Q, K.T) / np.sqrt(self._head_size)
        attention_weights = self._softmax(scores)
        output = np.dot(attention_weights, V)
        return output

    def update(self, state: np.ndarray, actual: np.ndarray) -> None:
        actual_arr = np.asarray(actual, dtype=np.float32)
        self._history.append(actual_arr.copy())
        self._initialized = True
        if len(self._history) >= 2:
            pred = self.predict(actual_arr)
            error = float(np.mean(np.abs(actual_arr - pred)))
            self._error_sum += error
            self._error_count += 1
            self._online_update(actual_arr, pred)

    def _online_update(self, actual: np.ndarray, pred: np.ndarray) -> None:
        if len(self._history) < 2:
            return
        dy = (pred - actual).reshape(1, -1)
        sequence = np.array(list(self._history))
        attention_output = self._self_attention(sequence)
        h_last = attention_output[-1].reshape(1, -1)
        dW_o = np.dot(h_last.T, dy)
        self._W_o -= self._learning_rate * dW_o

    def get_error(self) -> float:
        if self._error_count == 0:
            return 1.0
        return self._error_sum / self._error_count
