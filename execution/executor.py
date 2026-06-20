"""
任务执行器

第一性原理：大脑的决策最终要通过运动皮层转化为肌肉动作。
Agent生成的任务必须通过执行器转化为真实的系统操作。

实现：
1. 命令执行（shell命令）
2. K8s操作（通过kubectl或API）
3. 系统调优（cgroups、nice、sysctl等）
4. 安全限制（白名单、速率限制、影响评估）
"""

from __future__ import annotations

import subprocess
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from enum import Enum


class ActionType(Enum):
    """动作类型"""
    SHELL = "shell"
    KUBECTL = "kubectl"
    DOCKER = "docker"
    SYSCTL = "sysctl"
    CGROUP = "cgroup"
    NICE = "nice"
    LOG_ONLY = "log_only"  # 仅记录，不执行（安全模式）


class SafetyLevel(Enum):
    """安全等级"""
    SAFE = "safe"           # 只读/查询，无风险
    LOW_RISK = "low_risk"   # 低风险（调整优先级等）
    MEDIUM_RISK = "medium"  # 中风险（重启服务、清理资源）
    HIGH_RISK = "high"      # 高风险（删除数据、强制终止）


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    action_type: ActionType
    command: str
    stdout: str
    stderr: str
    return_code: int
    execution_time_ms: float
    safety_level: SafetyLevel


class TaskExecutor:
    """
    任务执行器

    将Agent决策转化为真实操作，带安全限制。
    """

    # 命令白名单（只允许执行这些命令前缀）
    COMMAND_WHITELIST = {
        ActionType.SHELL: [
            "ps ", "top ", "htop", "free", "df ", "du ", "ls ", "cat ",
            "echo ", "mkdir ", "touch ", "cp ", "mv ", "rm -f ", "rm -rf /tmp/",
            "kill -TERM ", "kill -HUP ", "pkill -TERM ", "pkill -HUP ",
            "systemctl status ", "systemctl restart ", "systemctl reload ",
            "service ", "nginx -t", "nginx -s reload",
        ],
        ActionType.KUBECTL: [
            "kubectl get ", "kubectl describe ", "kubectl logs ",
            "kubectl top ", "kubectl scale ", "kubectl rollout ",
            "kubectl delete pod ", "kubectl exec ",
        ],
        ActionType.DOCKER: [
            "docker ps", "docker stats", "docker logs ", "docker inspect ",
            "docker restart ", "docker stop ", "docker start ",
        ],
        ActionType.SYSCTL: [
            "sysctl -a", "sysctl -w ", "sysctl -p",
        ],
        ActionType.CGROUP: [
            "cgget ", "cgset ", "cgcreate ", "cgdelete ",
        ],
        ActionType.NICE: [
            "nice ", "renice ", "ionice ",
        ],
    }

    def __init__(self,
                 dry_run: bool = False,
                 max_risk_level: SafetyLevel = SafetyLevel.LOW_RISK,
                 command_timeout_seconds: float = 30.0):
        """
        Args:
            dry_run: 只打印命令不执行（测试模式）
            max_risk_level: 允许执行的最高风险等级
            command_timeout_seconds: 命令超时时间
        """
        self.dry_run = dry_run
        self.max_risk_level = max_risk_level
        self.command_timeout = command_timeout_seconds
        self._execution_history: List[ExecutionResult] = []
        self._daily_execution_count = 0
        self._daily_limit = 100  # 每日执行上限
        self._last_reset_date = time.strftime("%Y-%m-%d")

    def execute(self, action_type: ActionType, command: str,
                safety_level: SafetyLevel = SafetyLevel.LOW_RISK) -> ExecutionResult:
        """
        执行命令

        Precondition:
            - command 非空
            - safety_level <= max_risk_level
            - command 在白名单中

        Postcondition:
            - 返回 ExecutionResult
        """
        start_time = time.time()

        # 安全检查1：风险等级
        if not self._is_risk_acceptable(safety_level):
            return ExecutionResult(
                success=False,
                action_type=action_type,
                command=command,
                stdout="",
                stderr=f"Risk level {safety_level.value} exceeds maximum {self.max_risk_level.value}",
                return_code=-1,
                execution_time_ms=0.0,
                safety_level=safety_level,
            )

        # 安全检查2：白名单
        if not self._is_whitelisted(action_type, command):
            return ExecutionResult(
                success=False,
                action_type=action_type,
                command=command,
                stdout="",
                stderr=f"Command not in whitelist: {command}",
                return_code=-1,
                execution_time_ms=0.0,
                safety_level=safety_level,
            )

        # 安全检查3：频率限制（按日重置）
        today = time.strftime("%Y-%m-%d")
        if today != self._last_reset_date:
            self._daily_execution_count = 0
            self._last_reset_date = today
        if self._daily_execution_count >= self._daily_limit:
            return ExecutionResult(
                success=False,
                action_type=action_type,
                command=command,
                stdout="",
                stderr="Daily execution limit reached",
                return_code=-1,
                execution_time_ms=0.0,
                safety_level=safety_level,
            )

        # 干跑模式
        if self.dry_run or action_type == ActionType.LOG_ONLY:
            print(f"[DRY RUN] {action_type.value}: {command}")
            result = ExecutionResult(
                success=True,
                action_type=action_type,
                command=command,
                stdout="[dry run]",
                stderr="",
                return_code=0,
                execution_time_ms=0.0,
                safety_level=safety_level,
            )
            self._execution_history.append(result)
            return result

        # 真实执行
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.command_timeout,
            )

            execution_time = (time.time() - start_time) * 1000
            self._daily_execution_count += 1

            result = ExecutionResult(
                success=proc.returncode == 0,
                action_type=action_type,
                command=command,
                stdout=proc.stdout[:1000],  # 限制输出长度
                stderr=proc.stderr[:1000],
                return_code=proc.returncode,
                execution_time_ms=execution_time,
                safety_level=safety_level,
            )
            self._execution_history.append(result)
            return result

        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                action_type=action_type,
                command=command,
                stdout="",
                stderr=f"Command timed out after {self.command_timeout}s",
                return_code=-1,
                execution_time_ms=self.command_timeout * 1000,
                safety_level=safety_level,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                action_type=action_type,
                command=command,
                stdout="",
                stderr=str(e),
                return_code=-1,
                execution_time_ms=(time.time() - start_time) * 1000,
                safety_level=safety_level,
            )

    def execute_shell(self, command: str, safety_level: SafetyLevel = SafetyLevel.LOW_RISK) -> ExecutionResult:
        """便捷方法：执行shell命令"""
        return self.execute(ActionType.SHELL, command, safety_level)

    def execute_kubectl(self, command: str, safety_level: SafetyLevel = SafetyLevel.LOW_RISK) -> ExecutionResult:
        """便捷方法：执行kubectl命令"""
        return self.execute(ActionType.KUBECTL, f"kubectl {command}", safety_level)

    def scale_deployment(self, namespace: str, deployment: str, replicas: int) -> ExecutionResult:
        """扩缩容K8s Deployment"""
        cmd = f"kubectl scale deployment {deployment} -n {namespace} --replicas={replicas}"
        return self.execute(ActionType.KUBECTL, cmd, SafetyLevel.MEDIUM_RISK)

    def restart_pod(self, namespace: str, pod_name: str) -> ExecutionResult:
        """重启K8s Pod"""
        cmd = f"kubectl delete pod {pod_name} -n {namespace}"
        return self.execute(ActionType.KUBECTL, cmd, SafetyLevel.MEDIUM_RISK)

    def set_nice(self, pid: int, priority: int) -> ExecutionResult:
        """调整进程优先级"""
        cmd = f"renice {priority} -p {pid}"
        return self.execute(ActionType.NICE, cmd, SafetyLevel.LOW_RISK)

    def limit_cpu_cgroup(self, cgroup_path: str, cpu_quota_us: int, cpu_period_us: int = 100000) -> ExecutionResult:
        """通过cgroup限制CPU"""
        cmd = f"cgset -r cpu.cfs_quota_us={cpu_quota_us} -r cpu.cfs_period_us={cpu_period_us} {cgroup_path}"
        return self.execute(ActionType.CGROUP, cmd, SafetyLevel.LOW_RISK)

    def _is_risk_acceptable(self, level: SafetyLevel) -> bool:
        """检查风险等级是否可接受"""
        risk_order = {
            SafetyLevel.SAFE: 0,
            SafetyLevel.LOW_RISK: 1,
            SafetyLevel.MEDIUM_RISK: 2,
            SafetyLevel.HIGH_RISK: 3,
        }
        return risk_order.get(level, 999) <= risk_order.get(self.max_risk_level, 999)

    def _is_whitelisted(self, action_type: ActionType, command: str) -> bool:
        """检查命令是否在白名单中"""
        whitelist = self.COMMAND_WHITELIST.get(action_type, [])
        return any(command.startswith(prefix) for prefix in whitelist)

    def get_history(self) -> List[ExecutionResult]:
        """获取执行历史"""
        return self._execution_history.copy()

    def get_stats(self) -> Dict[str, Any]:
        """获取执行统计"""
        total = len(self._execution_history)
        successful = sum(1 for r in self._execution_history if r.success)
        return {
            "total_executions": total,
            "successful": successful,
            "failed": total - successful,
            "success_rate": successful / total if total > 0 else 0.0,
            "daily_count": self._daily_execution_count,
            "daily_limit": self._daily_limit,
        }
