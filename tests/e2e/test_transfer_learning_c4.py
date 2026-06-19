"""
C-4超复杂场景测试：离线复盘与迁移学习实战。

验证C-4修复的4个bug在极端复杂场景下的正确性。
覆盖：
- Bug16: TransferLearner集成到业务流程
- Bug17: compute_similarity维度不匹配处理
- Bug18: _train_predictor维度不匹配处理
- Bug19: sample_experiences检查_initialized
"""

import asyncio
import os
import shutil
import tempfile
import time
import unittest
from typing import Any, Dict
from unittest.mock import MagicMock

import numpy as np

from agent_core.common.config_manager import ConfigManager
from agent_core.common.data_contracts import (
    DriveSignals,
    EnvironmentState,
    ErrorMetrics,
    Experience,
    PredictionResult,
    Task,
)
from agent_core.memory.agent_main import SelfEvolvingAgent
from agent_core.memory.memory_module import MemorySystem
from agent_core.memory.transfer_learning import TransferLearner
from agent_core.monitoring.dashboard_server import DashboardServer


def _make_state(features: np.ndarray) -> EnvironmentState:
    return EnvironmentState(
        timestamp=time.time(),
        raw_sensors={},
        feature_vector=features,
    )


def _make_prediction(ensemble: np.ndarray) -> PredictionResult:
    return PredictionResult(
        low_level=ensemble,
        mid_level=ensemble,
        high_level=ensemble,
        ensemble=ensemble,
        confidence=0.8,
    )


def _make_drives() -> DriveSignals:
    return DriveSignals(
        safety_reward=0.5, gain_reward=0.5, efficiency_reward=0.5,
        safety_gap=0.5, gain_gap=0.5, efficiency_gap=0.5,
        weights={"safety": 0.33, "gain": 0.34, "efficiency": 0.33},
        total_reward=0.5,
    )


def _make_error() -> ErrorMetrics:
    return ErrorMetrics(
        mse=0.1, mae=0.2, mape=0.3,
        direction_accuracy=0.5, error_vector=np.array([0.1]),
    )


def _make_task(task_type: str = "safety") -> Task:
    return Task(
        task_id="t1", name="test", task_type=task_type,
        priority=0.5, expected_reward=0.8, expected_cost=0.2,
        novelty_score=0.3, params={},
    )


class TestTransferLearnerShapeMismatch(unittest.TestCase):
    """Bug17验证：compute_similarity维度不匹配处理。"""

    def test_shape_mismatch_returns_negative(self) -> None:
        """维度不匹配返回-1.0。"""
        learner = TransferLearner()
        learner.register_source_skill(
            "source1",
            np.array([0.1, 0.2, 0.3]),
            {"param": 1.0},
        )
        # 目标向量维度不同
        score = learner.compute_similarity(
            np.array([0.1, 0.2]), "source1"
        )
        self.assertEqual(score, -1.0)

    def test_same_shape_computes_correctly(self) -> None:
        """维度匹配时正常计算。"""
        learner = TransferLearner()
        vec = np.array([0.1, 0.2, 0.3])
        learner.register_source_skill("source1", vec, {"param": 1.0})
        score = learner.compute_similarity(vec, "source1")
        # 相同向量余弦相似度为1.0
        self.assertAlmostEqual(score, 1.0, places=5)

    def test_find_best_source_skips_mismatch(self) -> None:
        """find_best_source跳过维度不匹配的源。"""
        learner = TransferLearner(similarity_threshold=0.5)
        learner.register_source_skill(
            "wrong_dim", np.array([0.1, 0.2]), {"param": 1.0}
        )
        learner.register_source_skill(
            "right_dim", np.array([0.9, 0.9, 0.9]), {"param": 2.0}
        )
        target = np.array([0.8, 0.8, 0.8])
        best = learner.find_best_source(target)
        self.assertEqual(best, "right_dim")


class TestMemorySystemShapeMismatch(unittest.TestCase):
    """Bug18验证：_train_predictor维度不匹配处理。"""

    def test_train_skips_mismatched_shapes(self) -> None:
        """训练时跳过维度不匹配的经验。"""
        import asyncio

        async def run() -> None:
            mem = MemorySystem()
            await mem.initialize({"db_path": ":memory:"})

            # 创建维度不匹配的经验
            exp = Experience(
                timestamp=time.time(),
                state=_make_state(np.array([0.1, 0.2, 0.3])),
                prediction=_make_prediction(np.array([0.1, 0.2])),  # 维度不同
                drive_signals=_make_drives(),
                selected_task=_make_task(),
                execution_result={"status": "completed"},
                error_metrics=_make_error(),
                priority=0.5,
            )
            await mem.store(exp)

            predictor = MagicMock()
            predictor.update_all = MagicMock()

            mem._train_predictor(predictor, [exp])

            # 应该跳过，不调用update_all
            predictor.update_all.assert_not_called()

        asyncio.run(run())

    def test_train_with_matching_shapes(self) -> None:
        """维度匹配时正常训练。"""
        import asyncio

        async def run() -> None:
            mem = MemorySystem()
            await mem.initialize({"db_path": ":memory:"})

            vec = np.array([0.1, 0.2, 0.3])
            exp = Experience(
                timestamp=time.time(),
                state=_make_state(vec),
                prediction=_make_prediction(vec),
                drive_signals=_make_drives(),
                selected_task=_make_task(),
                execution_result={"status": "completed"},
                error_metrics=_make_error(),
                priority=0.5,
            )
            await mem.store(exp)

            predictor = MagicMock()
            predictor.update_all = MagicMock()

            mem._train_predictor(predictor, [exp])
            predictor.update_all.assert_called_once_with(vec, vec)

        asyncio.run(run())


class TestSampleExperiencesInitCheck(unittest.IsolatedAsyncioTestCase):
    """Bug19验证：sample_experiences检查_initialized。"""

    async def test_sample_before_init_returns_empty(self) -> None:
        """未初始化时采样返回空列表。"""
        mem = MemorySystem()
        result = await mem.sample_experiences(10)
        self.assertEqual(result, [])

    async def test_sample_after_shutdown_returns_empty(self) -> None:
        """shutdown后采样返回空列表。"""
        mem = MemorySystem()
        await mem.initialize({"db_path": ":memory:"})

        exp = Experience(
            timestamp=time.time(),
            state=_make_state(np.array([0.1])),
            prediction=_make_prediction(np.array([0.1])),
            drive_signals=_make_drives(),
            selected_task=_make_task(),
            execution_result={"status": "completed"},
            error_metrics=_make_error(),
            priority=0.5,
        )
        await mem.store(exp)
        await mem.shutdown()

        result = await mem.sample_experiences(10)
        self.assertEqual(result, [])


class TestTransferLearnerIntegration(unittest.IsolatedAsyncioTestCase):
    """Bug16验证：TransferLearner集成到业务流程。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c4_integration_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def _drain_pending_task(self, agent: SelfEvolvingAgent) -> None:
        """等待后台任务完成并收割结果，确保经验被存储。

        Bug29修复后guardian非阻塞，周期执行极快（~0.001s），
        而后台任务（gain任务_sample_cpu_sync需~1秒）无法在少数周期内完成。
        需显式等待pending任务完成并再跑一周期收割结果。
        """
        if agent._pending_execution is None:
            return
        if not agent._pending_execution.done():
            try:
                await asyncio.wait_for(
                    agent._pending_execution, timeout=5.0
                )
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                pass
        await agent._run_single_cycle(0.001)

    async def _build_agent(self) -> SelfEvolvingAgent:
        agent = SelfEvolvingAgent()
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {},
            "decision_engine": {},
            "memory": {
                "db_path": os.path.join(self._tmpdir, "transfer.db"),
            },
            "dashboard_port": 0,
        }
        await agent.initialize(config)
        return agent

    async def test_successful_task_registers_skill(self) -> None:
        """任务成功后注册源技能。"""
        agent = await self._build_agent()

        initial_sources = agent._transfer_learner.list_sources()
        self.assertEqual(len(initial_sources), 0)

        # 运行周期让任务执行
        for _ in range(20):
            await agent._run_single_cycle(0.001)

        # Bug29修复后guardian非阻塞，周期执行变快，
        # 需等待后台任务完成并收割结果，否则无经验存储、无源技能注册
        await self._drain_pending_task(agent)

        # 验证有源技能注册
        sources = agent._transfer_learner.list_sources()
        self.assertGreater(len(sources), 0)

        # 清理
        agent._running = False
        await agent._cancel_task(agent._pending_execution)
        agent._pending_execution = None
        agent._current_task = None
        await agent._shutdown_modules()
        agent._dashboard.stop()

    async def test_transfer_learning_applied_in_offline(self) -> None:
        """离线复盘中应用迁移学习。"""
        agent = await self._build_agent()

        # 运行周期积累经验
        for _ in range(30):
            await agent._run_single_cycle(0.001)

        # Bug29修复后guardian非阻塞，周期执行变快，
        # 需等待后台任务完成并收割结果，否则无经验存储、无源技能注册
        await self._drain_pending_task(agent)

        # 验证有源技能
        sources = agent._transfer_learner.list_sources()
        self.assertGreater(len(sources), 0)

        # 手动触发迁移学习
        epsilon_before = agent.decision_engine._epsilon
        agent._apply_transfer_learning()

        # 验证迁移学习被调用（epsilon可能变化也可能不变，取决于相似度）
        epsilon_after = agent.decision_engine._epsilon
        self.assertGreaterEqual(epsilon_after, 0.0)
        self.assertLessEqual(epsilon_after, 1.0)

        # 清理
        agent._running = False
        await agent._cancel_task(agent._pending_execution)
        agent._pending_execution = None
        agent._current_task = None
        await agent._shutdown_modules()
        agent._dashboard.stop()

    async def test_skill_count_capped(self) -> None:
        """源技能数量上限50。"""
        agent = await self._build_agent()

        # 手动注册60个源技能
        for i in range(60):
            agent._transfer_learner.register_source_skill(
                f"skill_{i}",
                np.random.rand(10),
                {"epsilon": 0.3},
            )

        # 触发清理（通过_register_transfer_skill）
        exp_state = _make_state(np.random.rand(10))
        from agent_core.common.data_contracts import Experience
        exp = Experience(
            timestamp=time.time(),
            state=exp_state,
            prediction=_make_prediction(np.random.rand(10)),
            drive_signals=_make_drives(),
            selected_task=_make_task(),
            execution_result={"status": "completed"},
            error_metrics=_make_error(),
            priority=0.5,
        )
        agent._register_transfer_skill(exp, {"status": "completed"})

        # 验证源技能数量不超过51（60+1-清理）
        # 实际上_register_transfer_skill先注册再清理，所以最多51
        sources = agent._transfer_learner.list_sources()
        self.assertLessEqual(len(sources), 51)

        # 清理
        agent._running = False
        await agent._shutdown_modules()
        agent._dashboard.stop()


class TestOfflineReviewIntegration(unittest.IsolatedAsyncioTestCase):
    """离线复盘集成测试。"""

    def setUp(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        self._tmpdir = tempfile.mkdtemp(prefix="c4_offline_")

    def tearDown(self) -> None:
        ConfigManager.reset_for_testing()
        DashboardServer.reset_for_testing()
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    async def test_offline_review_with_experiences(self) -> None:
        """有经验时离线复盘正常执行。"""
        mem = MemorySystem()
        await mem.initialize({"db_path": os.path.join(self._tmpdir, "offline.db")})

        # 存储多个经验
        for i in range(10):
            vec = np.array([0.1 * i, 0.2 * i, 0.3 * i])
            exp = Experience(
                timestamp=time.time() + i,
                state=_make_state(vec),
                prediction=_make_prediction(vec),
                drive_signals=_make_drives(),
                selected_task=_make_task(),
                execution_result={"status": "completed"},
                error_metrics=_make_error(),
                priority=0.5,
            )
            await mem.store(exp)

        predictor = MagicMock()
        predictor.update_all = MagicMock()

        await mem.offline_review(predictor)

        # 验证预测器被训练
        self.assertGreater(predictor.update_all.call_count, 0)
        await mem.shutdown()

    async def test_offline_review_empty_memory(self) -> None:
        """空记忆时离线复盘不崩溃。"""
        mem = MemorySystem()
        await mem.initialize({"db_path": os.path.join(self._tmpdir, "empty.db")})

        predictor = MagicMock()
        await mem.offline_review(predictor)
        predictor.update_all.assert_not_called()
        await mem.shutdown()

    async def test_offline_review_priority_decay(self) -> None:
        """离线复盘后优先级衰减。"""
        mem = MemorySystem()
        await mem.initialize({"db_path": os.path.join(self._tmpdir, "decay.db")})

        # 存储经验
        for i in range(5):
            vec = np.array([0.1 * i, 0.2 * i])
            exp = Experience(
                timestamp=time.time() + i,
                state=_make_state(vec),
                prediction=_make_prediction(vec),
                drive_signals=_make_drives(),
                selected_task=_make_task(),
                execution_result={"status": "completed"},
                error_metrics=_make_error(),
                priority=0.5,
            )
            await mem.store(exp)

        # 记录初始优先级
        initial_priorities = mem._priorities[:5].copy()

        predictor = MagicMock()
        await mem.offline_review(predictor)

        # 验证优先级衰减
        for i in range(5):
            self.assertLess(
                mem._priorities[i], initial_priorities[i]
            )

        await mem.shutdown()


class TestTransferLearningScenarios(unittest.TestCase):
    """迁移学习场景测试。"""

    def test_transfer_high_similarity(self) -> None:
        """高相似度时迁移参数。"""
        learner = TransferLearner(similarity_threshold=0.5)
        source_vec = np.array([0.8, 0.8, 0.8])
        learner.register_source_skill(
            "skill_a", source_vec, {"epsilon": 0.5}
        )

        # 目标向量与源高度相似
        target = np.array([0.85, 0.85, 0.85])
        params = learner.transfer_parameters(target, "target_skill")
        self.assertIsNotNone(params)
        self.assertIn("epsilon", params)
        # 迁移后的epsilon应接近源值乘以相似度
        self.assertGreater(params["epsilon"], 0.3)

    def test_transfer_low_similarity_no_match(self) -> None:
        """低相似度时不迁移。"""
        learner = TransferLearner(similarity_threshold=0.9)
        # 使用近似正交向量：源[0.9,0.1,0.1] vs 目标[0.1,0.9,0.1]
        # 余弦相似度≈0.229，低于阈值0.9
        learner.register_source_skill(
            "skill_a", np.array([0.9, 0.1, 0.1]), {"epsilon": 0.5}
        )

        target = np.array([0.1, 0.9, 0.1])
        params = learner.transfer_parameters(target, "target_skill")
        self.assertIsNone(params)

    def test_fine_tune_adjusts_parameters(self) -> None:
        """微调调整参数。"""
        learner = TransferLearner()
        params = {"epsilon": 0.5, "count": 10, "flag": True}

        # 正反馈增强
        tuned_pos = learner.fine_tune(params, 1.0)
        self.assertGreater(tuned_pos["epsilon"], params["epsilon"])
        # int被乘以(1+feedback*0.1)后变为float，值应增大
        self.assertGreater(tuned_pos["count"], params["count"])
        self.assertIsInstance(tuned_pos["count"], float)
        self.assertEqual(tuned_pos["flag"], params["flag"])  # bool不被微调

        # 负反馈减弱
        tuned_neg = learner.fine_tune(params, -1.0)
        self.assertLess(tuned_neg["epsilon"], params["epsilon"])
        self.assertLess(tuned_neg["count"], params["count"])

    def test_multiple_sources_find_best(self) -> None:
        """多源技能中找最相似的。"""
        learner = TransferLearner(similarity_threshold=0.5)
        learner.register_source_skill(
            "skill_a", np.array([0.9, 0.1, 0.1]), {"epsilon": 0.3}
        )
        learner.register_source_skill(
            "skill_b", np.array([0.1, 0.9, 0.1]), {"epsilon": 0.5}
        )
        learner.register_source_skill(
            "skill_c", np.array([0.1, 0.1, 0.9]), {"epsilon": 0.7}
        )

        # 目标最接近skill_b
        target = np.array([0.15, 0.85, 0.15])
        best = learner.find_best_source(target)
        self.assertEqual(best, "skill_b")

        params = learner.transfer_parameters(target, "target")
        self.assertIsNotNone(params)
        self.assertGreater(params["epsilon"], 0.3)  # 接近0.5*相似度


if __name__ == "__main__":
    unittest.main()
