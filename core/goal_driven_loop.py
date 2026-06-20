"""
目标驱动循环（阶段1：从驱力反射到目标规划）

第一性原理：生物体的行为模式从"反射驱动"（刺激→反应）升级到"目标驱动"
（目标→规划→行动→评估）。人类不仅能对当前刺激做反应，还能为"未来想要达成的
状态"制定多步计划并持续推进。

GoalDrivenLoop 封装这一升级：
  1. set_long_task() — 设定长任务，自动分解为子目标序列
  2. execute_step() — 执行一步：取当前子目标→生成动作→执行→更新进度→推进
  3. 断点续传 — 目标状态持久化到JSON，重启后恢复
  4. 工作记忆 — 跨步骤保持当前子目标上下文

与原驱力驱动的关系：
  - 有活跃长任务目标 → 走目标驱动（优先）
  - 无长任务目标 → 回退到驱力驱动（原逻辑）
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from core.goals import Goal, GoalManager, GoalGenerator, ValueAlignment
from core.interfaces import IGoalDrivenLoop
from memory.working_memory import WorkingMemory


class GoalDrivenLoop(IGoalDrivenLoop):
    """
    目标驱动循环

    核心方法（<=7个）：
    1. set_long_task() — 设定长任务并分解
    2. has_active_goal() — 是否有活跃长任务
    3. get_current_subgoal() — 获取当前子目标
    4. execute_step() — 执行一步目标驱动
    5. update_progress() — 更新子目标进度
    6. persist() / load() — 断点续传
    7. get_status() — 状态查询
    """

    def __init__(self,
                 agent_id: str,
                 working_memory: Optional[WorkingMemory] = None,
                 logger=None):
        """
        Args:
            agent_id: Agent标识
            working_memory: 工作记忆（跨步骤上下文保持），None则自建
            logger: 日志器
        """
        self.agent_id = agent_id
        self.goal_manager = GoalManager(agent_id=agent_id)
        self.working_memory = working_memory or WorkingMemory(capacity=7)
        self.logger = logger
        # 当前执行的子目标ID（None=无活跃子目标）
        self._current_subgoal_id: Optional[str] = None
        # 子目标执行步骤计数（用于进度估算）
        self._subgoal_step_counts: Dict[str, int] = {}
        # 子目标预期总步数（用于进度估算）
        self._subgoal_expected_steps: Dict[str, int] = {}
        # 已完成子目标记录（用于断点续传时跳过）
        self._completed_subgoals: List[str] = []

    def set_long_task(self,
                      description: str,
                      sub_tasks: List[str],
                      priority: float = 0.8,
                      deadline_hours: float = 1.0,
                      steps_per_subgoal: int = 10) -> str:
        """
        设定长任务并分解为子目标序列

        第一性原理：长任务无法一步完成，必须分解为可执行的子目标序列，
        每个子目标有明确的完成标准和时间预算。

        Args:
            description: 长任务描述
            sub_tasks: 子任务描述列表（按执行顺序）
            priority: 优先级 0-1
            deadline_hours: 截止时间（小时）
            steps_per_subgoal: 每个子目标预期执行步数（用于进度估算）

        Returns:
            父目标ID
        """
        if not sub_tasks:
            return ""

        # 创建父目标
        parent_goal = Goal(
            goal_id=self.goal_manager._generator._next_id(),
            description=description,
            priority=priority,
            deadline=time.time() + deadline_hours * 3600,
            metadata={"type": "long_task", "subtask_count": len(sub_tasks)},
        )
        self.goal_manager.add_goal(parent_goal)

        # 分解为子目标
        sub_goals = self.goal_manager._generator.decompose(
            goal=parent_goal,
            sub_tasks=sub_tasks,
        )
        for sg in sub_goals:
            self.goal_manager.add_goal(sg)
            self._subgoal_expected_steps[sg.goal_id] = steps_per_subgoal
            self._subgoal_step_counts[sg.goal_id] = 0

        # 设定第一个子目标为当前执行目标
        if sub_goals:
            self._current_subgoal_id = sub_goals[0].goal_id

        if self.logger:
            self.logger.info(
                f"Long task set: {description} "
                f"({len(sub_goals)} subgoals, deadline={deadline_hours}h)"
            )

        return parent_goal.goal_id

    def has_active_goal(self) -> bool:
        """是否有活跃的长任务子目标待执行"""
        return self._current_subgoal_id is not None

    def get_current_subgoal(self) -> Optional[Goal]:
        """获取当前执行的子目标"""
        if self._current_subgoal_id is None:
            return None
        return self.goal_manager._goals.get(self._current_subgoal_id)

    def execute_step(self,
                     state_vector: np.ndarray,
                     action_executor: callable) -> Dict[str, Any]:
        """
        执行一步目标驱动

        第一性原理：每一步都包含"感知当前状态→回忆目标→执行动作→评估进度→推进"。

        流程：
            1. 取当前子目标
            2. 把子目标描述编码到工作记忆（上下文保持）
            3. 调用 action_executor(subgoal_description, state_vector) 执行动作
            4. 根据执行结果更新子目标进度
            5. 子目标完成则推进到下一个；全部完成则标记父目标完成

        Args:
            state_vector: 当前状态向量
            action_executor: 动作执行回调，签名 (description, state_vector) -> Dict
                             返回的Dict应包含 "success": bool

        Returns:
            执行结果Dict
        """
        subgoal = self.get_current_subgoal()
        if subgoal is None:
            return {"status": "no_active_goal"}

        # 1. 工作记忆：存入当前子目标上下文（跨步骤保持）
        self.working_memory.store(state_vector, source="goal_context")

        # 2. 执行动作
        result = action_executor(subgoal.description, state_vector)
        success = result.get("success", False)

        # 3. 更新步数计数
        gid = subgoal.goal_id
        self._subgoal_step_counts[gid] = self._subgoal_step_counts.get(gid, 0) + 1
        expected = self._subgoal_expected_steps.get(gid, 10)

        # 4. 估算进度：成功执行累积到预期步数则完成
        if success:
            progress = min(1.0, self._subgoal_step_counts[gid] / expected)
        else:
            # 失败也推进进度（但更慢），避免卡死
            progress = min(0.9, self._subgoal_step_counts[gid] / (expected * 2))

        self.goal_manager.update_progress(gid, progress)

        # 5. 子目标完成 → 推进到下一个
        if progress >= 1.0:
            self._advance_to_next_subgoal(subgoal)

        return {
            "status": "executing",
            "subgoal_id": gid,
            "subgoal_description": subgoal.description,
            "step": self._subgoal_step_counts[gid],
            "expected_steps": expected,
            "progress": progress,
            "success": success,
            "result": result,
        }

    def _advance_to_next_subgoal(self, completed_subgoal: Goal) -> None:
        """推进到下一个子目标"""
        # 标记完成
        self.goal_manager.complete_goal(completed_subgoal.goal_id)
        self._completed_subgoals.append(completed_subgoal.goal_id)

        # 找父目标的下一个未完成子目标
        parent_id = completed_subgoal.parent_id
        if parent_id is None:
            self._current_subgoal_id = None
            return

        parent = self.goal_manager._goals.get(parent_id)
        if parent is None:
            self._current_subgoal_id = None
            return

        # 遍历子目标ID列表，找第一个未完成的
        for sg_id in parent.sub_goals:
            sg = self.goal_manager._goals.get(sg_id)
            if sg and not sg.completed:
                self._current_subgoal_id = sg_id
                if self.logger:
                    self.logger.info(
                        f"Subgoal advanced: {sg.description} "
                        f"(step {self._subgoal_step_counts.get(sg_id, 0)})"
                    )
                return

        # 所有子目标完成 → 标记父目标完成
        self.goal_manager.complete_goal(parent_id)
        self._current_subgoal_id = None
        if self.logger:
            self.logger.info(
                f"Long task completed: {parent.description}"
            )

    def update_progress(self, goal_id: str, progress: float) -> None:
        """手动更新目标进度"""
        self.goal_manager.update_progress(goal_id, progress)

    def get_status(self) -> Dict[str, Any]:
        """获取目标驱动状态"""
        subgoal = self.get_current_subgoal()
        parent_id = subgoal.parent_id if subgoal else None
        parent = self.goal_manager._goals.get(parent_id) if parent_id else None

        return {
            "has_active_goal": self.has_active_goal(),
            "current_subgoal": {
                "id": subgoal.goal_id,
                "description": subgoal.description,
                "progress": subgoal.progress,
                "step": self._subgoal_step_counts.get(subgoal.goal_id, 0),
                "expected_steps": self._subgoal_expected_steps.get(subgoal.goal_id, 0),
            } if subgoal else None,
            "parent_goal": {
                "id": parent.goal_id,
                "description": parent.description,
                "progress": parent.progress,
                "sub_goals_total": len(parent.sub_goals),
                "sub_goals_completed": sum(
                    1 for sg_id in parent.sub_goals
                    if self.goal_manager._goals.get(sg_id)
                    and self.goal_manager._goals[sg_id].completed
                ),
            } if parent else None,
            "goal_manager_stats": self.goal_manager.get_stats(),
            "working_memory_stats": self.working_memory.get_stats(),
            "completed_subgoals": len(self._completed_subgoals),
        }

    def persist(self, path: Path) -> bool:
        """持久化目标状态到JSON（断点续传）"""
        try:
            data = {
                "agent_id": self.agent_id,
                "current_subgoal_id": self._current_subgoal_id,
                "subgoal_step_counts": self._subgoal_step_counts,
                "subgoal_expected_steps": self._subgoal_expected_steps,
                "completed_subgoals": self._completed_subgoals,
                "goals": {
                    gid: {
                        "goal_id": g.goal_id,
                        "description": g.description,
                        "priority": g.priority,
                        "deadline": g.deadline,
                        "parent_id": g.parent_id,
                        "sub_goals": g.sub_goals,
                        "progress": g.progress,
                        "completed": g.completed,
                        "created_at": g.created_at,
                        "metadata": g.metadata,
                    }
                    for gid, g in self.goal_manager._goals.items()
                },
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to persist goals: {e}")
            return False

    def load(self, path: Path) -> bool:
        """从JSON加载目标状态（断点续传）"""
        try:
            if not path.exists():
                return False
            data = json.loads(path.read_text(encoding="utf-8"))

            self._current_subgoal_id = data.get("current_subgoal_id")
            self._subgoal_step_counts = data.get("subgoal_step_counts", {})
            self._subgoal_expected_steps = data.get("subgoal_expected_steps", {})
            self._completed_subgoals = data.get("completed_subgoals", [])

            # 重建目标
            self.goal_manager._goals.clear()
            for gid, gdata in data.get("goals", {}).items():
                goal = Goal(
                    goal_id=gdata["goal_id"],
                    description=gdata["description"],
                    priority=gdata["priority"],
                    deadline=gdata.get("deadline"),
                    parent_id=gdata.get("parent_id"),
                    sub_goals=gdata.get("sub_goals", []),
                    progress=gdata.get("progress", 0.0),
                    completed=gdata.get("completed", False),
                    created_at=gdata.get("created_at", time.time()),
                    metadata=gdata.get("metadata", {}),
                )
                self.goal_manager._goals[gid] = goal

            # 如果当前子目标已完成（手动标记），推进
            curr = self.get_current_subgoal()
            if curr and curr.completed:
                self._advance_to_next_subgoal(curr)

            if self.logger:
                self.logger.info(
                    f"Goals loaded: {len(self.goal_manager._goals)} goals, "
                    f"current_subgoal={self._current_subgoal_id}"
                )
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to load goals: {e}")
            return False
