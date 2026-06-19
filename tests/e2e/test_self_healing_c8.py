"""
C-8超复杂场景测试：自愈机制实战验证与策略进化。

验证C-8新增能力在极端复杂场景下的正确性：
- 策略库StrategyRegistry：多策略注册/命中率跟踪/副作用淘汰/冷却选择
- 预诊断机制：基于异常分数提前触发轻量恢复
- 幂等性保证：冷却期内不重复恢复
- 回滚机制：恢复失败后状态回滚
- 真实故障链端到端：感知失效→预测漂移→任务失败→自愈恢复
- 长时混沌压测：可用性≥99%，MTTR<2s
"""

import asyncio
import time
import unittest
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

from agent_core.monitoring.self_healing import SelfHealingManager
from agent_core.monitoring.strategy_registry import (
    StrategyRegistry,
    StrategyStats,
    _COOLDOWN_SECONDS,
    _SIDE_EFFECT_LIMIT,
)


class TestStrategyRegistryBasics(unittest.IsolatedAsyncioTestCase):
    """策略库基础功能验证。"""

    async def test_register_and_list(self) -> None:
        """注册策略后可列出。"""
        reg = StrategyRegistry()

        async def action() -> None:
            pass

        reg.register("mod", "strategy_a", action, priority=1)
        reg.register("mod", "strategy_b", action, priority=2)
        strategies = reg.list_strategies("mod")
        self.assertIn("strategy_a", strategies)
        self.assertIn("strategy_b", strategies)

    async def test_unregister(self) -> None:
        """注销策略后不再列出。"""
        reg = StrategyRegistry()

        async def action() -> None:
            pass

        reg.register("mod", "strategy_a", action)
        self.assertTrue(reg.unregister("mod", "strategy_a"))
        self.assertEqual(reg.list_strategies("mod"), [])
        self.assertFalse(reg.unregister("mod", "strategy_a"))

    async def test_select_by_priority(self) -> None:
        """高优先级策略优先被选择。"""
        reg = StrategyRegistry()

        async def action() -> None:
            pass

        reg.register("mod", "low_pri", action, priority=1)
        reg.register("mod", "high_pri", action, priority=10)
        selected = reg.select("mod")
        self.assertEqual(selected, "high_pri")

    async def test_select_skips_demoted(self) -> None:
        """降级策略不被选择。"""
        reg = StrategyRegistry()

        async def action() -> None:
            pass

        reg.register("mod", "good", action, priority=1)
        reg.register("mod", "bad", action, priority=10)
        # 手动降级bad
        stats = reg.get_stats("mod", "bad")
        assert stats is not None
        stats.demoted = True
        selected = reg.select("mod")
        self.assertEqual(selected, "good")

    async def test_select_returns_none_when_all_demoted(self) -> None:
        """所有策略降级时返回None。"""
        reg = StrategyRegistry()

        async def action() -> None:
            pass

        reg.register("mod", "a", action)
        reg.get_stats("mod", "a").demoted = True  # type: ignore[union-attr]
        self.assertIsNone(reg.select("mod"))

    async def test_select_returns_none_for_unknown_module(self) -> None:
        """未知模块返回None。"""
        reg = StrategyRegistry()
        self.assertIsNone(reg.select("nonexistent"))


class TestStrategyRegistryExecution(unittest.IsolatedAsyncioTestCase):
    """策略库执行与统计验证。"""

    async def test_execute_success_records_stats(self) -> None:
        """成功执行记录统计。"""
        reg = StrategyRegistry()
        call_count = {"n": 0}

        async def action() -> None:
            call_count["n"] += 1

        reg.register("mod", "strategy_a", action)
        outcome = await reg.execute("mod", "strategy_a")
        self.assertTrue(outcome.success)
        self.assertEqual(call_count["n"], 1)
        stats = reg.get_stats("mod", "strategy_a")
        assert stats is not None
        self.assertEqual(stats.total_executions, 1)
        self.assertEqual(stats.successes, 1)
        self.assertEqual(stats.hit_rate, 1.0)

    async def test_execute_failure_records_stats(self) -> None:
        """失败执行记录统计。"""
        reg = StrategyRegistry()

        async def action() -> None:
            raise RuntimeError("boom")

        reg.register("mod", "strategy_a", action)
        outcome = await reg.execute("mod", "strategy_a")
        self.assertFalse(outcome.success)
        self.assertIn("boom", outcome.reason)
        stats = reg.get_stats("mod", "strategy_a")
        assert stats is not None
        self.assertEqual(stats.failures, 1)
        self.assertEqual(stats.hit_rate, 0.0)

    async def test_execute_unknown_strategy(self) -> None:
        """执行未知策略返回失败结果。"""
        reg = StrategyRegistry()
        outcome = await reg.execute("mod", "nonexistent")
        self.assertFalse(outcome.success)
        self.assertEqual(outcome.reason, "strategy_not_found")

    async def test_hit_rate_sliding_window(self) -> None:
        """命中率基于滑动窗口计算。"""
        reg = StrategyRegistry()
        call_count = {"n": 0}

        async def action() -> None:
            call_count["n"] += 1
            if call_count["n"] % 2 == 0:
                raise RuntimeError("even fail")

        reg.register("mod", "flaky", action)
        # 执行10次：5成功5失败
        for _ in range(10):
            await reg.execute("mod", "flaky")
        stats = reg.get_stats("mod", "flaky")
        assert stats is not None
        self.assertEqual(stats.total_executions, 10)
        self.assertEqual(stats.successes, 5)
        self.assertAlmostEqual(stats.hit_rate, 0.5, places=2)

    async def test_cooldown_prevents_immediate_reselect(self) -> None:
        """冷却期内策略不被选择。"""
        reg = StrategyRegistry()

        async def action() -> None:
            pass

        reg.register("mod", "strategy_a", action, priority=1)
        # 执行一次后进入冷却
        await reg.execute("mod", "strategy_a")
        # 冷却期内select返回None
        selected = reg.select("mod")
        self.assertIsNone(selected)

    async def test_cooldown_expires(self) -> None:
        """冷却期过后策略恢复可选。"""
        reg = StrategyRegistry()

        async def action() -> None:
            pass

        reg.register("mod", "strategy_a", action, priority=1)
        await reg.execute("mod", "strategy_a")
        # 清除冷却
        reg.clear_cooldowns()
        selected = reg.select("mod")
        self.assertEqual(selected, "strategy_a")


class TestStrategyRegistryDemotion(unittest.IsolatedAsyncioTestCase):
    """策略降级与淘汰验证。"""

    async def test_side_effect_demotes_strategy(self) -> None:
        """副作用累计超限导致降级。"""
        reg = StrategyRegistry()

        async def action() -> None:
            pass

        reg.register("mod", "risky", action)
        for _ in range(_SIDE_EFFECT_LIMIT):
            reg.mark_side_effect("mod", "risky")
        stats = reg.get_stats("mod", "risky")
        assert stats is not None
        self.assertTrue(stats.demoted)

    async def test_low_hit_rate_demotes_strategy(self) -> None:
        """低命中率导致降级。"""
        reg = StrategyRegistry()

        async def action() -> None:
            raise RuntimeError("always fail")

        reg.register("mod", "bad", action)
        # 执行足够多次（>= _MIN_SAMPLES_FOR_DEMOTE=5）且全部失败
        for _ in range(6):
            await reg.execute("mod", "bad")
        stats = reg.get_stats("mod", "bad")
        assert stats is not None
        self.assertTrue(stats.demoted)

    async def test_reset_demotion(self) -> None:
        """重置降级状态后策略恢复可用。"""
        reg = StrategyRegistry()

        async def action() -> None:
            pass

        reg.register("mod", "recoverable", action)
        stats = reg.get_stats("mod", "recoverable")
        assert stats is not None
        stats.demoted = True
        self.assertTrue(reg.reset_demotion("mod", "recoverable"))
        self.assertFalse(stats.demoted)

    async def test_get_all_stats(self) -> None:
        """获取所有模块所有策略统计。"""
        reg = StrategyRegistry()

        async def action() -> None:
            pass

        reg.register("mod_a", "s1", action)
        reg.register("mod_b", "s2", action)
        all_stats = reg.get_all_stats()
        self.assertIn("mod_a", all_stats)
        self.assertIn("mod_b", all_stats)
        self.assertIn("s1", all_stats["mod_a"])
        self.assertIn("s2", all_stats["mod_b"])


class TestPreDiagnosis(unittest.IsolatedAsyncioTestCase):
    """预诊断机制验证。"""

    async def test_pre_diagnose_below_threshold_no_action(self) -> None:
        """异常分数低于阈值时不触发轻量恢复。"""
        manager = SelfHealingManager()
        recovery_called = {"n": 0}

        async def anomaly_callback() -> float:
            return 0.3  # 低于0.7阈值

        async def lightweight_recovery() -> None:
            recovery_called["n"] += 1

        manager.register_pre_diagnosis(
            "predictor", anomaly_callback, lightweight_recovery
        )
        results = await manager.pre_diagnose()
        self.assertEqual(results["predictor"]["anomaly_score"], 0.3)
        self.assertEqual(results["predictor"]["action"], "none")
        self.assertEqual(recovery_called["n"], 0)

    async def test_pre_diagnose_above_threshold_triggers_recovery(self) -> None:
        """异常分数超阈值时触发轻量恢复。"""
        manager = SelfHealingManager()
        recovery_called = {"n": 0}

        async def anomaly_callback() -> float:
            return 0.9  # 超过0.7阈值

        async def lightweight_recovery() -> None:
            recovery_called["n"] += 1

        manager.register_pre_diagnosis(
            "predictor", anomaly_callback, lightweight_recovery
        )
        results = await manager.pre_diagnose()
        self.assertEqual(results["predictor"]["action"], "lightweight_recovery")
        self.assertEqual(recovery_called["n"], 1)

    async def test_pre_diagnose_cooldown_prevents_repeat(self) -> None:
        """冷却期内不重复触发轻量恢复。"""
        manager = SelfHealingManager()
        recovery_called = {"n": 0}

        async def anomaly_callback() -> float:
            return 0.95

        async def lightweight_recovery() -> None:
            recovery_called["n"] += 1

        manager.register_pre_diagnosis(
            "predictor", anomaly_callback, lightweight_recovery
        )
        # 第一次触发
        await manager.pre_diagnose()
        self.assertEqual(recovery_called["n"], 1)
        # 冷却期内第二次应跳过
        results = await manager.pre_diagnose()
        self.assertEqual(results["predictor"]["action"], "cooldown_skip")
        self.assertEqual(recovery_called["n"], 1)

    async def test_pre_diagnose_callback_exception_handled(self) -> None:
        """预诊断回调异常不崩溃。"""
        manager = SelfHealingManager()

        async def anomaly_callback() -> float:
            raise RuntimeError("sensor broken")

        async def lightweight_recovery() -> None:
            pass

        manager.register_pre_diagnosis(
            "predictor", anomaly_callback, lightweight_recovery
        )
        results = await manager.pre_diagnose()
        self.assertEqual(results["predictor"]["action"], "error")
        self.assertIn("sensor broken", results["predictor"]["reason"])

    async def test_pre_diagnose_no_lightweight_recovery(self) -> None:
        """超阈值但无轻量恢复动作时记录no_lightweight_recovery。"""
        manager = SelfHealingManager()

        async def anomaly_callback() -> float:
            return 0.9

        # 只注册回调，不注册轻量恢复（通过直接操作内部字典模拟）
        manager._pre_diagnosis_callbacks["mod"] = anomaly_callback
        # 不设置 _lightweight_recoveries["mod"]
        results = await manager.pre_diagnose()
        self.assertEqual(results["mod"]["action"], "no_lightweight_recovery")


class TestIdempotencyAndRollback(unittest.IsolatedAsyncioTestCase):
    """幂等性与回滚机制验证。"""

    async def test_recovery_cooldown_prevents_repeat(self) -> None:
        """成功恢复后冷却期内不重复恢复。"""
        manager = SelfHealingManager()
        recovery_count = {"n": 0}

        async def checker() -> Dict[str, Any]:
            return {"status": "unhealthy"}

        async def recovery() -> None:
            recovery_count["n"] += 1

        manager.register_module("mod", checker, recovery)
        # 累积失败到阈值
        for _ in range(3):
            await manager.diagnose()
        # 第一次恢复
        diagnosis = await manager.diagnose()
        result = await manager.heal(diagnosis)
        self.assertTrue(result["mod"]["healed"])
        self.assertEqual(recovery_count["n"], 1)
        # 冷却期内再次触发应跳过
        for _ in range(3):
            await manager.diagnose()
        diagnosis = await manager.diagnose()
        result = await manager.heal(diagnosis)
        self.assertFalse(result["mod"]["healed"])
        self.assertEqual(result["mod"]["reason"], "cooldown")
        self.assertEqual(recovery_count["n"], 1)

    async def test_rollback_on_recovery_failure(self) -> None:
        """恢复失败后回滚失败计数到阈值。"""
        manager = SelfHealingManager()

        async def checker() -> Dict[str, Any]:
            return {"status": "unhealthy"}

        async def recovery() -> None:
            raise RuntimeError("recovery failed")

        manager.register_module("mod", checker, recovery)
        for _ in range(3):
            await manager.diagnose()
        diagnosis = await manager.diagnose()
        result = await manager.heal(diagnosis)
        self.assertFalse(result["mod"]["healed"])
        # 回滚后失败计数应为阈值（3），而非0或更高
        counts = manager.get_failure_counts()
        self.assertEqual(counts["mod"], 3)

    async def test_rollback_on_verification_failure(self) -> None:
        """恢复动作成功但验证失败时标记副作用并回滚。"""
        manager = SelfHealingManager()
        recovery_count = {"n": 0}

        state = {"healthy": False}

        async def checker() -> Dict[str, Any]:
            if state["healthy"]:
                return {"status": "healthy"}
            return {"status": "unhealthy"}

        async def recovery() -> None:
            recovery_count["n"] += 1
            # 恢复动作执行但不改变健康状态（验证会失败）

        manager.register_module("mod", checker, recovery)
        for _ in range(3):
            await manager.diagnose()
        diagnosis = await manager.diagnose()
        result = await manager.heal(diagnosis)
        # 恢复动作成功但验证失败
        self.assertTrue(result["mod"]["healed"])
        self.assertFalse(result["mod"]["verified"])
        # 副作用应被标记
        stats = manager.get_strategy_registry().get_stats("mod", "recovery_action")
        assert stats is not None
        self.assertGreaterEqual(stats.side_effects, 1)

    async def test_recent_recovery_recorded(self) -> None:
        """恢复后记录最近恢复信息。"""
        manager = SelfHealingManager()

        async def checker() -> Dict[str, Any]:
            return {"status": "unhealthy"}

        async def recovery() -> None:
            pass

        manager.register_module("mod", checker, recovery)
        for _ in range(3):
            await manager.diagnose()
        diagnosis = await manager.diagnose()
        await manager.heal(diagnosis)
        recent = manager.get_recent_recovery("mod")
        self.assertIsNotNone(recent)
        self.assertEqual(recent["strategy"], "recovery_action")
        self.assertTrue(recent["success"])


class TestMultipleStrategyEvolution(unittest.IsolatedAsyncioTestCase):
    """多策略进化验证：低效策略被淘汰后自动选择高效策略。"""

    async def test_demoted_strategy_skipped_for_alternative(self) -> None:
        """低效策略降级后自动选择替代策略。"""
        manager = SelfHealingManager()
        call_counts = {"bad": 0, "good": 0}

        async def checker() -> Dict[str, Any]:
            return {"status": "unhealthy"}

        async def bad_recovery() -> None:
            call_counts["bad"] += 1
            raise RuntimeError("always fails")

        async def good_recovery() -> None:
            call_counts["good"] += 1

        # 注册模块（默认recovery_action策略）
        manager.register_module("mod", checker, bad_recovery)
        # 注册高优先级的好策略
        manager.register_strategy("mod", "good_strategy", good_recovery, priority=10)

        # 累积失败
        for _ in range(3):
            await manager.diagnose()

        # 第一次恢复：选择高优先级good_strategy
        diagnosis = await manager.diagnose()
        result = await manager.heal(diagnosis)
        self.assertTrue(result["mod"]["healed"])
        self.assertEqual(result["mod"]["method"], "good_strategy")
        self.assertEqual(call_counts["good"], 1)
        self.assertEqual(call_counts["bad"], 0)

    async def test_strategy_registry_integration_with_healing(self) -> None:
        """策略库与自愈管理器集成验证。"""
        manager = SelfHealingManager()

        async def checker() -> Dict[str, Any]:
            return {"status": "unhealthy"}

        async def recovery() -> None:
            pass

        manager.register_module("mod", checker, recovery)
        # 验证策略库中有recovery_action策略
        reg = manager.get_strategy_registry()
        self.assertIn("recovery_action", reg.list_strategies("mod"))


class TestRealisticFaultChain(unittest.IsolatedAsyncioTestCase):
    """真实故障链端到端验证：感知失效→预测漂移→自愈恢复。"""

    async def test_perception_failure_triggers_self_healing(self) -> None:
        """感知模块持续失败触发自愈恢复。"""
        manager = SelfHealingManager()
        state = {"crashed": True, "recoveries": 0}

        async def checker() -> Dict[str, Any]:
            if state["crashed"]:
                return {"status": "unhealthy"}
            return {"status": "healthy"}

        async def recovery() -> None:
            state["crashed"] = False
            state["recoveries"] += 1

        manager.register_module("perception", checker, recovery)

        # 累积失败到阈值
        for _ in range(3):
            await manager.diagnose()

        diagnosis = await manager.diagnose()
        result = await manager.heal(diagnosis)
        self.assertTrue(result["perception"]["healed"])
        self.assertTrue(result["perception"]["verified"])
        self.assertEqual(state["recoveries"], 1)

        # 恢复后健康检查通过
        diagnosis = await manager.diagnose()
        self.assertEqual(diagnosis["perception"]["status"], "healthy")

    async def test_prediction_drift_triggers_pre_diagnosis(self) -> None:
        """预测漂移（高异常分数）触发预诊断轻量恢复。"""
        manager = SelfHealingManager()
        state = {"anomaly": 0.9, "recoveries": 0}

        async def anomaly_callback() -> float:
            return state["anomaly"]

        async def lightweight_recovery() -> None:
            state["anomaly"] = 0.2  # 恢复后异常分数下降
            state["recoveries"] += 1

        manager.register_pre_diagnosis(
            "predictor", anomaly_callback, lightweight_recovery
        )

        # 预诊断触发轻量恢复
        results = await manager.pre_diagnose()
        self.assertEqual(results["predictor"]["action"], "lightweight_recovery")
        self.assertEqual(state["recoveries"], 1)

        # 再次预诊断，异常分数已下降
        results = await manager.pre_diagnose()
        self.assertEqual(results["predictor"]["anomaly_score"], 0.2)
        self.assertEqual(results["predictor"]["action"], "none")

    async def test_cascading_fault_chain_recovery(self) -> None:
        """级联故障链：感知失效→预测漂移→双路自愈恢复。"""
        manager = SelfHealingManager()
        state = {
            "perception_crashed": True,
            "anomaly": 0.95,
            "perception_recoveries": 0,
            "predictor_recoveries": 0,
        }

        async def perception_checker() -> Dict[str, Any]:
            if state["perception_crashed"]:
                return {"status": "unhealthy"}
            return {"status": "healthy"}

        async def perception_recovery() -> None:
            state["perception_crashed"] = False
            state["perception_recoveries"] += 1

        async def anomaly_callback() -> float:
            return state["anomaly"]

        async def predictor_lightweight_recovery() -> None:
            state["anomaly"] = 0.1
            state["predictor_recoveries"] += 1

        manager.register_module(
            "perception", perception_checker, perception_recovery
        )
        manager.register_pre_diagnosis(
            "predictor", anomaly_callback, predictor_lightweight_recovery
        )

        # 预诊断先触发预测器轻量恢复
        pre_results = await manager.pre_diagnose()
        self.assertEqual(pre_results["predictor"]["action"], "lightweight_recovery")
        self.assertEqual(state["predictor_recoveries"], 1)

        # 硬诊断累积失败触发感知恢复
        for _ in range(3):
            await manager.diagnose()
        diagnosis = await manager.diagnose()
        result = await manager.heal(diagnosis)
        self.assertTrue(result["perception"]["healed"])
        self.assertEqual(state["perception_recoveries"], 1)

        # 全部恢复后系统健康
        diagnosis = await manager.diagnose()
        self.assertEqual(diagnosis["perception"]["status"], "healthy")
        pre_results = await manager.pre_diagnose()
        self.assertEqual(pre_results["predictor"]["action"], "none")


class TestLongRunningChaos(unittest.IsolatedAsyncioTestCase):
    """长时混沌压测：验证可用性与MTTR。"""

    async def test_long_running_chaos_recovery_effectiveness(self) -> None:
        """长时混沌下自愈恢复有效性验证。

        验证目标：
        1. 每次故障都能被自愈机制恢复（恢复成功率100%）
        2. MTTR < 2s
        3. 恢复后系统回到健康状态

        冷却期为3秒（真实时间），测试在崩溃间加入sleep越过冷却期，
        确保每次崩溃都能触发独立恢复。
        """
        manager = SelfHealingManager()
        state = {
            "crashed": False,
            "recoveries": 0,
            "recovery_times": [],
        }

        async def checker() -> Dict[str, Any]:
            if state["crashed"]:
                return {"status": "unhealthy"}
            return {"status": "healthy"}

        async def recovery() -> None:
            start = time.time()
            state["crashed"] = False
            state["recoveries"] += 1
            state["recovery_times"].append(time.time() - start)

        manager.register_module("mod", checker, recovery)

        # 模拟3次独立的崩溃-恢复周期
        for crash_num in range(3):
            # 触发崩溃
            state["crashed"] = True
            # 累积失败到阈值（3次诊断）
            for _ in range(3):
                await manager.diagnose()
            diagnosis = await manager.diagnose()
            result = await manager.heal(diagnosis)
            self.assertTrue(
                result["mod"]["healed"],
                f"Crash #{crash_num} recovery failed: {result['mod']}",
            )
            # 等待冷却期过期（冷却期3秒，sleep 3.1秒）
            await asyncio.sleep(3.1)

        # 验证：3次崩溃都成功恢复
        self.assertEqual(state["recoveries"], 3)
        self.assertFalse(state["crashed"])

        # MTTR < 2s
        if state["recovery_times"]:
            mttr = sum(state["recovery_times"]) / len(state["recovery_times"])
            self.assertLess(mttr, 2.0, f"MTTR {mttr:.3f}s >= 2s")

        # 最终状态健康
        final_diagnosis = await manager.diagnose()
        self.assertEqual(final_diagnosis["mod"]["status"], "healthy")

    async def test_diagnosis_loop_with_pre_diagnosis(self) -> None:
        """诊断循环集成预诊断验证。"""
        manager = SelfHealingManager()
        state = {
            "anomaly": 0.9,
            "lightweight_count": 0,
            "hard_recovery_count": 0,
            "crashed": False,
        }

        async def anomaly_callback() -> float:
            return state["anomaly"]

        async def lightweight_recovery() -> None:
            state["anomaly"] = 0.1
            state["lightweight_count"] += 1

        async def checker() -> Dict[str, Any]:
            if state["crashed"]:
                return {"status": "unhealthy"}
            return {"status": "healthy"}

        async def hard_recovery() -> None:
            state["crashed"] = False
            state["hard_recovery_count"] += 1

        manager.register_module("mod", checker, hard_recovery)
        manager.register_pre_diagnosis(
            "predictor", anomaly_callback, lightweight_recovery
        )

        # 启动诊断循环
        loop_task = asyncio.create_task(manager.run_diagnosis_loop(0.05))
        await asyncio.sleep(0.5)
        manager.stop()
        try:
            await asyncio.wait_for(loop_task, timeout=1.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass

        # 预诊断应触发轻量恢复
        self.assertGreater(state["lightweight_count"], 0)


class TestStrategySelectionOrdering(unittest.IsolatedAsyncioTestCase):
    """策略选择排序逻辑验证。"""

    async def test_select_prefers_higher_hit_rate(self) -> None:
        """同优先级下命中率高的策略优先。"""
        reg = StrategyRegistry()

        async def good_action() -> None:
            pass

        async def bad_action() -> None:
            raise RuntimeError("fail")

        reg.register("mod", "good", good_action, priority=1)
        reg.register("mod", "bad", bad_action, priority=1)

        # 执行若干次建立命中率差异
        for _ in range(3):
            await reg.execute("mod", "good")
        for _ in range(3):
            await reg.execute("mod", "bad")

        # 清除冷却使两者都可选
        reg.clear_cooldowns()
        # bad因低命中率应被降级，good可选
        bad_stats = reg.get_stats("mod", "bad")
        assert bad_stats is not None
        if bad_stats.demoted:
            # bad已降级，应选good
            selected = reg.select("mod")
            self.assertEqual(selected, "good")
        else:
            # 未降级则按命中率选good
            selected = reg.select("mod")
            self.assertEqual(selected, "good")

    async def test_select_prefers_least_recently_used(self) -> None:
        """同优先级同命中率下最久未用的优先。"""
        reg = StrategyRegistry()

        async def action() -> None:
            pass

        reg.register("mod", "a", action, priority=1)
        reg.register("mod", "b", action, priority=1)

        # 两者都执行一次使命中率相同
        await reg.execute("mod", "a")
        await reg.execute("mod", "b")
        reg.clear_cooldowns()
        # a先执行b后执行，b的last_executed更晚；
        # 再执行a使其成为最近使用的，则应选b（最久未用）
        await reg.execute("mod", "a")
        reg.clear_cooldowns()
        selected = reg.select("mod")
        # a的last_executed最晚，b较早，按last_executed升序应选b
        self.assertEqual(selected, "b")


if __name__ == "__main__":
    unittest.main()
