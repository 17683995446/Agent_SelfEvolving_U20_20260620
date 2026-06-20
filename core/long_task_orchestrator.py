"""
自驱长任务执行引擎（阶段4：从目标驱动到自驱长任务编排）

第一性原理：复杂长任务需要"规划→分派→执行→检查→推进"的闭环。
  - 规划：把长任务分解为阶段（phase）和步骤（step）
  - 分派：每步决定本地执行（用技能）还是委派（给其他agent）
  - 执行：调用技能或委派执行
  - 检查：验证执行结果，失败则重试或降级
  - 推进：完成后推进到下一步/下一阶段，支持断点续传

LongTaskOrchestrator 整合前3个阶段的能力：
  - 阶段1 GoalDrivenLoop：目标分解与进度追踪
  - 阶段2 SkillLibrary：技能调用执行步骤
  - 阶段3 MultiAgentCollaborator：委派步骤给其他agent

核心方法（<=7个）：
  1. start_task() — 启动长任务（分解为阶段+步骤）
  2. execute_next() — 执行下一步
  3. checkpoint() — 保存断点
  4. resume() — 从断点恢复
  5. get_progress() — 获取进度
  6. delegate_step() — 委派步骤给其他agent
  7. get_status() — 状态
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.skill_library import SkillLibrary
from core.multi_agent_collaborator import MultiAgentCollaborator
from core.interfaces import ILongTaskOrchestrator


class StepStatus(Enum):
    """步骤状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DELEGATED = "delegated"  # 已委派给其他agent
    SKIPPED = "skipped"      # 跳过（重试耗尽后降级）


class TaskStatus(Enum):
    """长任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskStep:
    """任务步骤"""
    step_id: str
    description: str
    phase: int                                    # 属于哪个阶段（0-indexed）
    status: StepStatus = StepStatus.PENDING
    skill_name: Optional[str] = None              # 用哪个技能执行
    skill_kwargs: Dict[str, Any] = field(default_factory=dict)  # 技能参数
    delegate_to: Optional[str] = None             # 委派给哪个agent（None=本地执行）
    delegate_capability: Optional[str] = None     # 委派所需能力
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    retry_count: int = 0
    max_retries: int = 2

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class LongTask:
    """长任务"""
    task_id: str
    description: str
    phases: List[List[TaskStep]]                  # 按阶段分组的步骤
    current_phase: int = 0
    current_step: int = 0                         # 当前阶段内的步骤索引
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def total_steps(self) -> int:
        return sum(len(phase) for phase in self.phases)

    def completed_steps(self) -> int:
        count = 0
        for phase in self.phases:
            for step in phase:
                if step.status in (StepStatus.COMPLETED, StepStatus.SKIPPED):
                    count += 1
        return count

    def progress(self) -> float:
        total = self.total_steps()
        if total == 0:
            return 0.0
        return self.completed_steps() / total

    def get_current_step(self) -> Optional[TaskStep]:
        if self.current_phase >= len(self.phases):
            return None
        phase = self.phases[self.current_phase]
        if self.current_step >= len(phase):
            return None
        return phase[self.current_step]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "current_phase": self.current_phase,
            "current_step": self.current_step,
            "status": self.status.value,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "total_steps": self.total_steps(),
            "completed_steps": self.completed_steps(),
            "progress": self.progress(),
            "phases": [[s.to_dict() for s in phase] for phase in self.phases],
        }


class LongTaskOrchestrator(ILongTaskOrchestrator):
    """
    长任务编排器

    整合目标驱动、技能库、多agent协作，实现自驱长任务执行。

    核心方法（<=7个）：
    1. start_task() — 启动长任务
    2. execute_next() — 执行下一步
    3. checkpoint() — 保存断点
    4. resume() — 从断点恢复
    5. get_progress() — 获取进度
    6. delegate_step() — 委派步骤
    7. get_status() — 状态
    """

    def __init__(self,
                 agent_id: str,
                 skill_library: Optional[SkillLibrary] = None,
                 collaborator: Optional[MultiAgentCollaborator] = None,
                 checkpoint_dir: str = "./data/checkpoints",
                 logger=None):
        """
        Args:
            agent_id: Agent ID
            skill_library: 技能库（用于本地执行步骤）
            collaborator: 多agent协作器（用于委派步骤）
            checkpoint_dir: 断点文件目录
            logger: 日志器
        """
        self.agent_id = agent_id
        self.skill_library = skill_library
        self.collaborator = collaborator
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger

        self._current_task: Optional[LongTask] = None
        self._step_handlers: Dict[str, Callable[[TaskStep], Any]] = {}

        # 统计
        self._total_tasks_started = 0
        self._total_tasks_completed = 0
        self._total_steps_executed = 0
        self._total_steps_delegated = 0
        self._total_steps_failed = 0

    # ========================================================================
    # 公开方法
    # ========================================================================

    def start_task(self,
                   description: str,
                   phases: List[List[Dict[str, Any]]],
                   metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        启动长任务

        第一性原理：长任务无法一步完成，必须分解为阶段和步骤。
        每个步骤指定用哪个技能执行，或委派给哪个agent。

        Args:
            description: 长任务描述
            phases: 阶段列表，每个阶段是步骤列表。
                    每个步骤是dict，包含：
                    - description: 步骤描述
                    - skill_name: 技能名（本地执行）
                    - skill_kwargs: 技能参数
                    - delegate_to: 委派目标agent
                    - delegate_capability: 委派所需能力
            metadata: 元数据

        Returns:
            task_id
        """
        task_id = f"longtask_{self.agent_id}_{int(time.time() * 1000)}"

        # 构建步骤
        built_phases: List[List[TaskStep]] = []
        for phase_idx, phase_steps in enumerate(phases):
            phase: List[TaskStep] = []
            for step_spec in phase_steps:
                step = TaskStep(
                    step_id=f"{task_id}_p{phase_idx}_s{len(phase)}",
                    description=step_spec.get("description", ""),
                    phase=phase_idx,
                    skill_name=step_spec.get("skill_name"),
                    skill_kwargs=step_spec.get("skill_kwargs", {}),
                    delegate_to=step_spec.get("delegate_to"),
                    delegate_capability=step_spec.get("delegate_capability"),
                    max_retries=step_spec.get("max_retries", 2),
                )
                phase.append(step)
            built_phases.append(phase)

        self._current_task = LongTask(
            task_id=task_id,
            description=description,
            phases=built_phases,
            metadata=metadata or {},
        )
        self._current_task.status = TaskStatus.RUNNING
        self._total_tasks_started += 1

        if self.logger:
            self.logger.info(
                f"LongTask started: {task_id} "
                f"phases={len(built_phases)} "
                f"steps={self._current_task.total_steps()}"
            )

        return task_id

    def execute_next(self) -> Dict[str, Any]:
        """
        执行下一步

        第一性原理：自驱执行——每步自动决定执行方式（本地技能 or 委派），
        执行后检查结果，失败则重试，重试耗尽则降级跳过。

        Returns:
            {"status": str, "step": dict, "result": Any, "error": str}
        """
        if self._current_task is None:
            return {"status": "no_task", "step": None, "result": None, "error": "无活跃任务"}

        # 任务已完成
        if self._current_task.status == TaskStatus.COMPLETED:
            return {"status": "task_completed", "step": None, "result": None, "error": None}

        if self._current_task.status != TaskStatus.RUNNING:
            return {"status": "not_running", "step": None, "result": None,
                    "error": f"任务状态={self._current_task.status.value}"}

        step = self._current_task.get_current_step()
        if step is None:
            # 所有步骤完成
            self._complete_task()
            return {"status": "task_completed", "step": None, "result": None, "error": None}

        # 执行步骤
        step.status = StepStatus.RUNNING
        step.started_at = time.time()

        result = None
        error = None
        success = False

        try:
            if step.delegate_to or step.delegate_capability:
                # 委派执行
                success, result, error = self._execute_delegated(step)
            elif step.skill_name:
                # 本地技能执行
                success, result, error = self._execute_with_skill(step)
            else:
                # 无技能无委派，用注册的handler
                success, result, error = self._execute_with_handler(step)

            if success:
                step.status = StepStatus.COMPLETED
                step.result = result
                step.completed_at = time.time()
                self._total_steps_executed += 1
                self._advance_step()
                status = "step_completed"
            else:
                step.retry_count += 1
                if step.retry_count >= step.max_retries:
                    # 重试耗尽，降级跳过（SKIPPED计入进度，避免卡死）
                    step.status = StepStatus.SKIPPED
                    step.error = error
                    step.completed_at = time.time()
                    self._total_steps_failed += 1
                    self._advance_step()
                    status = "step_failed_skipped"
                else:
                    step.status = StepStatus.PENDING  # 重置为待执行，下次重试
                    status = "step_retry"

        except Exception as e:
            step.retry_count += 1
            error = f"{type(e).__name__}: {e}"
            if step.retry_count >= step.max_retries:
                step.status = StepStatus.SKIPPED
                step.error = error
                step.completed_at = time.time()
                self._total_steps_failed += 1
                self._advance_step()
                status = "step_failed_skipped"
            else:
                step.status = StepStatus.PENDING
                status = "step_retry"

        # 自动保存断点
        self.checkpoint()

        return {
            "status": status,
            "step": step.to_dict(),
            "result": result,
            "error": error,
        }

    def checkpoint(self) -> Optional[Path]:
        """
        保存断点

        第一性原理：长任务可能被中断，断点续传确保已完成的进度不丢失。

        Returns:
            断点文件路径，无任务则返回None
        """
        if self._current_task is None:
            return None

        checkpoint_file = self.checkpoint_dir / f"{self._current_task.task_id}.json"
        try:
            data = self._current_task.to_dict()
            data["agent_id"] = self.agent_id
            checkpoint_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            return checkpoint_file
        except Exception as e:
            if self.logger:
                self.logger.error(f"Checkpoint failed: {e}")
            return None

    def resume(self, task_id: str) -> bool:
        """
        从断点恢复

        第一性原理：中断后重启，从上次断点恢复任务状态。

        Args:
            task_id: 要恢复的任务ID

        Returns:
            是否恢复成功
        """
        checkpoint_file = self.checkpoint_dir / f"{task_id}.json"
        if not checkpoint_file.exists():
            return False

        try:
            data = json.loads(checkpoint_file.read_text(encoding="utf-8"))

            # 重建LongTask
            phases: List[List[TaskStep]] = []
            for phase_data in data.get("phases", []):
                phase: List[TaskStep] = []
                for step_data in phase_data:
                    step = TaskStep(
                        step_id=step_data["step_id"],
                        description=step_data["description"],
                        phase=step_data["phase"],
                        status=StepStatus(step_data["status"]),
                        skill_name=step_data.get("skill_name"),
                        skill_kwargs=step_data.get("skill_kwargs", {}),
                        delegate_to=step_data.get("delegate_to"),
                        delegate_capability=step_data.get("delegate_capability"),
                        result=step_data.get("result"),
                        error=step_data.get("error"),
                        started_at=step_data.get("started_at"),
                        completed_at=step_data.get("completed_at"),
                        retry_count=step_data.get("retry_count", 0),
                        max_retries=step_data.get("max_retries", 2),
                    )
                    phase.append(step)
                phases.append(phase)

            self._current_task = LongTask(
                task_id=data["task_id"],
                description=data["description"],
                phases=phases,
                current_phase=data["current_phase"],
                current_step=data["current_step"],
                status=TaskStatus(data["status"]),
                created_at=data.get("created_at", time.time()),
                completed_at=data.get("completed_at"),
                metadata=data.get("metadata", {}),
            )

            # 如果状态是RUNNING，恢复执行
            if self._current_task.status == TaskStatus.RUNNING:
                pass  # 保持RUNNING，等待execute_next

            if self.logger:
                self.logger.info(
                    f"LongTask resumed: {task_id} "
                    f"progress={self._current_task.progress():.1%}"
                )
            return True

        except Exception as e:
            if self.logger:
                self.logger.error(f"Resume failed: {e}")
            return False

    def get_progress(self) -> Dict[str, Any]:
        """获取进度"""
        if self._current_task is None:
            return {"has_task": False, "progress": 0.0}

        task = self._current_task
        step = task.get_current_step()
        return {
            "has_task": True,
            "task_id": task.task_id,
            "description": task.description,
            "status": task.status.value,
            "current_phase": task.current_phase,
            "current_step": task.current_step,
            "total_phases": len(task.phases),
            "total_steps": task.total_steps(),
            "completed_steps": task.completed_steps(),
            "progress": task.progress(),
            "current_step_description": step.description if step else None,
        }

    def delegate_step(self, step: TaskStep) -> Tuple[str, Optional[Any]]:
        """
        委派步骤给其他agent

        第一性原理：当本agent不具备某能力或负载过高时，把步骤委派给
        具备相应能力的邻居agent。

        Args:
            step: 要委派的步骤

        Returns:
            (task_id, result) — 委派成功返回协作task_id，结果在execute_next中获取
        """
        if self.collaborator is None:
            return "", None

        task_type = step.delegate_capability or "generic"
        payload = {
            "description": step.description,
            "skill_name": step.skill_name,
            "skill_kwargs": step.skill_kwargs,
        }

        collab_task_id, msg = self.collaborator.dispatch_task(
            task_type=task_type,
            payload=payload,
            required_capability=step.delegate_capability,
        )

        step.status = StepStatus.DELEGATED
        self._total_steps_delegated += 1

        return collab_task_id, msg

    def get_status(self) -> Dict[str, Any]:
        """编排器状态"""
        return {
            "agent_id": self.agent_id,
            "has_task": self._current_task is not None,
            "tasks_started": self._total_tasks_started,
            "tasks_completed": self._total_tasks_completed,
            "steps_executed": self._total_steps_executed,
            "steps_delegated": self._total_steps_delegated,
            "steps_failed": self._total_steps_failed,
            "current_progress": self.get_progress(),
        }

    def register_step_handler(self, step_type: str,
                               handler: Callable[[TaskStep], Any]) -> None:
        """注册步骤处理器（用于无技能无委派的步骤）"""
        self._step_handlers[step_type] = handler

    # ========================================================================
    # 内部方法
    # ========================================================================

    def _execute_with_skill(self, step: TaskStep) -> Tuple[bool, Any, Optional[str]]:
        """用技能执行步骤"""
        if self.skill_library is None:
            return False, None, "无技能库"
        result = self.skill_library.invoke(step.skill_name, **step.skill_kwargs)
        if result["success"]:
            return True, result["result"], None
        else:
            return False, None, result.get("error", "技能调用失败")

    def _execute_delegated(self, step: TaskStep) -> Tuple[bool, Any, Optional[str]]:
        """委派执行步骤"""
        if self.collaborator is None:
            return False, None, "无协作器"

        collab_task_id, msg = self.delegate_step(step)
        if msg is None:
            return False, None, "无可用邻居委派"

        # 处理消息让目标agent接收
        self.collaborator.process_messages()

        # 检查结果
        task_record = self.collaborator.dispatcher.get_task(collab_task_id)
        if task_record and task_record.status.value == "completed":
            return True, task_record, None
        elif task_record and task_record.status.value == "failed":
            return False, None, "委派任务失败"
        else:
            # 异步委派，标记为进行中
            return True, {"collab_task_id": collab_task_id, "status": "delegated"}, None

    def _execute_with_handler(self, step: TaskStep) -> Tuple[bool, Any, Optional[str]]:
        """用注册的handler执行步骤"""
        # 按描述关键词匹配handler
        for step_type, handler in self._step_handlers.items():
            if step_type in step.description.lower():
                try:
                    result = handler(step)
                    return True, result, None
                except Exception as e:
                    return False, None, f"{type(e).__name__}: {e}"

        # 无匹配handler，默认成功（空操作）
        return True, {"status": "noop", "description": step.description}, None

    def _advance_step(self) -> None:
        """推进到下一步"""
        if self._current_task is None:
            return

        task = self._current_task
        task.current_step += 1

        # 检查当前阶段是否完成
        if task.current_phase < len(task.phases):
            if task.current_step >= len(task.phases[task.current_phase]):
                # 进入下一阶段
                task.current_phase += 1
                task.current_step = 0

        # 检查是否所有阶段完成
        if task.current_phase >= len(task.phases):
            self._complete_task()

    def _complete_task(self) -> None:
        """完成任务"""
        if self._current_task is None:
            return
        self._current_task.status = TaskStatus.COMPLETED
        self._current_task.completed_at = time.time()
        self._total_tasks_completed += 1

        if self.logger:
            self.logger.info(
                f"LongTask completed: {self._current_task.task_id} "
                f"progress=100%"
            )
