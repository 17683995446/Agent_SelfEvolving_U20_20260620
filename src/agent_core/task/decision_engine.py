"""
决策引擎模块。

任务选择与行为控制。
"""

import random
import time
from typing import Any, Dict, List, Optional

import numpy as np

from agent_core.common.data_contracts import DriveSignals, Task
from agent_core.common.interfaces import IDecisionEngine
from agent_core.common.exceptions import ModuleNotInitializedException
from agent_core.common.constants import (
    EPSILON_DEFAULT,
    INTERRUPT_THRESHOLD_DEFAULT,
    SAFETY_WEIGHT_EMERGENCY,
    TASK_TIMEOUT_SECONDS,
)
from agent_core.task.pareto_selector import ParetoSelector

_REWARD_WEIGHT = 0.4
_COST_WEIGHT = 0.4
_NOVELTY_WEIGHT = 0.2
_EXPLORE_TEMPERATURE = 2.0
_COST_RATIO_THRESHOLD = 0.5
_SOFTMAX_STABLE_EPS = 1e-10


class DecisionEngine(IDecisionEngine):
    """
    决策引擎实现。
    """

    def __init__(self) -> None:
        self._epsilon = EPSILON_DEFAULT
        self._interrupt_threshold = INTERRUPT_THRESHOLD_DEFAULT
        self._current_task: Optional[Task] = None
        self._task_start_time: Optional[float] = None
        self._initialized = False
        self._config: Dict[str, Any] = {}
        self._pareto_selector = ParetoSelector()
        self._use_pareto = False

    def _get_current_time(self) -> float:
        return time.time()

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "DecisionEngine"

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化决策引擎。"""
        self._config = config
        self._epsilon = config.get("epsilon", EPSILON_DEFAULT)
        self._interrupt_threshold = config.get(
            "interrupt_threshold", INTERRUPT_THRESHOLD_DEFAULT
        )
        self._use_pareto = config.get("use_pareto", False)
        self._initialized = True
        return True

    def select(
        self, tasks: List[Task], drive_signals: DriveSignals
    ) -> Optional[Task]:
        """从任务池中选择最优任务。"""
        if not self._initialized:
            raise ModuleNotInitializedException("DecisionEngine not initialized")
        valid_tasks = self._filter_valid(tasks)
        if not valid_tasks:
            return None
        selected = self._pick_task(valid_tasks, drive_signals)
        self._current_task = selected
        self._task_start_time = self._get_current_time()
        return selected

    def _filter_valid(self, tasks: List[Task]) -> List[Task]:
        return [
            t for t in tasks
            if t.expected_reward > t.expected_cost * _COST_RATIO_THRESHOLD
        ]

    def _pick_task(self, tasks: List[Task], drives: DriveSignals) -> Optional[Task]:
        if self._use_pareto:
            return self._pareto_selector.select(tasks, drives)
        scored = self._score_tasks(tasks, drives)
        return self._choose_task(scored)

    def _score_tasks(
        self, tasks: List[Task], drive_signals: DriveSignals
    ) -> List[tuple[Task, float]]:
        scored: List[tuple[Task, float]] = []
        for task in tasks:
            score = task.compute_score(
                {"reward": _REWARD_WEIGHT, "cost": _COST_WEIGHT, "novelty": _NOVELTY_WEIGHT}
            )
            multiplier = 1.0 + drive_signals.weights.get(task.task_type, 0.33)
            scored.append((task, score * multiplier))
        return scored

    def _choose_task(self, scored: List[tuple[Task, float]]) -> Task:
        if random.random() < self._epsilon:
            return self._explore(scored)
        return self._select_best(scored)

    def _select_best(self, scored: List[tuple[Task, float]]) -> Task:
        best_score = max(s for _, s in scored)
        tied = [t for t, s in scored if abs(s - best_score) < 1e-9]
        if len(tied) > 1:
            return random.choice(tied)
        return max(scored, key=lambda x: x[1])[0]

    def _explore(self, scored: List[tuple[Task, float]]) -> Task:
        scores = np.array([s for _, s in scored])
        max_score = np.max(scores)
        scores = scores - max_score
        exp_scores = np.exp(scores * _EXPLORE_TEMPERATURE)
        sum_exp = np.sum(exp_scores)
        if sum_exp < _SOFTMAX_STABLE_EPS or np.isnan(sum_exp):
            return scored[0][0]
        probs = exp_scores / sum_exp
        index = int(np.random.choice(len(scored), p=probs))
        return scored[index][0]

    def should_interrupt(self, current_task: Task, new_drives: DriveSignals) -> bool:
        """判断是否应该中断当前任务。"""
        if self._safety_gap_critical(new_drives, current_task):
            return True
        if self._task_timeout():
            return True
        if self._safety_weight_critical(new_drives, current_task):
            return True
        return False

    def _safety_gap_critical(self, drives: DriveSignals, task: Task) -> bool:
        if drives.safety_gap <= self._interrupt_threshold:
            return False
        return task.task_type != "safety"

    def _task_timeout(self) -> bool:
        if self._task_start_time is None:
            return False
        elapsed = self._get_current_time() - self._task_start_time
        return elapsed > TASK_TIMEOUT_SECONDS

    def _safety_weight_critical(self, drives: DriveSignals, task: Task) -> bool:
        if drives.weights.get("safety", 0.0) <= SAFETY_WEIGHT_EMERGENCY:
            return False
        return task.task_type != "safety"

    async def health_check(self) -> Dict[str, Any]:
        """健康检查。"""
        status = "healthy" if self._initialized else "unhealthy"
        task_id = None
        if self._current_task is not None:
            task_id = self._current_task.task_id
        return {
            "status": status,
            "metrics": {
                "epsilon": self._epsilon,
                "current_task": task_id,
            },
        }

    def set_epsilon(self, epsilon: float) -> None:
        """
        设置探索率。

        Args:
            epsilon: 探索率值 [0, 1]。
        """
        self._epsilon = float(max(0.0, min(1.0, epsilon)))

    async def shutdown(self) -> None:
        """优雅关闭。"""
        self._initialized = False
        self._current_task = None
        self._task_start_time = None
