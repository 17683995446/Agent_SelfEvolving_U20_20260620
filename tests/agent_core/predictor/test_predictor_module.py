"""
多层预测模型单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import asyncio
import unittest

import numpy as np

from agent_core.predictor.error_evaluator import PredictionErrorEvaluator
from agent_core.predictor.ensemble import EnsemblePredictor
from agent_core.predictor.high_level_predictor import MeanReversionPredictor
from agent_core.predictor.low_level_predictor import AdaptiveExponentialSmoother
from agent_core.predictor.mid_level_predictor import TrendLinearPredictor
from agent_core.predictor.predictor_module import MultiLayerPredictor


class TestAdaptiveExponentialSmoother(unittest.TestCase):
    """测试自适应指数平滑器。"""

    def test_initial_prediction(self) -> None:
        """正常值入参测试：初始预测返回输入。"""
        smoother = AdaptiveExponentialSmoother(
            feature_dimensions=4,
            alpha_init=0.3,
            alpha_min=0.05,
            alpha_max=0.8,
            adaptation_rate=0.1,
        )
        state = np.array([0.5, 0.3, 0.7, 0.2])
        pred = smoother.predict(state)
        np.testing.assert_array_equal(pred, state)

    def test_update(self) -> None:
        """正常值入参测试：更新后误差降低。"""
        smoother = AdaptiveExponentialSmoother(
            feature_dimensions=4,
            alpha_init=0.3,
            alpha_min=0.05,
            alpha_max=0.8,
            adaptation_rate=0.1,
        )
        state = np.array([0.5, 0.5, 0.5, 0.5])
        smoother.update(state, state)
        error_before = smoother.get_error()
        for _ in range(10):
            smoother.update(state, state)
        error_after = smoother.get_error()
        self.assertLess(error_after, error_before)

    def test_empty_update(self) -> None:
        """空入参测试：空数组更新。"""
        smoother = AdaptiveExponentialSmoother(
            feature_dimensions=0,
            alpha_init=0.3,
            alpha_min=0.05,
            alpha_max=0.8,
            adaptation_rate=0.1,
        )
        state = np.array([])
        smoother.update(state, state)
        self.assertEqual(smoother.get_error(), 1.0)


class TestTrendLinearPredictor(unittest.TestCase):
    """测试趋势线性预测器。"""

    def test_trend_prediction(self) -> None:
        """正常值入参测试：趋势捕捉。"""
        trend = TrendLinearPredictor(
            feature_dimensions=2,
            window_size=10,
            forecast_horizon=5,
        )
        for i in range(10):
            v = np.array([0.1 * i, 0.05 * i])
            trend.update(v, v)
        pred = trend.predict(np.array([0.9, 0.45]))
        self.assertGreater(pred[0], 0.9)
        self.assertGreater(pred[1], 0.45)

    def test_empty_history(self) -> None:
        """空入参测试：无历史数据。"""
        trend = TrendLinearPredictor(
            feature_dimensions=2,
            window_size=10,
            forecast_horizon=5,
        )
        pred = trend.predict(np.array([0.5, 0.5]))
        np.testing.assert_array_equal(pred, np.array([0.5, 0.5]))


class TestMeanReversionPredictor(unittest.TestCase):
    """测试均值回归预测器。"""

    def test_reversion(self) -> None:
        """正常值入参测试：均值回归。"""
        mr = MeanReversionPredictor(
            feature_dimensions=2,
            window_size=20,
            reversion_strength=0.3,
        )
        for i in range(20):
            v = np.array([0.5 + 0.1 * np.sin(i), 0.3])
            mr.update(v, v)
        pred = mr.predict(np.array([0.8, 0.3]))
        self.assertLess(pred[0], 0.8)

    def test_empty_history(self) -> None:
        """空入参测试：无历史数据。"""
        mr = MeanReversionPredictor(
            feature_dimensions=2,
            window_size=20,
            reversion_strength=0.3,
        )
        pred = mr.predict(np.array([0.5, 0.5]))
        np.testing.assert_array_equal(pred, np.array([0.5, 0.5]))


class TestEnsemblePredictor(unittest.TestCase):
    """测试集成预测器。"""

    def test_combine(self) -> None:
        """正常值入参测试：融合结果。"""
        ensemble = EnsemblePredictor(feature_dimensions=4, beta=5.0)
        low = np.array([0.4, 0.4, 0.4, 0.4])
        mid = np.array([0.5, 0.5, 0.5, 0.5])
        high = np.array([0.6, 0.6, 0.6, 0.6])
        result, conf = ensemble.combine(low, mid, high)
        self.assertEqual(len(result), 4)
        self.assertTrue(0.0 <= conf <= 1.0)
        self.assertTrue(np.all(result >= 0.4))
        self.assertTrue(np.all(result <= 0.6))

    def test_empty_errors(self) -> None:
        """边界极值测试：零误差权重。"""
        ensemble = EnsemblePredictor(feature_dimensions=2, beta=5.0)
        ensemble._layer_errors = {"low": 0.0, "mid": 0.0, "high": 0.0}
        result, conf = ensemble.combine(
            np.array([0.5, 0.5]),
            np.array([0.5, 0.5]),
            np.array([0.5, 0.5]),
        )
        self.assertTrue(0.0 <= conf <= 1.0)


class TestPredictionErrorEvaluator(unittest.TestCase):
    """测试误差评估器。"""

    def test_evaluate(self) -> None:
        """正常值入参测试：误差计算。"""
        evaluator = PredictionErrorEvaluator(feature_dimensions=4)
        pred = np.array([0.5, 0.5, 0.5, 0.5])
        actual = np.array([0.6, 0.4, 0.7, 0.3])
        err = evaluator.evaluate(pred, actual)
        self.assertGreater(err.mse, 0.0)
        self.assertGreater(err.mae, 0.0)
        self.assertEqual(len(err.error_vector), 4)

    def test_zero_error(self) -> None:
        """边界极值测试：完全匹配。"""
        evaluator = PredictionErrorEvaluator(feature_dimensions=2)
        pred = np.array([0.5, 0.5])
        actual = np.array([0.5, 0.5])
        err = evaluator.evaluate(pred, actual)
        self.assertEqual(err.mse, 0.0)
        self.assertEqual(err.mae, 0.0)


class TestMultiLayerPredictor(unittest.TestCase):
    """测试多层预测器主类。"""

    def test_initialization(self) -> None:
        """正常值入参测试：初始化。"""
        predictor = MultiLayerPredictor()
        result = asyncio.run(predictor.initialize({"feature_dimensions": 4}))
        self.assertTrue(result)

    def test_predict_all(self) -> None:
        """正常值入参测试：多层预测。"""
        predictor = MultiLayerPredictor()
        asyncio.run(predictor.initialize({"feature_dimensions": 4}))
        state = np.array([0.5, 0.3, 0.7, 0.2])
        result = predictor.predict_all(state)
        self.assertEqual(len(result.ensemble), 4)
        self.assertTrue(0.0 <= result.confidence <= 1.0)

    def test_predict_without_init(self) -> None:
        """非法格式测试：未初始化调用预测。"""
        predictor = MultiLayerPredictor()
        with self.assertRaises(Exception):
            predictor.predict_all(np.array([0.5]))


if __name__ == "__main__":
    unittest.main()
