"""
任务生成器

第一性原理：人脑的前额叶皮层根据动机状态生成目标导向的行为计划。
TaskGenerator将驱力转换为可执行的任务，实现"缺口→目标→行动"的闭环。
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

import numpy as np

from core import DriveType, DriveState, Task, TaskPriority, TaskStatus
from core import STATE_IDX_CPU_OVERALL, STATE_IDX_MEM_USED, STATE_IDX_DISK_USED
from core.interfaces import ITaskGenerator


class TaskGenerator(ITaskGenerator):
    """
    任务生成器
    
    根据驱力状态生成任务，实现缺口驱动的自主目标生成。
    """
    
    def __init__(self, max_active_tasks: int = 1000):
        self._task_counter = 0
        self._active_tasks: Dict[str, Task] = {}
        # 防止_active_tasks无界增长（已完成/失败的任务需要定期清理）
        self._max_active_tasks = max_active_tasks
        self._last_cleanup = time.time()

    def _cleanup_finished_tasks(self) -> None:
        """清理已完成/失败/取消的任务，防止_active_tasks无界增长"""
        now = time.time()
        # 每60秒最多清理一次，避免频繁遍历
        if now - self._last_cleanup < 60 and len(self._active_tasks) < self._max_active_tasks:
            return
        finished_states = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
        finished_ids = [
            tid for tid, t in self._active_tasks.items()
            if t.status in finished_states
        ]
        for tid in finished_ids:
            del self._active_tasks[tid]
        # 若仍超限，按最早创建时间淘汰
        if len(self._active_tasks) > self._max_active_tasks:
            sorted_ids = sorted(
                self._active_tasks.keys(),
                key=lambda tid: self._active_tasks[tid].created_at
                if hasattr(self._active_tasks[tid], 'created_at') and self._active_tasks[tid].created_at
                else 0
            )
            for tid in sorted_ids[: len(self._active_tasks) - self._max_active_tasks]:
                del self._active_tasks[tid]
        self._last_cleanup = now

    def generate(self, drive_state: DriveState, state_vector: np.ndarray) -> List[Task]:
        """
        根据驱力状态生成任务

        Args:
            drive_state: 当前驱力状态
            state_vector: 当前状态向量

        Returns:
            List[Task]: 生成的任务列表
        """
        # 先清理已完成任务，防止_active_tasks无界增长
        self._cleanup_finished_tasks()

        tasks = []

        for drive_type, drive in drive_state.drives.items():
            if not drive.is_active(time.time()):
                continue

            # 根据驱力类型生成对应任务
            if drive_type == DriveType.SAFETY and drive.intensity > 0.3:
                tasks.extend(self._generate_safety_tasks(drive, state_vector))

            elif drive_type == DriveType.GAIN and drive.intensity > 0.3:
                tasks.extend(self._generate_gain_tasks(drive, state_vector))

            elif drive_type == DriveType.EFFICIENCY and drive.intensity > 0.3:
                tasks.extend(self._generate_efficiency_tasks(drive, state_vector))

        # 去重：避免生成相同任务
        unique_tasks = []
        for task in tasks:
            if not self._is_duplicate(task):
                unique_tasks.append(task)
                self._active_tasks[task.id] = task

        return unique_tasks
    
    def _generate_safety_tasks(self, drive, state_vector) -> List[Task]:
        """生成安全相关任务"""
        tasks = []
        
        cpu = state_vector[STATE_IDX_CPU_OVERALL]
        mem = state_vector[STATE_IDX_MEM_USED]
        disk = state_vector[STATE_IDX_DISK_USED]
        
        if cpu > 0.9:
            tasks.append(self._create_task(
                name="cpu_throttle",
                description=f"CPU usage critical: {cpu:.1%}",
                priority=TaskPriority.CRITICAL,
                drive=DriveType.SAFETY,
                action="reduce_cpu_load",
            ))
        
        if mem > 0.9:
            tasks.append(self._create_task(
                name="memory_cleanup",
                description=f"Memory usage critical: {mem:.1%}",
                priority=TaskPriority.CRITICAL,
                drive=DriveType.SAFETY,
                action="free_memory",
            ))
        
        if disk > 0.9:
            tasks.append(self._create_task(
                name="disk_cleanup",
                description=f"Disk usage critical: {disk:.1%}",
                priority=TaskPriority.CRITICAL,
                drive=DriveType.SAFETY,
                action="free_disk_space",
            ))
        
        return tasks
    
    def _generate_gain_tasks(self, drive, state_vector) -> List[Task]:
        """生成收益相关任务"""
        tasks = []
        
        # 认知缺口大时，增加采样频率以获取更多数据
        if drive.intensity > 0.5:
            tasks.append(self._create_task(
                name="increase_sampling",
                description="High prediction error, increase data sampling",
                priority=TaskPriority.HIGH,
                drive=DriveType.GAIN,
                action="increase_sampling_rate",
            ))
        
        return tasks
    
    def _generate_efficiency_tasks(self, drive, state_vector) -> List[Task]:
        """生成能效相关任务"""
        tasks = []
        
        cpu = state_vector[STATE_IDX_CPU_OVERALL]
        mem = state_vector[STATE_IDX_MEM_USED]
        
        # 资源使用高时，优化能效
        if cpu > 0.5 or mem > 0.5:
            tasks.append(self._create_task(
                name="optimize_resources",
                description=f"Optimize resource usage (CPU:{cpu:.1%}, MEM:{mem:.1%})",
                priority=TaskPriority.NORMAL,
                drive=DriveType.EFFICIENCY,
                action="optimize_resources",
            ))
        
        return tasks
    
    def _create_task(self, name: str, description: str, 
                     priority: TaskPriority, drive: DriveType,
                     action: str) -> Task:
        """创建任务"""
        self._task_counter += 1
        return Task(
            id=f"task_{int(time.time())}_{self._task_counter}",
            name=name,
            description=description,
            priority=priority,
            drive_source=drive,
            action=action,
        )
    
    def _is_duplicate(self, task: Task) -> bool:
        """检查是否已有相同任务"""
        for active in self._active_tasks.values():
            if active.name == task.name and active.status == TaskStatus.PENDING:
                return True
        return False
    
    def complete_task(self, task_id: str, reward: float = 0.0) -> bool:
        """完成任务"""
        task = self._active_tasks.get(task_id)
        if task:
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            task.reward = reward
            return True
        return False
    
    def get_pending_tasks(self) -> List[Task]:
        """获取待处理任务"""
        return [
            t for t in self._active_tasks.values()
            if t.status == TaskStatus.PENDING
        ]
    
    def get_tasks_by_priority(self) -> List[Task]:
        """按优先级排序获取任务"""
        pending = self.get_pending_tasks()
        pending.sort(key=lambda t: t.priority.value)
        return pending
