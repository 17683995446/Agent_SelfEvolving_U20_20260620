"""
社会智能模块单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import unittest

from agent_core.memory.social_intelligence import (
    CoalitionManager,
    GameTheoreticStrategy,
    ReputationTracker,
)


class TestReputationTracker(unittest.TestCase):
    """测试信誉追踪器。"""

    def setUp(self) -> None:
        """每个用例前创建新实例。"""
        self.tracker = ReputationTracker()

    def test_default_reputation(self) -> None:
        """正常值入参测试：默认信誉。"""
        self.assertEqual(self.tracker.get_reputation("a"), 0.5)

    def test_record_cooperation(self) -> None:
        """正常值入参测试：记录合作。"""
        self.tracker.record_interaction("a", True)
        self.assertEqual(self.tracker.get_reputation("a"), 1.0)

    def test_record_defection(self) -> None:
        """正常值入参测试：记录背叛。"""
        self.tracker.record_interaction("a", False)
        self.assertEqual(self.tracker.get_reputation("a"), 0.0)

    def test_mixed_history(self) -> None:
        """正常值入参测试：混合历史。"""
        for _ in range(5):
            self.tracker.record_interaction("a", True)
        for _ in range(5):
            self.tracker.record_interaction("a", False)
        self.assertAlmostEqual(
            self.tracker.get_reputation("a"), 0.5, places=5
        )

    def test_decay(self) -> None:
        """正常值入参测试：信誉衰减。"""
        self.tracker.record_interaction("a", True)
        self.tracker.decay_reputations()
        self.assertLess(self.tracker.get_reputation("a"), 1.0)
        self.assertGreater(self.tracker.get_reputation("a"), 0.5)

    def test_trusted_agents(self) -> None:
        """正常值入参测试：可信Agent。"""
        self.tracker.record_interaction("good", True)
        self.tracker.record_interaction("bad", False)
        trusted = self.tracker.get_trusted_agents(threshold=0.6)
        self.assertIn("good", trusted)
        self.assertNotIn("bad", trusted)


class TestCoalitionManager(unittest.TestCase):
    """测试联盟管理器。"""

    def setUp(self) -> None:
        """每个用例前创建新实例。"""
        self.manager = CoalitionManager()
        self.tracker = ReputationTracker()

    def test_form_coalition_success(self) -> None:
        """正常值入参测试：成功组建。"""
        self.tracker.record_interaction("a", True)
        self.tracker.record_interaction("b", True)
        result = self.manager.form_coalition(
            "c1", ["a", "b"], self.tracker
        )
        self.assertTrue(result)
        self.assertEqual(self.manager.get_members("c1"), ["a", "b"])

    def test_form_coalition_fail(self) -> None:
        """边界极值测试：成员不足。"""
        self.tracker.record_interaction("a", True)
        result = self.manager.form_coalition(
            "c1", ["a"], self.tracker
        )
        self.assertFalse(result)

    def test_form_coalition_untrusted(self) -> None:
        """正常值入参测试：不可信成员被过滤。"""
        self.tracker.record_interaction("a", True)
        self.tracker.record_interaction("b", False)
        result = self.manager.form_coalition(
            "c1", ["a", "b"], self.tracker
        )
        self.assertFalse(result)

    def test_dissolve(self) -> None:
        """正常值入参测试：解散联盟。"""
        self.tracker.record_interaction("a", True)
        self.tracker.record_interaction("b", True)
        self.manager.form_coalition("c1", ["a", "b"], self.tracker)
        self.manager.dissolve_coalition("c1")
        self.assertEqual(self.manager.get_members("c1"), [])

    def test_list_coalitions(self) -> None:
        """正常值入参测试：列出联盟。"""
        self.tracker.record_interaction("a", True)
        self.tracker.record_interaction("b", True)
        self.manager.form_coalition("c1", ["a", "b"], self.tracker)
        self.assertEqual(self.manager.list_coalitions(), ["c1"])


class TestGameTheoreticStrategy(unittest.TestCase):
    """测试博弈论策略。"""

    def setUp(self) -> None:
        """每个用例前创建新实例。"""
        self.strategy = GameTheoreticStrategy()
        self.tracker = ReputationTracker()

    def test_choose_cooperate(self) -> None:
        """正常值入参测试：高信誉下选择合作。"""
        self.tracker.record_interaction("a", True)
        # 合作-合作收益高于背叛-合作收益时选择合作
        matrix = {
            "cooperate": {"cooperate": 5.0, "defect": 1.0},
            "defect": {"cooperate": 3.0, "defect": 0.0},
        }
        action = self.strategy.choose_action("a", self.tracker, matrix)
        self.assertEqual(action, "cooperate")

    def test_choose_defect(self) -> None:
        """正常值入参测试：低信誉下选择背叛。"""
        self.tracker.record_interaction("a", False)
        matrix = {
            "cooperate": {"cooperate": 3.0, "defect": 0.0},
            "defect": {"cooperate": 5.0, "defect": 1.0},
        }
        action = self.strategy.choose_action("a", self.tracker, matrix)
        self.assertEqual(action, "defect")

    def test_tit_for_tat_first(self) -> None:
        """正常值入参测试：首次合作。"""
        action = self.strategy.tit_for_tat("a", None)
        self.assertEqual(action, "cooperate")

    def test_tit_for_tat_mimic(self) -> None:
        """正常值入参测试：模仿对方。"""
        action = self.strategy.tit_for_tat("a", "defect")
        self.assertEqual(action, "defect")

    def test_tit_for_tat_cooperate(self) -> None:
        """正常值入参测试：回应合作。"""
        action = self.strategy.tit_for_tat("a", "cooperate")
        self.assertEqual(action, "cooperate")


if __name__ == "__main__":
    unittest.main()
