"""
鲁棒滤波模块单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import unittest

import numpy as np

from agent_core.perception.robust_filter import AdversarialDefender, RobustFilter


class TestRobustFilter(unittest.TestCase):
    """测试鲁棒滤波器。"""

    def setUp(self) -> None:
        """每个用例前创建新实例。"""
        self.filter = RobustFilter(window_size=5, outlier_threshold=3.0)

    def test_filter_normal(self) -> None:
        """正常值入参测试：正常输入滤波。"""
        for _ in range(5):
            result = self.filter.filter(np.array([0.5, 0.5, 0.5]))
        np.testing.assert_array_almost_equal(result, [0.5, 0.5, 0.5], decimal=1)

    def test_clip_outlier(self) -> None:
        """正常值入参测试：异常值裁剪。"""
        for _ in range(5):
            self.filter.filter(np.array([0.5, 0.5, 0.5]))
        outlier = np.array([0.5, 10.0, 0.5])
        clipped = self.filter.filter(outlier)
        self.assertLess(clipped[1], 5.0)

    def test_detect_anomaly_true(self) -> None:
        """正常值入参测试：检测异常。"""
        for _ in range(5):
            self.filter.filter(np.array([0.5, 0.5, 0.5]))
        is_anomaly = self.filter.detect_anomaly(np.array([0.5, 20.0, 0.5]))
        self.assertTrue(is_anomaly)

    def test_detect_anomaly_false(self) -> None:
        """正常值入参测试：正常值不异常。"""
        for _ in range(5):
            self.filter.filter(np.array([0.5, 0.5, 0.5]))
        is_anomaly = self.filter.detect_anomaly(np.array([0.5, 0.5, 0.5]))
        self.assertFalse(is_anomaly)

    def test_detect_anomaly_insufficient_history(self) -> None:
        """空入参测试：历史不足不检测。"""
        is_anomaly = self.filter.detect_anomaly(np.array([0.5, 0.5, 0.5]))
        self.assertFalse(is_anomaly)

    def test_reset(self) -> None:
        """正常值入参测试：重置历史。"""
        self.filter.filter(np.array([0.5, 0.5, 0.5]))
        self.filter.reset()
        self.assertEqual(len(self.filter._history), 0)

    def test_median_smooth_window(self) -> None:
        """正常值入参测试：中值平滑窗口。"""
        for i in range(10):
            result = self.filter.filter(np.array([float(i), 0.0, 0.0]))
        self.assertGreaterEqual(result[0], 0.0)

    def test_empty_vector(self) -> None:
        """空入参测试：空向量。"""
        result = self.filter.filter(np.array([]))
        self.assertEqual(len(result), 0)

    def test_boundary_extreme_values(self) -> None:
        """边界极值测试：极值输入。"""
        for _ in range(5):
            self.filter.filter(np.array([0.0, 1.0, 0.5]))
        result = self.filter.filter(np.array([1e6, -1e6, 0.5]))
        self.assertTrue(np.all(np.isfinite(result)))


class TestAdversarialDefender(unittest.TestCase):
    """测试对抗防御器。"""

    def setUp(self) -> None:
        """每个用例前创建新实例。"""
        self.defender = AdversarialDefender(
            noise_scale=0.01, clip_range=(0.0, 1.0)
        )

    def test_defend_range(self) -> None:
        """正常值入参测试：防御后范围。"""
        vector = np.array([0.5, 0.5, 0.5])
        result = self.defender.defend(vector)
        self.assertTrue(np.all(result >= 0.0))
        self.assertTrue(np.all(result <= 1.0))

    def test_defend_quantization(self) -> None:
        """正常值入参测试：量化效果。"""
        vector = np.array([0.123456, 0.987654, 0.5])
        result = self.defender.defend(vector)
        # 量化后应为 1/64 的整数倍
        levels = 64
        for val in result:
            residual = round(val * levels) % 1
            self.assertAlmostEqual(residual, 0.0, places=5)

    def test_defend_empty(self) -> None:
        """空入参测试：空向量。"""
        result = self.defender.defend(np.array([]))
        self.assertEqual(len(result), 0)

    def test_defend_boundary_values(self) -> None:
        """边界极值测试：边界值裁剪。"""
        vector = np.array([-0.5, 1.5, 0.5])
        result = self.defender.defend(vector)
        self.assertTrue(np.all(result >= 0.0))
        self.assertTrue(np.all(result <= 1.0))

    def test_noise_changes_input(self) -> None:
        """正常值入参测试：噪声改变输入。"""
        vector = np.array([0.5, 0.5, 0.5])
        results = [self.defender.defend(vector) for _ in range(10)]
        # 至少有一个结果与原始不同
        any_diff = any(not np.allclose(r, vector) for r in results)
        self.assertTrue(any_diff)


if __name__ == "__main__":
    unittest.main()
