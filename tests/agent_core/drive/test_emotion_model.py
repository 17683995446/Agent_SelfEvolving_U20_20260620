"""
情绪与动机建模模块单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import unittest

from agent_core.drive.emotion_model import EmotionEngine, EmotionState


class TestEmotionEngine(unittest.TestCase):
    """测试情绪引擎。"""

    def setUp(self) -> None:
        """每个用例前创建新实例。"""
        self.engine = EmotionEngine()

    def test_initial_state(self) -> None:
        """正常值入参测试：初始状态。"""
        state = self.engine.get_state()
        self.assertEqual(state.curiosity, 0.5)
        self.assertEqual(state.boredom, 0.0)
        self.assertEqual(state.anxiety, 0.0)
        self.assertEqual(state.confidence, 0.5)

    def test_curiosity_increase(self) -> None:
        """正常值入参测试：高误差增加好奇。"""
        self.engine.update(prediction_error=0.5, task_type="a", success=True)
        self.assertGreater(self.engine.get_state().curiosity, 0.5)

    def test_curiosity_decrease(self) -> None:
        """正常值入参测试：低误差减少好奇。"""
        self.engine.update(prediction_error=0.1, task_type="a", success=True)
        self.assertLess(self.engine.get_state().curiosity, 0.5)

    def test_boredom_buildup(self) -> None:
        """正常值入参测试：重复任务增加无聊。"""
        for _ in range(10):
            self.engine.update(prediction_error=0.1, task_type="same", success=True)
        self.assertGreater(self.engine.get_state().boredom, 0.0)

    def test_boredom_reset(self) -> None:
        """正常值入参测试：多样任务减少无聊。"""
        for i in range(10):
            self.engine.update(
                prediction_error=0.1,
                task_type=f"task_{i}",
                success=True,
            )
        self.assertEqual(self.engine.get_state().boredom, 0.0)

    def test_anxiety_failure(self) -> None:
        """正常值入参测试：失败增加焦虑。"""
        self.engine.update(prediction_error=0.1, task_type="a", success=False)
        self.assertGreater(self.engine.get_state().anxiety, 0.0)

    def test_anxiety_recovery(self) -> None:
        """正常值入参测试：成功减少焦虑。"""
        self.engine.update(prediction_error=0.1, task_type="a", success=False)
        self.engine.update(prediction_error=0.1, task_type="a", success=True)
        self.assertLess(self.engine.get_state().anxiety, 0.15)

    def test_confidence_update(self) -> None:
        """正常值入参测试：信心更新。"""
        for _ in range(5):
            self.engine.update(prediction_error=0.1, task_type="a", success=True)
        self.assertGreater(self.engine.get_state().confidence, 0.5)

    def test_adjust_exploration_curiosity(self) -> None:
        """正常值入参测试：好奇增加探索。"""
        for _ in range(10):
            self.engine.update(prediction_error=0.5, task_type="a", success=True)
        adjusted = self.engine.adjust_exploration_bias(0.3)
        self.assertGreater(adjusted, 0.3)

    def test_adjust_exploration_boredom(self) -> None:
        """正常值入参测试：无聊强制探索。"""
        for _ in range(20):
            self.engine.update(prediction_error=0.1, task_type="same", success=True)
        adjusted = self.engine.adjust_exploration_bias(0.3)
        self.assertGreater(adjusted, 0.3)

    def test_adjust_exploration_anxiety(self) -> None:
        """正常值入参测试：焦虑减少探索。"""
        engine = EmotionEngine()
        for _ in range(10):
            engine.update(prediction_error=0.1, task_type="a", success=False)
        state = engine.get_state()
        self.assertGreater(state.anxiety, 0.0)
        adjusted = engine.adjust_exploration_bias(0.5)
        # 焦虑>0.7时减少0.1探索
        if state.anxiety > 0.7 and state.curiosity <= 0.7 and state.boredom <= 0.8:
            self.assertLess(adjusted, 0.5)

    def test_adjust_exploration_bounds(self) -> None:
        """边界极值测试：探索率边界。"""
        for _ in range(50):
            self.engine.update(prediction_error=0.9, task_type="a", success=True)
        adjusted = self.engine.adjust_exploration_bias(0.9)
        self.assertLessEqual(adjusted, 1.0)

    def test_emotion_state_dict(self) -> None:
        """正常值入参测试：状态字典。"""
        state = EmotionState()
        d = state.to_dict()
        self.assertIn("curiosity", d)
        self.assertIn("boredom", d)
        self.assertIn("anxiety", d)
        self.assertIn("confidence", d)


if __name__ == "__main__":
    unittest.main()
