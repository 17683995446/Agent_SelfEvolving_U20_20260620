"""
自驱永续进化Agent主类模块。

全系统整合，双循环运行。
通过DI容器组装模块，实现乐高式插拔。
"""

import asyncio
import time
import traceback
from typing import Any, Dict, Optional

import numpy as np

from agent_core.common.config_manager import get_config_manager
from agent_core.common.data_contracts import Experience
from agent_core.common.di_container import DIContainer, get_di_container
from agent_core.common.exceptions import ModuleNotInitializedException
from agent_core.common.interfaces import (
    IDecisionEngine,
    IDriveEngine,
    IEnvironmentPerception,
    IErrorEvaluator,
    IMemorySystem,
    IMultiLayerPredictor,
    IResourceGuardian,
    ITaskGenerator,
)
from agent_core.common.logger import get_logger
from agent_core.drive.emotion_model import EmotionEngine
from agent_core.memory.transfer_learning import TransferLearner
from agent_core.monitoring.dashboard_server import get_dashboard_server
from agent_core.monitoring.self_healing import SelfHealingManager
from agent_core.task.causal_reasoner import CausalReasoner
from agent_core.task.task_executor import TaskExecutor


class SelfEvolvingAgent:
    """
    自驱永续进化Agent主类。
    """

    def __init__(self, container: Optional[DIContainer] = None) -> None:
        self._container = container or get_di_container()
        self.perception = self._resolve_perception()
        self.drive_engine = self._resolve_drive_engine()
        self.predictor = self._resolve_predictor()
        self.error_evaluator = self._resolve_error_evaluator()
        self.task_generator = self._resolve_task_generator()
        self.decision_engine = self._resolve_decision_engine()
        self.task_executor = self._resolve_task_executor()
        self.memory = self._resolve_memory()
        self.guardian = self._resolve_guardian()
        self._running = False
        self._online_task: Optional[asyncio.Task] = None
        self._offline_task: Optional[asyncio.Task] = None
        self._diagnosis_task: Optional[asyncio.Task] = None
        self._current_task: Optional[Any] = None
        self._pending_execution: Optional[asyncio.Task] = None
        self._pending_context: Optional[Dict[str, Any]] = None
        self._config: Dict[str, Any] = {}
        self._logger = get_logger()
        self._previous_state: Optional[np.ndarray] = None
        self._config_manager = get_config_manager()
        self._recent_errors: list[tuple[float, float]] = []
        self._recent_rewards: list[tuple[float, float]] = []
        self._interrupt_history: list[tuple[float, int]] = []
        self._interrupt_count: int = 0
        self._dashboard = get_dashboard_server()
        self._cycle_count: int = 0
        self._self_healing = SelfHealingManager()
        self._causal_reasoner = CausalReasoner()
        self._emotion_engine = EmotionEngine()
        self._transfer_learner = TransferLearner()
        self._initialized = False
        self._task_succeeded = False

    def _resolve_perception(self) -> IEnvironmentPerception:
        return self._container.resolve("perception")

    def _resolve_drive_engine(self) -> IDriveEngine:
        return self._container.resolve("drive_engine")

    def _resolve_predictor(self) -> IMultiLayerPredictor:
        return self._container.resolve("predictor")

    def _resolve_error_evaluator(self) -> IErrorEvaluator:
        return self._container.resolve("error_evaluator")

    def _resolve_task_generator(self) -> ITaskGenerator:
        return self._container.resolve("task_generator")

    def _resolve_decision_engine(self) -> IDecisionEngine:
        return self._container.resolve("decision_engine")

    def _resolve_task_executor(self) -> TaskExecutor:
        return self._container.resolve("task_executor")

    def _resolve_memory(self) -> IMemorySystem:
        return self._container.resolve("memory")

    def _resolve_guardian(self) -> IResourceGuardian:
        return self._container.resolve("guardian")

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化所有模块。"""
        self._config = config
        self._config_manager.load(config)
        self._logger.info(
            "[SelfEvolvingAgent] Initializing all modules..."
        )
        await self._initialize_modules(config)
        self.error_evaluator = self._container.resolve("error_evaluator")
        self._logger.info(
            "[SelfEvolvingAgent] All modules initialized"
        )
        self._start_dashboard(config)
        self._register_modules_for_healing()
        self._initialized = True
        self._logger.info("[SelfEvolvingAgent] Initialization complete")
        return True

    async def _initialize_modules(self, config: Dict[str, Any]) -> None:
        """初始化各子模块。"""
        results = await asyncio.gather(
            self.perception.initialize(config.get("perception", {})),
            self.drive_engine.initialize(
                config.get("drive_engine", {})
            ),
            self.predictor.initialize(config.get("predictor", {})),
            self.task_generator.initialize(
                config.get("task_generator", {})
            ),
            self.decision_engine.initialize(
                config.get("decision_engine", {})
            ),
            self.memory.initialize(config.get("memory", {})),
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                name = [
                    "perception", "drive_engine", "predictor",
                    "task_generator", "decision_engine", "memory",
                ][i]
                self._logger.error(
                    f"[SelfEvolvingAgent] Module {name} init failed: {result}"
                )
                raise result

    def _start_dashboard(self, config: Dict[str, Any]) -> None:
        """启动监控面板。"""
        port = config.get("dashboard_port", 8080)
        self._dashboard.register_state_provider(
            self._get_runtime_state
        )
        self._dashboard.start(port=port)

    async def run_online_loop(self, interval_seconds: float) -> None:
        """在线实时闭环。"""
        self._running = True
        self._logger.info(
            "[SelfEvolvingAgent] Online loop started"
        )
        while self._running:
            await self._run_single_cycle(interval_seconds)

    async def _run_single_cycle(self, interval_seconds: float) -> None:
        """执行单个在线周期。"""
        try:
            await self._execute_cycle_core(interval_seconds)
        except Exception as exc:
            self._logger.error(
                f"[SelfEvolvingAgent] Cycle error: {exc}\n"
                f"{traceback.format_exc()}"
            )
            await asyncio.sleep(interval_seconds)

    async def _execute_cycle_core(
        self, interval_seconds: float
    ) -> None:
        """周期核心逻辑。"""
        self._logger.debug("[SelfEvolvingAgent] Cycle start")
        loop_start = time.monotonic()
        self._task_succeeded = False
        guardian_ok = await self._check_guardian(interval_seconds)
        if not guardian_ok:
            self._logger.warning(
                "[SelfEvolvingAgent] Cycle skipped by guardian"
            )
            return
        env_state = await self.perception.perceive()
        self._logger.debug("[SelfEvolvingAgent] Perception done")
        drive_signals = await self.drive_engine.compute(env_state)
        self._log_drives(drive_signals)
        prediction = self.predictor.predict_all(
            env_state.feature_vector
        )
        self._log_prediction(prediction)
        error = self.error_evaluator.evaluate(
            prediction.ensemble, env_state.feature_vector
        )
        self._log_error(error)
        self._record_error(error.mae)
        self._cycle_count += 1
        candidate_tasks = self.task_generator.generate(
            drive_signals, error
        )
        self._log_task_count(candidate_tasks)
        await self._handle_task_execution(
            candidate_tasks, drive_signals, env_state, prediction, error
        )
        self._update_predictor(env_state, self._task_succeeded)
        await self._sleep_remaining(loop_start, interval_seconds)
        self._logger.debug("[SelfEvolvingAgent] Cycle end")

    async def _check_guardian(self, interval_seconds: float) -> bool:
        """检查资源守护状态，返回是否继续执行。"""
        check = await self.guardian.check()
        self._logger.debug(
            f"[SelfEvolvingAgent] Guardian check: {check['status']}"
        )
        if not check["can_execute"]:
            self._logger.warning(
                "[SelfEvolvingAgent] Resource critical, skipping"
            )
            await asyncio.sleep(interval_seconds)
            return False
        return True

    def _log_drives(self, drives: Any) -> None:
        """记录驱力信号。"""
        self._logger.info(
            f"[SelfEvolvingAgent] Drives: "
            f"safety={drives.safety_reward:.3f}"
            f"(gap={drives.safety_gap:.3f}), "
            f"gain={drives.gain_reward:.3f}, "
            f"efficiency={drives.efficiency_reward:.3f}, "
            f"total={drives.total_reward:.3f}"
        )

    def _log_prediction(self, prediction: Any) -> None:
        """记录预测结果。"""
        self._logger.info(
            f"[SelfEvolvingAgent] Prediction "
            f"confidence={prediction.confidence:.3f}"
        )

    def _log_error(self, error: Any) -> None:
        """记录误差指标。"""
        self._logger.info(
            f"[SelfEvolvingAgent] Error: "
            f"mae={error.mae:.4f}, mse={error.mse:.4f}"
        )

    def _record_error(self, error_value: float) -> None:
        """记录误差到历史。"""
        self._recent_errors.append((time.time(), error_value))
        if len(self._recent_errors) > 20:
            self._recent_errors.pop(0)

    def _update_predictor(
        self, env_state: Any, learn: bool = True
    ) -> None:
        """用上一状态更新预测器并推进时序。"""
        if learn and self._previous_state is not None:
            self.predictor.update_all(
                self._previous_state, env_state.feature_vector
            )
            self._logger.debug(
                "[SelfEvolvingAgent] Predictor updated"
            )
        self._previous_state = env_state.feature_vector.copy()

    def _log_task_count(self, tasks: list) -> None:
        """记录生成任务数量。"""
        self._logger.info(
            f"[SelfEvolvingAgent] Generated {len(tasks)} tasks"
        )

    async def _sleep_remaining(
        self, loop_start: float, interval_seconds: float
    ) -> None:
        """睡眠至下一周期，使用单调时钟防跳变。"""
        elapsed = time.monotonic() - loop_start
        sleep_time = max(0.0, interval_seconds - elapsed)
        await asyncio.sleep(sleep_time)

    async def _handle_task_execution(
        self,
        candidate_tasks: list,
        drive_signals: Any,
        env_state: Any,
        prediction: Any,
        error: Any,
    ) -> None:
        """处理任务执行流程：先收割已完成的后台任务，再检查中断，最后启动新任务。"""
        await self._check_pending_result()
        await self._check_interrupt(drive_signals)
        try:
            await self._select_and_execute(
                candidate_tasks, drive_signals, env_state, prediction, error
            )
        finally:
            self._adapt_config_if_needed()

    async def _check_pending_result(self) -> None:
        """收割后台任务结果，完成则处理经验存储与情绪更新。"""
        if self._pending_execution is None:
            return
        if not self._pending_execution.done():
            return
        ctx = self._pending_context
        execution = self._pending_execution
        self._pending_execution = None
        self._pending_context = None
        selected = ctx.get("selected") if ctx else None
        try:
            result = execution.result()
            self._log_task_result(result)
            self._record_reward(result)
            self._update_emotion(ctx.get("error"), selected, result)
            await self._store_experience(
                ctx.get("env_state"),
                ctx.get("prediction"),
                ctx.get("drive_signals"),
                selected,
                result,
                ctx.get("error"),
            )
            self._task_succeeded = result.get("status") == "completed"
        except asyncio.CancelledError:
            self._logger.warning(
                "[SelfEvolvingAgent] Pending task was cancelled"
            )
            self._task_succeeded = False
        except Exception as exc:
            self._logger.error(
                f"[SelfEvolvingAgent] Pending task failed: {exc}"
            )
            self._task_succeeded = False
        finally:
            self._current_task = None

    async def _check_interrupt(self, drive_signals: Any) -> None:
        """检查是否需要中断当前运行中的后台任务。"""
        if not self._current_task:
            return
        should_interrupt = self.decision_engine.should_interrupt(
            self._current_task, drive_signals
        )
        if should_interrupt:
            self._interrupt_count += 1
            self._interrupt_history.append((time.time(), 1))
            if len(self._interrupt_history) > 20:
                self._interrupt_history.pop(0)
            self._logger.warning(
                f"[SelfEvolvingAgent] Interrupting task "
                f"{self._current_task.task_id}"
            )
            await self.task_executor.cancel(self._current_task)
            if self._pending_execution is not None:
                self._pending_execution.cancel()
                try:
                    await self._pending_execution
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    self._logger.warning(
                        f"[SelfEvolvingAgent] Interrupted task "
                        f"cleanup error: {exc}"
                    )
                self._pending_execution = None
                self._pending_context = None
            self._current_task = None

    async def _select_and_execute(
        self,
        candidate_tasks: list,
        drive_signals: Any,
        env_state: Any,
        prediction: Any,
        error: Any,
    ) -> None:
        """选择任务并在后台启动执行，使中断机制可跨周期生效。"""
        if self._current_task or not candidate_tasks:
            return
        self._apply_emotion_to_decision(error, candidate_tasks)
        selected = self.decision_engine.select(
            candidate_tasks, drive_signals
        )
        if not selected:
            self._logger.debug("[SelfEvolvingAgent] No task selected")
            return
        self._logger.info(
            f"[SelfEvolvingAgent] Selected task: {selected.name}"
        )
        self._current_task = selected
        self._pending_context = {
            "env_state": env_state,
            "prediction": prediction,
            "drive_signals": drive_signals,
            "selected": selected,
            "error": error,
        }
        self._pending_execution = asyncio.create_task(
            self.task_executor.execute(selected)
        )

    def _apply_emotion_to_decision(
        self, error: Any, candidate_tasks: list
    ) -> None:
        """将情绪状态应用到决策引擎探索率。"""
        adjusted_epsilon = self._emotion_engine.adjust_exploration_bias(
            self.decision_engine._epsilon
        )
        self.decision_engine.set_epsilon(adjusted_epsilon)

    def _update_emotion(
        self, error: Any, selected: Any, result: Dict[str, Any]
    ) -> None:
        """根据执行结果更新情绪状态。"""
        success = result.get("status") == "completed"
        self._emotion_engine.update(error.mae, selected.task_type, success)

    def _log_task_result(self, result: Dict[str, Any]) -> None:
        """记录任务结果。"""
        self._logger.info(
            f"[SelfEvolvingAgent] Task result: {result['status']}, "
            f"reward={result.get('reward', 0):.3f}"
        )

    def _record_reward(self, result: Dict[str, Any]) -> None:
        """记录奖励到历史。"""
        reward = result.get("reward", 0.0)
        self._recent_rewards.append((time.time(), reward))
        if len(self._recent_rewards) > 20:
            self._recent_rewards.pop(0)

    async def _store_experience(
        self,
        env_state: Any,
        prediction: Any,
        drive_signals: Any,
        selected: Any,
        result: Dict[str, Any],
        error: Any,
    ) -> None:
        """存储经验到记忆系统，并注入因果推理器。"""
        experience = Experience(
            timestamp=time.time(),
            state=env_state,
            prediction=prediction,
            drive_signals=drive_signals,
            selected_task=selected,
            execution_result=result,
            error_metrics=error,
            priority=selected.priority,
        )
        self._causal_reasoner.ingest(experience)
        await self.memory.store(experience)
        self._register_transfer_skill(experience, result)
        self._logger.debug(
            "[SelfEvolvingAgent] Experience stored"
        )

    def _register_transfer_skill(
        self, experience: Any, result: Dict[str, Any]
    ) -> None:
        """任务成功时将状态特征注册为迁移学习源技能。"""
        if result.get("status") != "completed":
            return
        if not hasattr(experience.state, "feature_vector"):
            return
        skill_name = (
            f"skill_{experience.selected_task.task_type}_"
            f"{int(experience.timestamp)}"
        )
        self._transfer_learner.register_source_skill(
            skill_name,
            experience.state.feature_vector,
            {"epsilon": self.decision_engine._epsilon},
        )
        sources = self._transfer_learner.list_sources()
        while len(sources) > 50:
            oldest = sources[0]
            del self._transfer_learner._source_skills[oldest]
            sources = self._transfer_learner.list_sources()

    async def run_offline_loop(self, interval_seconds: float) -> None:
        """离线复盘循环。"""
        self._logger.info(
            "[SelfEvolvingAgent] Offline loop started"
        )
        while self._running:
            try:
                await asyncio.sleep(interval_seconds)
                self._logger.info(
                    "[SelfEvolvingAgent] Starting offline review"
                )
                await self.memory.offline_review(self.predictor)
                self._apply_transfer_learning()
                self._logger.info(
                    "[SelfEvolvingAgent] Offline review completed"
                )
            except Exception as exc:
                self._logger.error(
                    f"[SelfEvolvingAgent] Offline error: {exc}\n"
                    f"{traceback.format_exc()}"
                )

    def _apply_transfer_learning(self) -> None:
        """从历史成功经验迁移知识到当前决策。"""
        if self._previous_state is None:
            return
        if not self._transfer_learner.list_sources():
            return
        source_name = self._transfer_learner.find_best_source(
            self._previous_state
        )
        if source_name is None:
            return
        params = self._transfer_learner.transfer_parameters(
            self._previous_state, "current"
        )
        if params and "epsilon" in params:
            new_epsilon = float(params["epsilon"])
            self.decision_engine.set_epsilon(new_epsilon)
            self._logger.info(
                f"[SelfEvolvingAgent] Transfer learning: "
                f"epsilon={new_epsilon:.3f} from {source_name}"
            )

    async def start(
        self, online_interval_seconds: float, offline_interval_seconds: float
    ) -> None:
        """启动Agent。"""
        if not self._initialized:
            raise ModuleNotInitializedException(
                "Agent must be initialized before start"
            )
        if self._running:
            self._logger.warning("[SelfEvolvingAgent] Already running")
            return
        self._running = True
        self._logger.info("[SelfEvolvingAgent] Starting loops")
        self._online_task = asyncio.create_task(
            self.run_online_loop(online_interval_seconds)
        )
        self._offline_task = asyncio.create_task(
            self.run_offline_loop(offline_interval_seconds)
        )
        self._diagnosis_task = asyncio.create_task(
            self._self_healing.run_diagnosis_loop(5.0)
        )

    async def stop(self) -> None:
        """停止Agent。"""
        if not self._running:
            self._logger.warning("[SelfEvolvingAgent] Not running")
            return
        self._running = False
        self._logger.info("[SelfEvolvingAgent] Stopping...")
        self._self_healing.stop()
        await self._cancel_task(self._online_task)
        await self._cancel_task(self._offline_task)
        await self._cancel_task(self._diagnosis_task)
        await self._cancel_task(self._pending_execution)
        self._online_task = None
        self._offline_task = None
        self._diagnosis_task = None
        self._pending_execution = None
        self._pending_context = None
        self._current_task = None
        await self._shutdown_modules()
        self._dashboard.stop()
        self._initialized = False
        self._logger.info("[SelfEvolvingAgent] Stopped")

    async def _cancel_task(self, task: Optional[asyncio.Task]) -> None:
        """取消异步任务，捕获所有异常防传播。"""
        if not task:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            self._logger.debug(
                f"[SelfEvolvingAgent] Task cancel cleanup: {exc}"
            )

    async def _shutdown_modules(self) -> None:
        """关闭所有模块，单个失败不影响其他。"""
        results = await asyncio.gather(
            self.perception.shutdown(),
            self.drive_engine.shutdown(),
            self.predictor.shutdown(),
            self.task_generator.shutdown(),
            self.decision_engine.shutdown(),
            self.memory.shutdown(),
            return_exceptions=True,
        )
        names = [
            "perception", "drive_engine", "predictor",
            "task_generator", "decision_engine", "memory",
        ]
        for name, result in zip(names, results):
            if isinstance(result, Exception):
                self._logger.error(
                    f"[SelfEvolvingAgent] {name} shutdown failed: {result}"
                )

    async def health_check(self) -> Dict[str, Any]:
        """全系统健康检查。"""
        checks = await asyncio.gather(
            self.perception.health_check(),
            self.drive_engine.health_check(),
            self.predictor.health_check(),
            self.task_generator.health_check(),
            self.decision_engine.health_check(),
            self.memory.health_check(),
            self.guardian.check(),
            return_exceptions=True,
        )
        names = [
            "perception",
            "drive_engine",
            "predictor",
            "task_generator",
            "decision_engine",
            "memory",
            "guardian",
        ]
        return self._build_health_result(checks, names)

    def _build_health_result(
        self, checks: tuple, names: list[str]
    ) -> Dict[str, Any]:
        """构建健康检查结果。"""
        safe_checks = []
        for check in checks:
            if isinstance(check, Exception):
                safe_checks.append(
                    {"status": "error", "error": str(check)}
                )
            else:
                safe_checks.append(check)
        all_healthy = all(
            c.get("status") in ("healthy", "safe", "warning")
            for c in safe_checks
        )
        return {
            "status": "healthy" if all_healthy else "degraded",
            "modules": {
                name: check
                for name, check in zip(names, safe_checks)
            },
        }

    def _adapt_config_if_needed(self) -> None:
        """根据近期运行指标自适应调整配置。"""
        if len(self._recent_errors) >= 5:
            self._config_manager.adapt_exploration_rate(
                self._recent_errors
            )
        if len(self._recent_rewards) >= 5:
            self._config_manager.adapt_epsilon(
                self._recent_rewards
            )
        if self._interrupt_count >= 3:
            self._config_manager.adapt_interrupt_threshold(
                self._interrupt_history
            )
            self._interrupt_count = 0

    def _get_runtime_state(self) -> Dict[str, Any]:
        """获取运行时状态快照。"""
        return {
            "status": "running" if self._running else "stopped",
            "cycle_count": self._cycle_count,
            "recent_errors": self._recent_errors[-5:],
            "recent_rewards": self._recent_rewards[-5:],
            "interrupt_count": self._interrupt_count,
            "config": self._config_manager.get_all(),
            "current_task": (
                self._current_task.name
                if self._current_task
                else None
            ),
        }

    def _register_modules_for_healing(self) -> None:
        """注册各模块到自愈系统，恢复动作为带配置的闭包。"""
        saved_config = self._config

        async def recover_perception() -> None:
            await self.perception.initialize(
                saved_config.get("perception", {})
            )

        async def recover_drive() -> None:
            await self.drive_engine.initialize(
                saved_config.get("drive_engine", {})
            )

        async def recover_predictor() -> None:
            await self.predictor.initialize(
                saved_config.get("predictor", {})
            )

        async def recover_memory() -> None:
            await self.memory.initialize(
                saved_config.get("memory", {})
            )

        async def recover_task_gen() -> None:
            await self.task_generator.initialize(
                saved_config.get("task_generator", {})
            )

        async def recover_decision() -> None:
            await self.decision_engine.initialize(
                saved_config.get("decision_engine", {})
            )

        self._self_healing.register_module(
            "perception",
            self.perception.health_check,
            recover_perception,
        )
        self._self_healing.register_module(
            "drive_engine",
            self.drive_engine.health_check,
            recover_drive,
        )
        self._self_healing.register_module(
            "predictor",
            self.predictor.health_check,
            recover_predictor,
        )
        self._self_healing.register_module(
            "memory",
            self.memory.health_check,
            recover_memory,
        )
        self._self_healing.register_module(
            "task_generator",
            self.task_generator.health_check,
            recover_task_gen,
        )
        self._self_healing.register_module(
            "decision_engine",
            self.decision_engine.health_check,
            recover_decision,
        )
