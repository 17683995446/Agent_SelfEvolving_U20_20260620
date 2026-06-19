"""
配置管理器单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import time
import unittest

from agent_core.common.config_manager import ConfigManager, get_config_manager


class TestConfigManager(unittest.TestCase):
    """测试配置管理器。"""

    def setUp(self) -> None:
        """每个用例前重置单例。"""
        ConfigManager._instance = None
        self.manager = ConfigManager()

    def test_singleton(self) -> None:
        """正常值入参测试：单例模式。"""
        another = ConfigManager()
        self.assertIs(self.manager, another)

    def test_load_and_get(self) -> None:
        """正常值入参测试：加载与获取。"""
        self.manager.load({"exploration_rate": 0.3, "epsilon": 0.2})
        self.assertEqual(self.manager.get("exploration_rate"), 0.3)
        self.assertEqual(self.manager.get("epsilon"), 0.2)

    def test_get_default(self) -> None:
        """正常值入参测试：默认值。"""
        self.assertIsNone(self.manager.get("missing"))
        self.assertEqual(self.manager.get("missing", 42), 42)

    def test_set_and_history(self) -> None:
        """正常值入参测试：设置与历史。"""
        self.manager.load({"key": 1})
        self.manager.set("key", 2)
        history = self.manager.get_history("key")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0][2], 2)

    def test_get_all(self) -> None:
        """正常值入参测试：获取全部。"""
        self.manager.load({"a": 1, "b": 2})
        all_config = self.manager.get_all()
        self.assertEqual(all_config, {"a": 1, "b": 2})

    def _now_entries(self, values: list[float]) -> list[tuple[float, float]]:
        """生成带当前时间戳的条目。"""
        ts = time.time()
        return [(ts, v) for v in values]

    def test_adapt_exploration_rate_increase(self) -> None:
        """正常值入参测试：误差大时探索率增加。"""
        self.manager.load({"exploration_rate": 0.3})
        self.manager.adapt_exploration_rate(self._now_entries([0.6, 0.7, 0.8]))
        self.assertEqual(self.manager.get("exploration_rate"), 0.35)

    def test_adapt_exploration_rate_decrease(self) -> None:
        """正常值入参测试：误差小时探索率减少。"""
        self.manager.load({"exploration_rate": 0.3})
        self.manager.adapt_exploration_rate(self._now_entries([0.05, 0.08, 0.02]))
        self.assertEqual(self.manager.get("exploration_rate"), 0.25)

    def test_adapt_exploration_rate_no_change(self) -> None:
        """正常值入参测试：误差中等时不调整。"""
        self.manager.load({"exploration_rate": 0.3})
        self.manager.adapt_exploration_rate(self._now_entries([0.2, 0.3, 0.4]))
        self.assertEqual(self.manager.get("exploration_rate"), 0.3)

    def test_adapt_exploration_rate_upper_bound(self) -> None:
        """边界极值测试：探索率上限。"""
        self.manager.load({"exploration_rate": 0.78})
        self.manager.adapt_exploration_rate(self._now_entries([0.9]))
        self.assertEqual(self.manager.get("exploration_rate"), 0.8)

    def test_adapt_exploration_rate_lower_bound(self) -> None:
        """边界极值测试：探索率下限。"""
        self.manager.load({"exploration_rate": 0.12})
        self.manager.adapt_exploration_rate(self._now_entries([0.01]))
        self.assertEqual(self.manager.get("exploration_rate"), 0.1)

    def test_adapt_epsilon_increase(self) -> None:
        """正常值入参测试：奖励低时epsilon增加。"""
        self.manager.load({"epsilon": 0.2})
        self.manager.adapt_epsilon(self._now_entries([0.1, 0.2, 0.1]))
        self.assertEqual(self.manager.get("epsilon"), 0.25)

    def test_adapt_epsilon_decrease(self) -> None:
        """正常值入参测试：奖励高时epsilon减少。"""
        self.manager.load({"epsilon": 0.2})
        self.manager.adapt_epsilon(self._now_entries([0.8, 0.9, 0.85]))
        self.assertAlmostEqual(self.manager.get("epsilon"), 0.15, places=10)

    def test_adapt_epsilon_lower_bound(self) -> None:
        """边界极值测试：epsilon下限。"""
        self.manager.load({"epsilon": 0.06})
        self.manager.adapt_epsilon(self._now_entries([0.9]))
        self.assertAlmostEqual(self.manager.get("epsilon"), 0.05, places=10)

    def test_adapt_interrupt_threshold_increase(self) -> None:
        """正常值入参测试：中断频繁时阈值增加。"""
        self.manager.load({"interrupt_threshold": 0.7})
        self.manager.adapt_interrupt_threshold(self._now_entries([12]))
        self.assertAlmostEqual(self.manager.get("interrupt_threshold"), 0.75, places=10)

    def test_adapt_interrupt_threshold_decrease(self) -> None:
        """正常值入参测试：中断稀少时阈值降低。"""
        self.manager.load({"interrupt_threshold": 0.7})
        self.manager.adapt_interrupt_threshold(self._now_entries([1]))
        self.assertAlmostEqual(self.manager.get("interrupt_threshold"), 0.65, places=10)

    def test_adapt_interrupt_threshold_upper_bound(self) -> None:
        """边界极值测试：阈值上限。"""
        self.manager.load({"interrupt_threshold": 0.88})
        self.manager.adapt_interrupt_threshold(self._now_entries([20]))
        self.assertAlmostEqual(self.manager.get("interrupt_threshold"), 0.9, places=10)

    def test_empty_errors(self) -> None:
        """空入参测试：空误差列表。"""
        self.manager.load({"exploration_rate": 0.3})
        self.manager.adapt_exploration_rate([])
        self.assertEqual(self.manager.get("exploration_rate"), 0.3)

    def test_empty_rewards(self) -> None:
        """空入参测试：空奖励列表。"""
        self.manager.load({"epsilon": 0.2})
        self.manager.adapt_epsilon([])
        self.assertEqual(self.manager.get("epsilon"), 0.2)

    def test_get_logger_helper(self) -> None:
        """正常值入参测试：获取配置管理器。"""
        manager = get_config_manager()
        self.assertIsInstance(manager, ConfigManager)

    def test_load_deep_copy_isolation(self) -> None:
        """边界极值测试：load深拷贝隔离，外部修改不影响内部。"""
        original = {"nested": {"value": 1}, "list": [1, 2, 3]}
        self.manager.load(original)
        # 外部修改原始字典
        original["nested"]["value"] = 999
        original["list"].append(4)
        # 内部配置不受影响
        self.assertEqual(self.manager.get("nested")["value"], 1)
        self.assertEqual(self.manager.get("list"), [1, 2, 3])

    def test_get_all_deep_copy_isolation(self) -> None:
        """边界极值测试：get_all深拷贝隔离，修改返回值不影响内部。"""
        self.manager.load({"nested": {"value": 1}})
        all_config = self.manager.get_all()
        all_config["nested"]["value"] = 999
        # 内部配置不受影响
        self.assertEqual(self.manager.get("nested")["value"], 1)

    def test_history_upper_limit(self) -> None:
        """边界极值测试：历史记录上限100。"""
        self.manager.load({"key": 0})
        for i in range(150):
            self.manager.set("key", i)
        history = self.manager.get_history("key")
        self.assertEqual(len(history), 100)
        # 保留最近100条
        self.assertEqual(history[-1][2], 149)
        self.assertEqual(history[0][2], 50)

    def test_reset_for_testing(self) -> None:
        """正常值入参测试：reset_for_testing清除单例。"""
        self.manager.load({"key": "value"})
        ConfigManager.reset_for_testing()
        new_manager = ConfigManager()
        self.assertIsNot(self.manager, new_manager)
        # 新实例配置为空
        self.assertIsNone(new_manager.get("key"))

    def test_hot_reload_replaces_config(self) -> None:
        """正常值入参测试：热更新load完全替换配置。"""
        self.manager.load({"a": 1, "b": 2})
        # 热更新为新配置
        self.manager.load({"c": 3})
        self.assertIsNone(self.manager.get("a"))
        self.assertIsNone(self.manager.get("b"))
        self.assertEqual(self.manager.get("c"), 3)

    def test_set_overwrites_existing(self) -> None:
        """正常值入参测试：set覆盖已存在键。"""
        self.manager.load({"key": "old"})
        self.manager.set("key", "new")
        self.assertEqual(self.manager.get("key"), "new")
        history = self.manager.get_history("key")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0][1], "old")
        self.assertEqual(history[0][2], "new")

    def test_set_new_key(self) -> None:
        """正常值入参测试：set新增不存在的键。"""
        self.manager.load({})
        self.manager.set("new_key", "value")
        self.assertEqual(self.manager.get("new_key"), "value")
        history = self.manager.get_history("new_key")
        self.assertEqual(len(history), 1)
        self.assertIsNone(history[0][1])

    def test_load_empty_dict(self) -> None:
        """空入参测试：加载空字典。"""
        self.manager.load({})
        self.assertEqual(self.manager.get_all(), {})
        self.assertIsNone(self.manager.get("any"))

    def test_load_none_value(self) -> None:
        """空入参测试：加载None值。"""
        self.manager.load({"key": None})
        self.assertIsNone(self.manager.get("key"))
        # 与默认值区分
        self.assertIsNone(self.manager.get("key", "default"))

    def test_load_nested_structures(self) -> None:
        """正常值入参测试：加载嵌套结构。"""
        nested = {
            "level1": {
                "level2": {
                    "level3": [1, 2, {"deep": True}]
                }
            }
        }
        self.manager.load(nested)
        result = self.manager.get("level1")
        self.assertEqual(result["level2"]["level3"][2]["deep"], True)

    def test_set_with_none_value(self) -> None:
        """空入参测试：set None值。"""
        self.manager.load({"key": "value"})
        self.manager.set("key", None)
        self.assertIsNone(self.manager.get("key"))

    def test_set_with_complex_object(self) -> None:
        """正常值入参测试：set复杂对象。"""
        self.manager.load({})
        complex_obj = {"list": [1, 2], "dict": {"a": 1}}
        self.manager.set("complex", complex_obj)
        # 修改原始对象不影响内部
        complex_obj["list"].append(3)
        stored = self.manager.get("complex")
        self.assertEqual(stored["list"], [1, 2])

    def test_adapt_exploration_rate_empty_after_filter(self) -> None:
        """空入参测试：过滤后为空（时间戳过期）。"""
        self.manager.load({"exploration_rate": 0.3})
        old_ts = time.time() - 1000  # 超过窗口
        self.manager.adapt_exploration_rate([(old_ts, 0.9)])
        self.assertEqual(self.manager.get("exploration_rate"), 0.3)

    def test_adapt_epsilon_empty_after_filter(self) -> None:
        """空入参测试：epsilon过滤后为空。"""
        self.manager.load({"epsilon": 0.2})
        old_ts = time.time() - 1000
        self.manager.adapt_epsilon([(old_ts, 0.9)])
        self.assertEqual(self.manager.get("epsilon"), 0.2)

    def test_adapt_interrupt_threshold_empty_after_filter(self) -> None:
        """空入参测试：中断阈值过滤后为空。"""
        self.manager.load({"interrupt_threshold": 0.7})
        old_ts = time.time() - 1000
        self.manager.adapt_interrupt_threshold([(old_ts, 100)])
        self.assertEqual(self.manager.get("interrupt_threshold"), 0.7)

    def test_adapt_interrupt_threshold_no_change(self) -> None:
        """正常值入参测试：中断数中等时不调整。"""
        self.manager.load({"interrupt_threshold": 0.7})
        self.manager.adapt_interrupt_threshold(self._now_entries([5]))
        self.assertEqual(self.manager.get("interrupt_threshold"), 0.7)

    def test_adapt_interrupt_threshold_lower_bound(self) -> None:
        """边界极值测试：中断阈值下限。"""
        self.manager.load({"interrupt_threshold": 0.52})
        self.manager.adapt_interrupt_threshold(self._now_entries([0]))
        self.assertEqual(self.manager.get("interrupt_threshold"), 0.5)

    def test_get_history_missing_key(self) -> None:
        """空入参测试：获取不存在键的历史。"""
        self.assertEqual(self.manager.get_history("missing"), [])

    def test_multiple_keys_history_independent(self) -> None:
        """正常值入参测试：多键历史独立。"""
        self.manager.load({"a": 1, "b": 1})
        self.manager.set("a", 2)
        self.manager.set("b", 3)
        self.manager.set("a", 4)
        self.assertEqual(len(self.manager.get_history("a")), 2)
        self.assertEqual(len(self.manager.get_history("b")), 1)


if __name__ == "__main__":
    unittest.main()
