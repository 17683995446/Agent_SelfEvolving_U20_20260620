"""
任务路由器

第一性原理：大脑的运动皮层把抽象意图（"伸手"）转化为具体的肌肉指令。
TaskRouter 把 Agent 生成的抽象任务动作（reduce_cpu_load / free_memory / ...）
路由到具体的执行器（AutoHealingEngine / TaskExecutor / ActionableTaskEngine），
让 Agent 的决策真正落地为系统操作。

设计原则：
- 单一职责：只做"路由"，不做执行（执行交给各专业执行器）
- 可观测：每次路由打印日志，验证路由链路
- 安全第一：默认 dry_run，生产环境显式开启
- 闭环准备：返回结构化 ExecutionOutcome，供阶段2做反馈学习
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core import TaskStatus, STATE_IDX_CPU_OVERALL, STATE_IDX_MEM_USED, STATE_IDX_DISK_USED
from core.auto_healing import AutoHealingEngine
from core.actionable_tasks import ActionableTaskEngine
from execution.executor import TaskExecutor, ActionType, SafetyLevel
from safety.security_guard import SecurityGuard


@dataclass
class ExecutionOutcome:
    """任务执行结果（统一格式，供阶段2反馈学习使用）"""
    task_id: str
    task_name: str
    task_action: str
    executed: bool                       # 是否真正执行了（False=被安全策略拒绝/dry_run）
    success: bool                        # 执行是否成功
    executor: str                        # 哪个执行器处理的（auto_healing/task_executor/actionable/log_only）
    command: str                         # 实际执行的命令
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0
    duration_ms: float = 0.0
    before_metrics: Dict[str, float] = field(default_factory=dict)
    after_metrics: Dict[str, float] = field(default_factory=dict)
    message: str = ""
    timestamp: float = field(default_factory=lambda: time.time())


class TaskRouter:
    """
    任务路由器

    把 Agent 的抽象任务动作路由到具体执行器。

    路由表（task.action → 执行器）：
    - reduce_cpu_load   → AutoHealingEngine (cpu_bound_process 诊断+throttle)
    - free_memory       → AutoHealingEngine (memory_leak 诊断+clear_cache)
    - free_disk_space   → AutoHealingEngine (disk_full 诊断+clear_cache)
    - optimize_resources→ TaskExecutor (ps 查看进程，SAFE只读)
    - increase_sampling_rate → log_only（调整采样频率，阶段2实现真实反馈）
    - 其他未知 action   → log_only（记录但不执行，安全兜底）
    """

    # action → 执行器映射
    ACTION_ROUTES = {
        "reduce_cpu_load":         "auto_healing",
        "free_memory":             "auto_healing",
        "free_disk_space":         "auto_healing",
        "optimize_resources":      "task_executor",
        "increase_sampling_rate":  "log_only",
    }

    def __init__(self,
                 auto_healing: Optional[AutoHealingEngine] = None,
                 task_executor: Optional[TaskExecutor] = None,
                 actionable_engine: Optional[ActionableTaskEngine] = None,
                 dry_run: bool = True,
                 logger=None):
        """
        Args:
            auto_healing: 自愈引擎（诊断+修复）
            task_executor: 任务执行器（shell/kubectl等）
            actionable_engine: 可执行任务引擎（NL→命令）
            dry_run: 干跑模式（只打印不执行），默认True安全
            logger: 日志器
        """
        self.auto_healing = auto_healing or AutoHealingEngine(auto_approve_low_risk=not dry_run)
        self.task_executor = task_executor or TaskExecutor(dry_run=dry_run, max_risk_level=SafetyLevel.LOW_RISK)
        self.actionable_engine = actionable_engine or ActionableTaskEngine(dry_run=dry_run)
        self.dry_run = dry_run
        self.logger = logger
        # === 阶段3：安全护栏 ===
        # 第一性原理：免疫系统有"自身耐受"机制——不会攻击自身组织。
        # SecurityGuard 对所有执行命令做注入检测+黑名单+白名单+风险评级。
        self.security_guard = SecurityGuard(max_risk_level="medium")
        self._outcomes: List[ExecutionOutcome] = []

    def route(self, task, state_vector=None) -> ExecutionOutcome:
        """
        路由并执行任务

        Args:
            task: Task 对象（必须有 action 字段）
            state_vector: 当前状态向量（用于构造metrics给auto_healing）

        Returns:
            ExecutionOutcome: 统一执行结果
        """
        action = getattr(task, "action", None) or task.name
        executor_name = self.ACTION_ROUTES.get(action, "log_only")

        print(f"  [TaskRouter] route task={task.name} action={action} -> executor={executor_name} dry_run={self.dry_run}")
        if self.logger:
            self.logger.info(f"TaskRouter: route {task.name} -> {executor_name}")

        # 采集执行前指标（供阶段2反馈学习）
        before_metrics = self._extract_metrics(state_vector)

        start = time.time()
        outcome = self._dispatch(executor_name, task, action, state_vector, before_metrics)
        outcome.duration_ms = (time.time() - start) * 1000
        outcome.before_metrics = before_metrics
        outcome.after_metrics = self._extract_metrics(state_vector)  # 同步执行，after≈before；阶段2会重新采集

        self._outcomes.append(outcome)
        print(f"  [TaskRouter] outcome: executed={outcome.executed} success={outcome.success} "
              f"executor={outcome.executor} cmd='{outcome.command[:60]}' rc={outcome.return_code} "
              f"duration={outcome.duration_ms:.1f}ms")
        return outcome

    def _dispatch(self, executor_name: str, task, action: str,
                  state_vector, before_metrics: Dict[str, float]) -> ExecutionOutcome:
        """分发到具体执行器"""
        try:
            if executor_name == "auto_healing":
                return self._via_auto_healing(task, action, before_metrics)
            elif executor_name == "task_executor":
                return self._via_task_executor(task, action)
            elif executor_name == "actionable":
                return self._via_actionable(task)
            else:
                return self._log_only(task, action)
        except Exception as e:
            print(f"  [TaskRouter] dispatch error: {type(e).__name__}: {e}")
            return ExecutionOutcome(
                task_id=task.id, task_name=task.name, task_action=action,
                executed=False, success=False, executor=executor_name,
                command="", stderr=f"{type(e).__name__}: {e}",
                message=f"dispatch error: {e}",
            )

    def _via_auto_healing(self, task, action: str, metrics: Dict[str, float]) -> ExecutionOutcome:
        """通过 AutoHealingEngine 执行（诊断+修复+验证）"""
        # auto_healing 的 run_healing_cycle 内部会 detect→diagnose→select→execute
        result = self.auto_healing.run_healing_cycle(metrics)

        executed = result.get("status") == "healed"
        execution = result.get("execution", {})
        command = execution.get("command", "")

        # === 阶段3：安全护栏 — 对 auto_healing 选出的命令做安全检查 ===
        if command and executed:
            sec_check = self.security_guard.check(command)
            if not sec_check.allowed:
                print(f"  [TaskRouter] auto_healing command BLOCKED by SecurityGuard: {command[:50]} - {sec_check.reason}")
                return ExecutionOutcome(
                    task_id=task.id, task_name=task.name, task_action=action,
                    executed=False, success=False, executor="auto_healing",
                    command=command, stderr=f"安全拦截: {sec_check.reason}",
                    message=f"命令被安全护栏拦截: {sec_check.reason}",
                )

        stdout = execution.get("stdout", "")
        stderr = execution.get("stderr", "") or execution.get("reason", "")

        return ExecutionOutcome(
            task_id=task.id, task_name=task.name, task_action=action,
            executed=executed, success=executed,
            executor="auto_healing",
            command=command, stdout=stdout, stderr=stderr,
            return_code=execution.get("returncode", 0),
            message=result.get("message", ""),
        )

    def _via_task_executor(self, task, action: str) -> ExecutionOutcome:
        """通过 TaskExecutor 执行（白名单shell命令）"""
        # optimize_resources → 查看高CPU进程（只读，SAFE级别）
        command = "ps -eo pid,pcpu,pmem,comm --sort=-pcpu | head -10"

        # === 阶段3：安全护栏 — 执行前安全检查 ===
        sec_check = self.security_guard.check(command)
        if not sec_check.allowed:
            print(f"  [TaskRouter] command BLOCKED: {command[:50]} - {sec_check.reason}")
            return ExecutionOutcome(
                task_id=task.id, task_name=task.name, task_action=action,
                executed=False, success=False, executor="task_executor",
                command=command, stderr=f"安全拦截: {sec_check.reason}",
                message=f"命令被安全护栏拦截: {sec_check.reason}",
            )

        result = self.task_executor.execute(
            ActionType.SHELL, command, SafetyLevel.SAFE
        )
        return ExecutionOutcome(
            task_id=task.id, task_name=task.name, task_action=action,
            executed=not self.dry_run, success=result.success,
            executor="task_executor",
            command=result.command, stdout=result.stdout, stderr=result.stderr,
            return_code=result.return_code,
        )

    def _via_actionable(self, task) -> ExecutionOutcome:
        """通过 ActionableTaskEngine 执行（NL→命令）"""
        result = self.actionable_engine.run_task_pipeline(task.description)
        execution = result.get("execution", {})
        return ExecutionOutcome(
            task_id=task.id, task_name=task.name, task_action=getattr(task, "action", ""),
            executed=result.get("status") == "success",
            success=result.get("status") == "success",
            executor="actionable",
            command=result.get("task", {}).get("command", ""),
            stdout=execution.get("stdout", ""),
            stderr=execution.get("stderr", ""),
            message=result.get("message", ""),
        )

    def _log_only(self, task, action: str) -> ExecutionOutcome:
        """仅记录日志，不执行（安全兜底）"""
        msg = f"log_only: task={task.name} action={action} (no real execution)"
        print(f"  [TaskRouter] {msg}")
        return ExecutionOutcome(
            task_id=task.id, task_name=task.name, task_action=action,
            executed=False, success=True, executor="log_only",
            command="", message=msg,
        )

    def _extract_metrics(self, state_vector) -> Dict[str, float]:
        """从状态向量提取 auto_healing 需要的 metrics 格式"""
        if state_vector is None:
            return {"cpu_percent": 0.0, "memory_percent": 0.0, "disk_percent": 0.0}
        try:
            return {
                "cpu_percent": float(state_vector[STATE_IDX_CPU_OVERALL]) * 100,
                "memory_percent": float(state_vector[STATE_IDX_MEM_USED]) * 100,
                "disk_percent": float(state_vector[STATE_IDX_DISK_USED]) * 100,
            }
        except (IndexError, TypeError):
            return {"cpu_percent": 0.0, "memory_percent": 0.0, "disk_percent": 0.0}

    def get_outcomes(self) -> List[ExecutionOutcome]:
        """获取所有执行结果（供阶段2反馈学习）"""
        return self._outcomes.copy()

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._outcomes)
        executed = sum(1 for o in self._outcomes if o.executed)
        success = sum(1 for o in self._outcomes if o.success)
        return {
            "total_routed": total,
            "executed": executed,
            "skipped": total - executed,
            "success_count": success,
            "failure_count": executed - success,
            "success_rate": success / executed if executed > 0 else 0.0,
            "by_executor": self._stats_by_executor(),
            "security_stats": self.security_guard.get_stats() if hasattr(self, 'security_guard') else {},
        }

    def _stats_by_executor(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for o in self._outcomes:
            counts[o.executor] = counts.get(o.executor, 0) + 1
        return counts
