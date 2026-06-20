"""
C-13: 能耗优化与资源自适应 测试。

覆盖：能量预算管理、自适应计算控制、模块休眠。
"""

import threading
import time
import unittest

from agent_core.energy.energy_budget import (
    EnergyBudgetManager,
    BudgetResult,
    ModulePriority,
)
from agent_core.energy.adaptive_compute import (
    AdaptiveComputeController,
    PowerProfile,
    ComputeDecision,
)
from agent_core.energy.module_hibernator import (
    ModuleHibernator,
    ModuleState,
)


class TestEnergyBudgetManager(unittest.TestCase):
    """能量预算管理器测试。"""

    def test_register_module(self):
        """注册模块分配初始预算。"""
        ebm = EnergyBudgetManager()
        ebm.register_module("mod", ModulePriority.NORMAL)
        stats = ebm.get_stats("mod")
        self.assertIsNotNone(stats)
        self.assertGreater(stats["budget"], 0)

    def test_priority_affects_budget(self):
        """优先级影响预算配额。"""
        ebm = EnergyBudgetManager(base_max_budget=100.0)
        ebm.register_module("critical", ModulePriority.CRITICAL)
        ebm.register_module("low", ModulePriority.LOW)
        c_stats = ebm.get_stats("critical")
        l_stats = ebm.get_stats("low")
        self.assertGreater(c_stats["max_budget"], l_stats["max_budget"])

    def test_consume_reduces_budget(self):
        """消耗减少预算。"""
        ebm = EnergyBudgetManager()
        ebm.register_module("mod", ModulePriority.NORMAL)
        before = ebm.get_budget("mod")
        result = ebm.consume("mod", 5.0)
        after = ebm.get_budget("mod")
        self.assertTrue(result.allowed)
        self.assertLess(after, before)

    def test_budget_replenishes(self):
        """预算随时间补充。"""
        ebm = EnergyBudgetManager(base_replenish_rate=100.0)
        ebm.register_module("mod", ModulePriority.NORMAL)
        ebm.consume("mod", 40.0)
        budget_low = ebm.get_budget("mod")
        time.sleep(0.1)
        budget_high = ebm.get_budget("mod")
        self.assertGreater(budget_high, budget_low)

    def test_low_budget_degraded(self):
        """低预算时降级标记。"""
        ebm = EnergyBudgetManager(base_max_budget=30.0)
        ebm.register_module("mod", ModulePriority.NORMAL)
        result = ebm.consume("mod", 25.0)
        self.assertTrue(result.degraded)

    def test_non_critical_rejected_when_empty(self):
        """非关键模块预算耗尽时拒绝。"""
        ebm = EnergyBudgetManager(
            base_max_budget=10.0, base_replenish_rate=0.1
        )
        ebm.register_module("mod", ModulePriority.LOW)
        # 耗尽预算
        for _ in range(20):
            ebm.consume("mod", 1.0)
        result = ebm.consume("mod", 1.0)
        self.assertFalse(result.allowed)

    def test_critical_overdraft_allowed(self):
        """关键模块允许透支。"""
        ebm = EnergyBudgetManager(
            base_max_budget=5.0, base_replenish_rate=0.1
        )
        ebm.register_module("vital", ModulePriority.CRITICAL)
        # 耗尽预算
        for _ in range(10):
            ebm.consume("vital", 1.0)
        # 关键模块仍允许
        result = ebm.consume("vital", 1.0)
        self.assertTrue(result.allowed)
        self.assertTrue(result.degraded)

    def test_unregister_module(self):
        """注销模块。"""
        ebm = EnergyBudgetManager()
        ebm.register_module("mod")
        ebm.unregister_module("mod")
        self.assertIsNone(ebm.get_budget("mod"))

    def test_unregistered_consumes_creates_account(self):
        """未注册模块消耗时自动创建低优先级账户。"""
        ebm = EnergyBudgetManager()
        result = ebm.consume("new_mod", 1.0)
        self.assertTrue(result.allowed)
        stats = ebm.get_stats("new_mod")
        self.assertEqual(stats["priority"], "LOW")

    def test_set_priority(self):
        """动态调整优先级。"""
        ebm = EnergyBudgetManager(base_max_budget=100.0)
        ebm.register_module("mod", ModulePriority.LOW)
        ebm.set_priority("mod", ModulePriority.CRITICAL)
        stats = ebm.get_stats("mod")
        self.assertEqual(stats["priority"], "CRITICAL")

    def test_get_all_stats(self):
        """获取所有模块统计。"""
        ebm = EnergyBudgetManager()
        ebm.register_module("a", ModulePriority.HIGH)
        ebm.register_module("b", ModulePriority.LOW)
        all_stats = ebm.get_all_stats()
        self.assertIn("a", all_stats)
        self.assertIn("b", all_stats)

    def test_invalid_params_rejected(self):
        """无效参数被拒绝。"""
        with self.assertRaises(ValueError):
            EnergyBudgetManager(base_replenish_rate=0)
        with self.assertRaises(ValueError):
            EnergyBudgetManager(base_max_budget=-1)

    def test_concurrent_access(self):
        """并发访问安全。"""
        ebm = EnergyBudgetManager(
            base_max_budget=10000.0, base_replenish_rate=1000.0
        )
        ebm.register_module("shared", ModulePriority.NORMAL)
        results = []
        barrier = threading.Barrier(5)

        def worker():
            barrier.wait()
            for _ in range(50):
                results.append(ebm.allow("shared", 1.0))

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 大部分应该允许（预算充足+补充）
        allowed_count = sum(results)
        self.assertGreater(allowed_count, 100)

    def test_reset(self):
        """重置所有账户。"""
        ebm = EnergyBudgetManager()
        ebm.register_module("a")
        ebm.register_module("b")
        ebm.reset()
        self.assertIsNone(ebm.get_budget("a"))


class TestAdaptiveComputeController(unittest.TestCase):
    """自适应计算控制器测试。"""

    def test_initial_profile(self):
        """初始配置为BALANCED。"""
        acc = AdaptiveComputeController()
        self.assertEqual(acc.profile, PowerProfile.BALANCED)

    def test_manual_profile(self):
        """手动设置配置。"""
        acc = AdaptiveComputeController()
        acc.set_manual_profile(PowerProfile.PERFORMANCE)
        self.assertEqual(acc.profile, PowerProfile.PERFORMANCE)

    def test_manual_override_resists_auto(self):
        """手动覆盖抵抗自动切换。"""
        acc = AdaptiveComputeController()
        acc.set_manual_profile(PowerProfile.PERFORMANCE)
        acc.update_pressure(95.0, 95.0)  # 极高压力
        self.assertEqual(acc.profile, PowerProfile.PERFORMANCE)

    def test_clear_override_restores_auto(self):
        """清除覆盖恢复自动。"""
        acc = AdaptiveComputeController()
        acc.set_manual_profile(PowerProfile.PERFORMANCE)
        acc.clear_manual_override()
        acc.update_pressure(95.0, 95.0)
        self.assertEqual(acc.profile, PowerProfile.EMERGENCY)

    def test_low_pressure_performance(self):
        """低压力切到PERFORMANCE。"""
        acc = AdaptiveComputeController()
        acc.update_pressure(30.0, 40.0)
        self.assertEqual(acc.profile, PowerProfile.PERFORMANCE)

    def test_medium_pressure_balanced(self):
        """中压力保持BALANCED。"""
        acc = AdaptiveComputeController()
        acc.update_pressure(65.0, 50.0)
        self.assertEqual(acc.profile, PowerProfile.BALANCED)

    def test_high_pressure_power_save(self):
        """高压力切到POWER_SAVE。"""
        acc = AdaptiveComputeController()
        acc.update_pressure(85.0, 70.0)
        self.assertEqual(acc.profile, PowerProfile.POWER_SAVE)

    def test_extreme_pressure_emergency(self):
        """极高压力切到EMERGENCY。"""
        acc = AdaptiveComputeController()
        acc.update_pressure(95.0, 95.0)
        self.assertEqual(acc.profile, PowerProfile.EMERGENCY)

    def test_decide_critical_always_computes(self):
        """关键计算始终执行。"""
        acc = AdaptiveComputeController()
        acc.set_manual_profile(PowerProfile.EMERGENCY)
        decision = acc.decide(is_critical=True)
        self.assertTrue(decision.should_compute)

    def test_decide_non_critical_frequency_skip(self):
        """非关键计算按频率跳过。"""
        acc = AdaptiveComputeController()
        acc.set_manual_profile(PowerProfile.POWER_SAVE)
        # POWER_SAVE频率0.5，约一半跳过
        decisions = [acc.decide(is_critical=False).should_compute for _ in range(10)]
        # 不应全部执行
        self.assertLess(sum(decisions), 10)

    def test_performance_no_skip(self):
        """PERFORMANCE模式不跳过。"""
        acc = AdaptiveComputeController()
        acc.set_manual_profile(PowerProfile.PERFORMANCE)
        decisions = [acc.decide().should_compute for _ in range(10)]
        self.assertTrue(all(decisions))

    def test_skip_non_critical_flag(self):
        """skip_non_critical标志正确。"""
        acc = AdaptiveComputeController()
        acc.set_manual_profile(PowerProfile.PERFORMANCE)
        self.assertFalse(acc.should_skip_non_critical())
        acc.set_manual_profile(PowerProfile.EMERGENCY)
        self.assertTrue(acc.should_skip_non_critical())

    def test_ensemble_ratio(self):
        """集成规模比例正确。"""
        acc = AdaptiveComputeController()
        acc.set_manual_profile(PowerProfile.PERFORMANCE)
        self.assertAlmostEqual(acc.get_ensemble_ratio(), 1.0)
        acc.set_manual_profile(PowerProfile.POWER_SAVE)
        self.assertAlmostEqual(acc.get_ensemble_ratio(), 0.5)

    def test_consolidation_interval(self):
        """记忆整合间隔正确。"""
        acc = AdaptiveComputeController()
        acc.set_manual_profile(PowerProfile.PERFORMANCE)
        self.assertAlmostEqual(acc.get_consolidation_interval(), 10.0)
        acc.set_manual_profile(PowerProfile.EMERGENCY)
        self.assertAlmostEqual(acc.get_consolidation_interval(), 120.0)

    def test_get_stats(self):
        """获取统计信息。"""
        acc = AdaptiveComputeController()
        acc.update_pressure(50.0, 60.0)
        acc.decide()
        stats = acc.get_stats()
        self.assertEqual(stats["profile"], "BALANCED")
        self.assertEqual(stats["call_count"], 1)
        self.assertFalse(stats["manual_override"])

    def test_reset(self):
        """重置控制器。"""
        acc = AdaptiveComputeController()
        acc.set_manual_profile(PowerProfile.EMERGENCY)
        acc.decide()
        acc.reset()
        self.assertEqual(acc.profile, PowerProfile.BALANCED)
        self.assertFalse(acc.should_skip_non_critical())

    def test_profile_switch_recorded(self):
        """配置切换被记录。"""
        acc = AdaptiveComputeController()
        acc.update_pressure(30.0, 30.0)  # -> PERFORMANCE
        acc.update_pressure(95.0, 95.0)  # -> EMERGENCY
        stats = acc.get_stats()
        self.assertGreaterEqual(stats["profile_switches"], 1)


class TestModuleHibernator(unittest.TestCase):
    """模块休眠管理器测试。"""

    def test_register_module(self):
        """注册模块初始为ACTIVE。"""
        mh = ModuleHibernator()
        mh.register("mod")
        self.assertEqual(mh.get_state("mod"), ModuleState.ACTIVE)

    def test_touch_updates_active_time(self):
        """touch更新活跃时间。"""
        mh = ModuleHibernator()
        mh.register("mod")
        idle_before = mh.get_idle_time("mod")
        time.sleep(0.05)
        mh.touch("mod")
        idle_after = mh.get_idle_time("mod")
        self.assertLess(idle_after, idle_before)

    def test_light_sleep_after_threshold(self):
        """超过浅休眠阈值进入浅休眠。"""
        mh = ModuleHibernator(
            light_sleep_threshold=0.1, deep_sleep_threshold=0.5
        )
        mh.register("mod")
        time.sleep(0.15)
        slept = mh.check_and_hibernate()
        self.assertIn("mod", slept)
        self.assertEqual(mh.get_state("mod"), ModuleState.LIGHT_SLEEP)

    def test_deep_sleep_after_threshold(self):
        """超过深休眠阈值进入深休眠。"""
        mh = ModuleHibernator(
            light_sleep_threshold=0.05, deep_sleep_threshold=0.15
        )
        mh.register("mod")
        time.sleep(0.2)
        mh.check_and_hibernate()
        self.assertEqual(mh.get_state("mod"), ModuleState.DEEP_SLEEP)

    def test_touch_wakes_up(self):
        """touch唤醒休眠模块。"""
        mh = ModuleHibernator(
            light_sleep_threshold=0.05, deep_sleep_threshold=0.2
        )
        mh.register("mod")
        time.sleep(0.1)
        mh.check_and_hibernate()
        self.assertEqual(mh.get_state("mod"), ModuleState.LIGHT_SLEEP)
        mh.touch("mod")
        self.assertEqual(mh.get_state("mod"), ModuleState.ACTIVE)

    def test_explicit_wake_up(self):
        """显式唤醒。"""
        mh = ModuleHibernator(
            light_sleep_threshold=0.05, deep_sleep_threshold=0.2
        )
        mh.register("mod")
        time.sleep(0.1)
        mh.check_and_hibernate()
        result = mh.wake_up("mod")
        self.assertTrue(result)
        self.assertEqual(mh.get_state("mod"), ModuleState.ACTIVE)

    def test_wake_up_already_active(self):
        """唤醒已活跃模块返回False。"""
        mh = ModuleHibernator()
        mh.register("mod")
        result = mh.wake_up("mod")
        self.assertFalse(result)

    def test_wake_up_nonexistent(self):
        """唤醒不存在模块返回False。"""
        mh = ModuleHibernator()
        self.assertFalse(mh.wake_up("ghost"))

    def test_sleep_callback_invoked(self):
        """休眠回调被调用。"""
        called = []
        mh = ModuleHibernator(
            light_sleep_threshold=0.05, deep_sleep_threshold=0.2
        )
        mh.register("mod", sleep_callback=lambda: called.append("sleep"))
        time.sleep(0.1)
        mh.check_and_hibernate()
        self.assertIn("sleep", called)

    def test_wakeup_callback_invoked(self):
        """唤醒回调被调用。"""
        called = []
        mh = ModuleHibernator(
            light_sleep_threshold=0.05, deep_sleep_threshold=0.2
        )
        mh.register("mod", wakeup_callback=lambda: called.append("wake"))
        time.sleep(0.1)
        mh.check_and_hibernate()
        mh.touch("mod")
        self.assertIn("wake", called)

    def test_callback_exception_isolated(self):
        """回调异常隔离。"""
        def bad_callback():
            raise RuntimeError("callback error")
        mh = ModuleHibernator(
            light_sleep_threshold=0.05, deep_sleep_threshold=0.2
        )
        mh.register("mod", sleep_callback=bad_callback)
        time.sleep(0.1)
        # 不应抛出
        mh.check_and_hibernate()

    def test_is_active(self):
        """is_active正确判断。"""
        mh = ModuleHibernator(
            light_sleep_threshold=0.05, deep_sleep_threshold=0.2
        )
        mh.register("mod")
        self.assertTrue(mh.is_active("mod"))
        time.sleep(0.1)
        mh.check_and_hibernate()
        self.assertFalse(mh.is_active("mod"))

    def test_unregister(self):
        """注销模块。"""
        mh = ModuleHibernator()
        mh.register("mod")
        mh.unregister("mod")
        self.assertIsNone(mh.get_state("mod"))

    def test_get_stats(self):
        """获取统计信息。"""
        mh = ModuleHibernator()
        mh.register("mod")
        mh.touch("mod")
        stats = mh.get_stats("mod")
        self.assertEqual(stats["name"], "mod")
        self.assertEqual(stats["state"], "ACTIVE")
        self.assertGreaterEqual(stats["activation_count"], 1)

    def test_get_all_stats(self):
        """获取所有模块统计。"""
        mh = ModuleHibernator()
        mh.register("a")
        mh.register("b")
        all_stats = mh.get_all_stats()
        self.assertIn("a", all_stats)
        self.assertIn("b", all_stats)

    def test_set_thresholds(self):
        """设置休眠阈值。"""
        mh = ModuleHibernator()
        mh.set_thresholds(light=10.0, deep=60.0)
        # 注册后用短时间验证不会休眠
        mh.register("mod")
        time.sleep(0.1)
        mh.check_and_hibernate()
        self.assertEqual(mh.get_state("mod"), ModuleState.ACTIVE)

    def test_invalid_thresholds(self):
        """无效阈值被拒绝。"""
        with self.assertRaises(ValueError):
            ModuleHibernator(light_sleep_threshold=0)
        with self.assertRaises(ValueError):
            ModuleHibernator(
                light_sleep_threshold=10.0, deep_sleep_threshold=5.0
            )

    def test_reset(self):
        """重置所有模块。"""
        mh = ModuleHibernator()
        mh.register("a")
        mh.register("b")
        mh.reset()
        self.assertIsNone(mh.get_state("a"))

    def test_concurrent_access(self):
        """并发访问安全。"""
        mh = ModuleHibernator(
            light_sleep_threshold=100.0, deep_sleep_threshold=200.0
        )
        mh.register("shared")
        barrier = threading.Barrier(5)

        def worker():
            barrier.wait()
            for _ in range(50):
                mh.touch("shared")
                mh.check_and_hibernate()

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(mh.get_state("shared"), ModuleState.ACTIVE)


class TestEndToEndEnergy(unittest.TestCase):
    """端到端能耗优化测试。"""

    def test_full_pipeline_normal_operation(self):
        """正常操作全流水线。"""
        ebm = EnergyBudgetManager()
        acc = AdaptiveComputeController()
        mh = ModuleHibernator()

        ebm.register_module("predictor", ModulePriority.HIGH)
        mh.register("predictor")

        # 正常压力
        acc.update_pressure(40.0, 50.0)
        self.assertEqual(acc.profile, PowerProfile.PERFORMANCE)

        # 预算充足
        self.assertTrue(ebm.allow("predictor", 1.0))

        # 模块活跃
        mh.touch("predictor")
        self.assertTrue(mh.is_active("predictor"))

    def test_high_pressure_degradation(self):
        """高压力下降级。"""
        ebm = EnergyBudgetManager()
        acc = AdaptiveComputeController()

        ebm.register_module("analyzer", ModulePriority.NORMAL)

        # 高压力
        acc.update_pressure(85.0, 80.0)
        self.assertEqual(acc.profile, PowerProfile.POWER_SAVE)

        # 非关键计算被跳过
        decisions = [
            acc.decide(is_critical=False).should_compute
            for _ in range(10)
        ]
        self.assertLess(sum(decisions), 10)

    def test_emergency_pressure_minimal_compute(self):
        """紧急压力下最小计算。"""
        acc = AdaptiveComputeController()
        acc.update_pressure(95.0, 95.0)
        self.assertEqual(acc.profile, PowerProfile.EMERGENCY)
        self.assertTrue(acc.should_skip_non_critical())
        # 关键计算仍执行
        self.assertTrue(acc.decide(is_critical=True).should_compute)

    def test_idle_module_hibernation_flow(self):
        """空闲模块休眠流程。"""
        mh = ModuleHibernator(
            light_sleep_threshold=0.05, deep_sleep_threshold=0.15
        )
        mh.register("doc_generator")

        # 初始活跃
        self.assertTrue(mh.is_active("doc_generator"))

        # 空闲后浅休眠
        time.sleep(0.08)
        mh.check_and_hibernate()
        self.assertEqual(mh.get_state("doc_generator"), ModuleState.LIGHT_SLEEP)

        # 继续空闲后深休眠
        time.sleep(0.1)
        mh.check_and_hibernate()
        self.assertEqual(mh.get_state("doc_generator"), ModuleState.DEEP_SLEEP)

        # 唤醒
        mh.wake_up("doc_generator")
        self.assertTrue(mh.is_active("doc_generator"))

    def test_energy_budget_priority_under_pressure(self):
        """压力下预算优先级保障。"""
        ebm = EnergyBudgetManager(
            base_max_budget=20.0, base_replenish_rate=1.0
        )
        ebm.register_module("perception", ModulePriority.CRITICAL)
        ebm.register_module("doc_gen", ModulePriority.LOW)

        # 耗尽低优先级预算
        for _ in range(30):
            ebm.consume("doc_gen", 1.0)
        # 低优先级被拒
        self.assertFalse(ebm.allow("doc_gen", 1.0))
        # 关键模块仍可用
        self.assertTrue(ebm.allow("perception", 1.0))

    def test_adaptive_profile_affects_ensemble(self):
        """自适应配置影响集成规模。"""
        acc = AdaptiveComputeController()

        # PERFORMANCE: 全集成
        acc.set_manual_profile(PowerProfile.PERFORMANCE)
        self.assertAlmostEqual(acc.get_ensemble_ratio(), 1.0)

        # EMERGENCY: 最小集成
        acc.set_manual_profile(PowerProfile.EMERGENCY)
        self.assertAlmostEqual(acc.get_ensemble_ratio(), 0.3)

    def test_hibernator_with_callbacks_integration(self):
        """休眠器与回调集成。"""
        events = []
        mh = ModuleHibernator(
            light_sleep_threshold=0.05, deep_sleep_threshold=0.2
        )
        mh.register(
            "module_x",
            wakeup_callback=lambda: events.append("wake"),
            sleep_callback=lambda: events.append("sleep"),
        )

        time.sleep(0.08)
        mh.check_and_hibernate()
        self.assertIn("sleep", events)

        mh.touch("module_x")
        self.assertIn("wake", events)
        self.assertTrue(mh.is_active("module_x"))


if __name__ == "__main__":
    unittest.main()
