"""
帕累托多目标选择器模块。

支持安全、收益、能效三维目标的帕累托前沿决策。

第一性原理：
- 真实决策 rarely 单目标，需权衡多维度
- 帕累托前沿提供非支配解集，避免局部最优
- 动态偏好根据驱力缺口自适应调整
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from agent_core.common.data_contracts import DriveSignals, Task


class ParetoSelector:
    """
    帕累托多目标选择器。
    """

    def __init__(self) -> None:
        self._objectives = ["safety", "gain", "efficiency"]

    def select(
        self,
        tasks: List[Task],
        drive_signals: DriveSignals,
    ) -> Optional[Task]:
        """
        从任务池中选择帕累托最优任务。

        Args:
            tasks: 任务对象列表。
            drive_signals: 驱力信号对象。

        Returns:
            选中的任务对象。
        """
        if not tasks:
            return None
        objectives = self._extract_objectives(tasks)
        fronts = self._non_dominated_sort(objectives)
        if not fronts or not fronts[0]:
            return tasks[0]
        best_front = fronts[0]
        selected = self._select_by_preference(
            best_front, tasks, drive_signals
        )
        return selected

    def _extract_objectives(
        self, tasks: List[Task]
    ) -> np.ndarray:
        """
        提取任务的多目标向量。

        目标维度：[安全收益, 经济收益, 能效收益, -成本]。

        Args:
            tasks: 任务列表。

        Returns:
            目标矩阵，形状为 (n_tasks, n_objectives)。
        """
        matrix = []
        for task in tasks:
            safety = 1.0 if task.task_type == "safety" else 0.3
            gain = task.expected_reward if task.task_type == "gain" else 0.2
            efficiency = (
                1.0 - task.expected_cost
                if task.task_type == "efficiency"
                else 0.3
            )
            cost = -task.expected_cost
            matrix.append([safety, gain, efficiency, cost])
        return np.array(matrix, dtype=np.float32)

    def _non_dominated_sort(
        self, objectives: np.ndarray
    ) -> List[List[int]]:
        """
        非支配排序。

        Args:
            objectives: 目标矩阵。

        Returns:
            帕累托前沿列表，每个前沿是任务索引列表。
        """
        n = len(objectives)
        dominated_counts = [0] * n
        dominated_sets: List[List[int]] = [[] for _ in range(n)]
        fronts: List[List[int]] = [[]]

        for i in range(n):
            for j in range(i + 1, n):
                dom_i = self._dominates(objectives[i], objectives[j])
                dom_j = self._dominates(objectives[j], objectives[i])
                if dom_i:
                    dominated_sets[i].append(j)
                    dominated_counts[j] += 1
                elif dom_j:
                    dominated_sets[j].append(i)
                    dominated_counts[i] += 1
            if dominated_counts[i] == 0:
                fronts[0].append(i)

        current_front = 0
        while fronts[current_front]:
            next_front: List[int] = []
            for i in fronts[current_front]:
                for j in dominated_sets[i]:
                    dominated_counts[j] -= 1
                    if dominated_counts[j] == 0:
                        next_front.append(j)
            current_front += 1
            fronts.append(next_front)

        return fronts[:-1]

    def _dominates(self, a: np.ndarray, b: np.ndarray) -> bool:
        """
        判断向量a是否支配向量b。

        Args:
            a: 向量a。
            b: 向量b。

        Returns:
            a支配b返回True。
        """
        better = np.all(a >= b)
        strictly_better = np.any(a > b)
        return better and strictly_better

    def _select_by_preference(
        self,
        front_indices: List[int],
        tasks: List[Task],
        drive_signals: DriveSignals,
    ) -> Task:
        """
        根据驱力偏好从帕累托前沿中选择任务。

        Args:
            front_indices: 前沿任务索引。
            tasks: 全部任务列表。
            drive_signals: 驱力信号。

        Returns:
            选中的任务。
        """
        gaps = np.array(
            [
                drive_signals.safety_gap,
                drive_signals.gain_gap,
                drive_signals.efficiency_gap,
            ],
            dtype=np.float32,
        )
        weights = gaps / (np.sum(gaps) + 1e-10)
        best_score = -1.0
        best_index = front_indices[0]
        for idx in front_indices:
            task = tasks[idx]
            score = self._compute_preference_score(task, weights)
            if score > best_score:
                best_score = score
                best_index = idx
        return tasks[best_index]

    def _compute_preference_score(
        self, task: Task, weights: np.ndarray
    ) -> float:
        """
        计算任务偏好得分。

        Args:
            task: 任务对象。
            weights: 三维权重 [安全, 收益, 能效]。

        Returns:
            偏好得分。
        """
        type_index = {"safety": 0, "gain": 1, "efficiency": 2}.get(
            task.task_type, 1
        )
        base = weights[type_index]
        reward_bonus = task.expected_reward * 0.3
        cost_penalty = task.expected_cost * 0.2
        return base + reward_bonus - cost_penalty
