"""
元学习模块单元测试。

覆盖自适应调整的四类用例。
"""

import unittest

from agent_core.predictor.meta_learner import MetaLearner


class TestMetaLearner(unittest.TestCase):
    """测试元学习器。"""

    def test_record_error(self) -> None:
        """正常值测试：记录误差。"""
        ml = MetaLearner()
        ml.record_error(0.5)
        self.assertEqual(ml._error_history, [0.5])

    def test_record_error_overflow(self) -> None:
        """边界测试：误差历史溢出。"""
        ml = MetaLearner()
        for i in range(30):
            ml.record_error(float(i) / 100.0)
        self.assertLessEqual(len(ml._error_history), 20)

    def test_record_adaptation_rate(self) -> None:
        """正常值测试：记录适应率。"""
        ml = MetaLearner()
        ml.record_adaptation_rate(0.1)
        self.assertEqual(ml._adaptation_rate_history, [0.1])

    def test_record_exploration_rate(self) -> None:
        """正常值测试：记录探索率。"""
        ml = MetaLearner()
        ml.record_exploration_rate(0.3)
        self.assertEqual(ml._exploration_history, [0.3])

    def test_suggest_adaptation_rate_insufficient_data(self) -> None:
        """边界测试：数据不足返回当前值。"""
        ml = MetaLearner()
        result = ml.suggest_adaptation_rate(0.1)
        self.assertEqual(result, 0.1)

    def test_suggest_adaptation_rate_increase(self) -> None:
        """正常值测试：误差上升增大适应率。"""
        ml = MetaLearner()
        for _ in range(10):
            ml.record_error(0.01)
        for _ in range(10):
            ml.record_error(0.05)
        result = ml.suggest_adaptation_rate(0.1)
        self.assertGreater(result, 0.1)

    def test_suggest_adaptation_rate_decrease(self) -> None:
        """正常值测试：误差下降减小适应率。"""
        ml = MetaLearner()
        for _ in range(10):
            ml.record_error(0.05)
        for _ in range(10):
            ml.record_error(0.01)
        result = ml.suggest_adaptation_rate(0.1)
        self.assertLess(result, 0.1)

    def test_suggest_adaptation_rate_stable(self) -> None:
        """边界测试：误差稳定不变。"""
        ml = MetaLearner()
        for _ in range(20):
            ml.record_error(0.05)
        result = ml.suggest_adaptation_rate(0.1)
        self.assertEqual(result, 0.1)

    def test_suggest_exploration_rate_high_variance(self) -> None:
        """正常值测试：高方差增加探索。"""
        ml = MetaLearner()
        result = ml.suggest_exploration_rate(0.3, 0.2)
        self.assertGreater(result, 0.3)

    def test_suggest_exploration_rate_low_variance(self) -> None:
        """正常值测试：低方差减少探索。"""
        ml = MetaLearner()
        result = ml.suggest_exploration_rate(0.3, 0.005)
        self.assertLess(result, 0.3)

    def test_suggest_exploration_rate_medium_variance(self) -> None:
        """边界测试：中等方差不变。"""
        ml = MetaLearner()
        result = ml.suggest_exploration_rate(0.3, 0.05)
        self.assertEqual(result, 0.3)

    def test_compute_environment_variance_insufficient(self) -> None:
        """边界测试：数据不足方差为0。"""
        ml = MetaLearner()
        self.assertEqual(ml.compute_environment_variance(), 0.0)

    def test_compute_environment_variance(self) -> None:
        """正常值测试：计算方差。"""
        ml = MetaLearner()
        ml.record_error(0.1)
        ml.record_error(0.2)
        ml.record_error(0.3)
        var = ml.compute_environment_variance()
        self.assertGreater(var, 0.0)

    def test_get_meta_state_empty(self) -> None:
        """空值测试：空状态。"""
        ml = MetaLearner()
        state = ml.get_meta_state()
        self.assertEqual(state["error_count"], 0)
        self.assertIsNone(state["latest_error"])
        self.assertEqual(state["env_variance"], 0.0)

    def test_get_meta_state_with_data(self) -> None:
        """正常值测试：有数据状态。"""
        ml = MetaLearner()
        ml.record_error(0.5)
        state = ml.get_meta_state()
        self.assertEqual(state["error_count"], 1)
        self.assertEqual(state["latest_error"], 0.5)


if __name__ == "__main__":
    unittest.main()
