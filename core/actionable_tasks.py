"""
可执行任务引擎

第一性原理：语言到行动—— 人类听到"关门"就会执行关门的动作。
ActionableTaskEngine 把自然语言任务翻译成可执行的命令并执行。

约束：
- 纯Python实现
- 方法数 <= 7
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np


@dataclass
class ActionableTask:
    """可执行任务"""
    task_id: str
    description: str
    command: str
    action_type: str
    safety_level: str
    auto_approved: bool
    rollback_command: Optional[str] = None


@dataclass
class TaskExecutionResult:
    """任务执行结果"""
    task_id: str
    success: bool
    description: str
    command: str
    stdout: str
    stderr: str
    duration_ms: float
    rolled_back: bool = False


class ActionableTaskEngine:
    """
    可执行任务引擎

    把自然语言任务描述翻译为具体命令并安全执行。

    核心方法（<=7个）：
    1. parse_task() — 解析任务描述
    2. translate_to_command() — 翻译为命令
    3. assess_safety() — 安全评估
    4. execute_task() — 执行任务
    5. rollback_task() — 回滚任务
    6. run_task_pipeline() — 完整流水线
    7. get_stats() — 统计
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._history: List[TaskExecutionResult] = []
        self._task_counter = 0

        # 任务模板库：关键词 → 命令模板
        self._task_templates: Dict[str, Dict[str, Any]] = {
            "清理日志": {
                "command": "find /var/log -name '*.log' -mtime +7 -delete && echo '日志清理完成'",
                "type": "shell",
                "safety": "medium",
                "auto": True,
                "rollback": None,
            },
            "清理临时文件": {
                "command": "find /tmp -type f -mtime +1 -delete && echo '临时文件清理完成'",
                "type": "shell",
                "safety": "medium",
                "auto": True,
                "rollback": None,
            },
            "查看磁盘": {
                "command": "df -h",
                "type": "shell",
                "safety": "safe",
                "auto": True,
                "rollback": None,
            },
            "查看内存": {
                "command": "free -h",
                "type": "shell",
                "safety": "safe",
                "auto": True,
                "rollback": None,
            },
            "查看进程": {
                "command": "ps aux --sort=-%cpu | head -20",
                "type": "shell",
                "safety": "safe",
                "auto": True,
                "rollback": None,
            },
            "重启服务": {
                "command": "systemctl restart {service}",
                "type": "shell",
                "safety": "high",
                "auto": False,
                "rollback": "systemctl start {service}",
            },
            "调整采样频率": {
                "command": "echo '采样频率已调整为 {value}'",
                "type": "shell",
                "safety": "low",
                "auto": True,
                "rollback": None,
            },
            "备份配置": {
                "command": "cp {file} {file}.bak.$(date +%s)",
                "type": "shell",
                "safety": "safe",
                "auto": True,
                "rollback": None,
            },
            "杀死进程": {
                "command": "kill -TERM {pid}",
                "type": "shell",
                "safety": "high",
                "auto": False,
                "rollback": None,
            },
            "ping测试": {
                "command": "ping -c 3 {host}",
                "type": "shell",
                "safety": "safe",
                "auto": True,
                "rollback": None,
            },
        }

    def parse_task(self, description: str) -> Dict[str, Any]:
        """
        解析自然语言任务描述

        提取关键词和参数。
        """
        result = {
            "raw": description,
            "keywords": [],
            "params": {},
        }

        # 匹配模板关键词
        for keyword in self._task_templates:
            if keyword in description:
                result["keywords"].append(keyword)

        # 提取参数：服务名、PID、主机名等
        # 匹配 "xxx服务"
        service_match = re.search(r'(\w+)\s*服务', description)
        if service_match:
            result["params"]["service"] = service_match.group(1)

        # 匹配 "PID xxx" 或 "进程 xxx"
        pid_match = re.search(r'(?:PID|进程)\s*(\d+)', description)
        if pid_match:
            result["params"]["pid"] = pid_match.group(1)

        # 匹配 "xxx主机" 或 IP
        host_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', description)
        if host_match:
            result["params"]["host"] = host_match.group(1)

        # 匹配数值参数
        value_match = re.search(r'(\d+(?:\.\d+)?)\s*(秒|分钟|小时|%|GB|MB)', description)
        if value_match:
            result["params"]["value"] = value_match.group(1)

        return result

    def translate_to_command(self, description: str) -> Optional[ActionableTask]:
        """
        把任务描述翻译为可执行命令

        第一性原理：翻译—— 把一种语言（自然语言）转换为另一种（机器命令）。
        """
        parsed = self.parse_task(description)

        # 找最匹配的模板
        best_template = None
        best_keyword = None
        for keyword in parsed["keywords"]:
            if keyword in self._task_templates:
                best_template = self._task_templates[keyword]
                best_keyword = keyword
                break

        if not best_template:
            return None

        # 填充参数
        command = best_template["command"]
        rollback = best_template.get("rollback")
        for param_name, param_value in parsed["params"].items():
            command = command.replace(f"{{{param_name}}}", str(param_value))
            if rollback:
                rollback = rollback.replace(f"{{{param_name}}}", str(param_value))

        self._task_counter += 1
        return ActionableTask(
            task_id=f"task_{self._task_counter}_{int(time.time())}",
            description=description,
            command=command,
            action_type=best_template["type"],
            safety_level=best_template["safety"],
            auto_approved=best_template["auto"],
            rollback_command=rollback,
        )

    def assess_safety(self, task: ActionableTask) -> Dict[str, Any]:
        """
        安全评估

        判断任务是否可以自动执行。
        """
        level = task.safety_level

        if level == "safe":
            return {"approved": True, "reason": "只读操作，无风险"}
        elif level == "low":
            return {"approved": True, "reason": "低风险操作"}
        elif level == "medium":
            return {"approved": task.auto_approved, "reason": "中风险，需配置确认"}
        else:
            return {"approved": False, "reason": "高风险操作，必须人工审批"}

    def execute_task(self, task: ActionableTask) -> TaskExecutionResult:
        """
        执行任务

        安全执行shell命令。
        """
        start = time.time()

        if self.dry_run:
            return TaskExecutionResult(
                task_id=task.task_id,
                success=True,
                description=task.description,
                command=task.command,
                stdout="[DRY RUN] " + task.command,
                stderr="",
                duration_ms=0,
            )

        import subprocess
        try:
            result = subprocess.run(
                task.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            duration = (time.time() - start) * 1000

            return TaskExecutionResult(
                task_id=task.task_id,
                success=result.returncode == 0,
                description=task.description,
                command=task.command,
                stdout=result.stdout[:1000],
                stderr=result.stderr[:1000],
                duration_ms=duration,
            )
        except Exception as e:
            return TaskExecutionResult(
                task_id=task.task_id,
                success=False,
                description=task.description,
                command=task.command,
                stdout="",
                stderr=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def rollback_task(self, task: ActionableTask) -> TaskExecutionResult:
        """
        回滚任务

        执行回滚命令恢复状态。
        """
        if not task.rollback_command:
            return TaskExecutionResult(
                task_id=task.task_id,
                success=False,
                description=task.description,
                command="",
                stdout="",
                stderr="无回滚命令",
                duration_ms=0,
            )

        start = time.time()
        import subprocess
        try:
            result = subprocess.run(
                task.rollback_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return TaskExecutionResult(
                task_id=task.task_id,
                success=result.returncode == 0,
                description=f"回滚: {task.description}",
                command=task.rollback_command,
                stdout=result.stdout[:1000],
                stderr=result.stderr[:1000],
                duration_ms=(time.time() - start) * 1000,
                rolled_back=True,
            )
        except Exception as e:
            return TaskExecutionResult(
                task_id=task.task_id,
                success=False,
                description=f"回滚失败: {task.description}",
                command=task.rollback_command,
                stdout="",
                stderr=str(e),
                duration_ms=(time.time() - start) * 1000,
                rolled_back=True,
            )

    def run_task_pipeline(self, description: str) -> Dict[str, Any]:
        """
        完整任务流水线

        解析→翻译→评估→执行，一站式完成任务。
        """
        pipeline_start = time.time()

        # 1. 翻译为命令
        task = self.translate_to_command(description)
        if not task:
            return {
                "status": "unknown_task",
                "message": f"无法识别任务: {description}",
            }

        # 2. 安全评估
        safety = self.assess_safety(task)

        # 3. 执行（安全才执行）
        if safety["approved"]:
            result = self.execute_task(task)
            self._history.append(result)

            # 4. 如果失败且有回滚命令，尝试回滚
            if not result.success and task.rollback_command:
                rollback_result = self.rollback_task(task)
                self._history.append(rollback_result)
                return {
                    "status": "rolled_back" if rollback_result.success else "failed",
                    "task": {
                        "id": task.task_id,
                        "description": task.description,
                        "command": task.command,
                    },
                    "execution": {
                        "success": result.success,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    },
                    "rollback": {
                        "success": rollback_result.success,
                        "command": rollback_result.command,
                    },
                    "duration_ms": (time.time() - pipeline_start) * 1000,
                }

            return {
                "status": "success" if result.success else "failed",
                "task": {
                    "id": task.task_id,
                    "description": task.description,
                    "command": task.command,
                    "safety_level": task.safety_level,
                },
                "execution": {
                    "success": result.success,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "duration_ms": result.duration_ms,
                },
                "duration_ms": (time.time() - pipeline_start) * 1000,
            }
        else:
            return {
                "status": "rejected",
                "task": {
                    "id": task.task_id,
                    "description": task.description,
                    "command": task.command,
                },
                "safety": safety,
                "message": "任务因安全原因被拒绝，需人工审批",
            }

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._history)
        success = len([h for h in self._history if h.success])
        return {
            "total_executed": total,
            "success_count": success,
            "failure_count": total - success,
            "rollback_count": len([h for h in self._history if h.rolled_back]),
        }
