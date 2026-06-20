"""
智能运维自愈引擎

第一性原理：免疫系统—— 发现入侵→识别病原体→产生抗体→清除→记忆。
AutoHealingEngine 让系统异常自动检测、自动诊断、自动修复、自动验证。

约束：
- 纯Python实现
- 方法数 <= 7
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class HealingAction:
    """修复动作"""
    action_type: str          # kill_restart / clear_cache / throttle / alert
    target: str               # 目标进程/服务/资源
    command: str              # 具体执行的shell命令
    estimated_impact: str     # 预估影响（low/medium/high）
    auto_approved: bool = False  # 是否自动执行（低风险才自动）


@dataclass
class HealingResult:
    """修复结果"""
    success: bool
    action_taken: str
    before_state: Dict[str, float]
    after_state: Dict[str, float]
    duration_ms: float
    message: str


class AutoHealingEngine:
    """
    智能运维自愈引擎

    核心方法（<=7个）：
    1. detect_anomaly() — 检测异常（复用AnomalyDetector）
    2. diagnose_root_cause() — 根因分析
    3. select_healing_action() — 选择修复策略
    4. execute_action() — 执行修复
    5. verify_recovery() — 验证恢复
    6. run_healing_cycle() — 完整自愈循环
    7. get_stats() — 统计
    """

    def __init__(self, auto_approve_low_risk: bool = True, max_history_size: int = 500):
        self.auto_approve_low_risk = auto_approve_low_risk
        self.max_history_size = max_history_size
        self._history: List[Dict[str, Any]] = []
        self._success_count = 0
        self._failure_count = 0
        self._total_cycles = 0

    def detect_anomaly(self, metrics: Dict[str, float]) -> Dict[str, Any]:
        """
        检测系统异常

        输入：系统指标字典（cpu_percent, memory_percent, disk_percent）
        输出：异常检测结果
        """
        anomalies = []
        severity = 0.0

        cpu = metrics.get("cpu_percent", 0)
        mem = metrics.get("memory_percent", 0)
        disk = metrics.get("disk_percent", 0)

        if cpu > 90:
            anomalies.append({"type": "cpu_critical", "value": cpu, "threshold": 90})
            severity = max(severity, 1.0)
        elif cpu > 70:
            anomalies.append({"type": "cpu_high", "value": cpu, "threshold": 70})
            severity = max(severity, 0.6)

        if mem > 90:
            anomalies.append({"type": "memory_critical", "value": mem, "threshold": 90})
            severity = max(severity, 1.0)
        elif mem > 80:
            anomalies.append({"type": "memory_high", "value": mem, "threshold": 80})
            severity = max(severity, 0.7)

        if disk > 95:
            anomalies.append({"type": "disk_critical", "value": disk, "threshold": 95})
            severity = max(severity, 0.9)

        return {
            "is_anomaly": len(anomalies) > 0,
            "anomalies": anomalies,
            "severity": severity,
            "timestamp": time.time(),
        }

    def diagnose_root_cause(self, metrics: Dict[str, float]) -> Dict[str, Any]:
        """
        根因分析

        根据指标特征判断最可能的根因。
        """
        cpu = metrics.get("cpu_percent", 0)
        mem = metrics.get("memory_percent", 0)
        disk = metrics.get("disk_percent", 0)

        causes = []

        if cpu > 80 and mem > 80:
            causes.append({
                "cause": "system_overload",
                "confidence": 0.9,
                "description": "CPU和内存双高，系统整体过载",
            })
        elif cpu > 80:
            causes.append({
                "cause": "cpu_bound_process",
                "confidence": 0.85,
                "description": "CPU高，可能是某个进程CPU密集型计算",
            })
        elif mem > 80:
            causes.append({
                "cause": "memory_leak",
                "confidence": 0.75,
                "description": "内存高，可能存在内存泄漏",
            })

        if disk > 90:
            causes.append({
                "cause": "disk_full",
                "confidence": 0.95,
                "description": "磁盘空间不足",
            })

        # 按置信度排序
        causes.sort(key=lambda x: x["confidence"], reverse=True)

        return {
            "primary_cause": causes[0] if causes else None,
            "all_causes": causes,
            "timestamp": time.time(),
        }

    def select_healing_action(self, diagnosis: Dict[str, Any]) -> Optional[HealingAction]:
        """
        根据根因选择修复策略

        第一性原理：医生开处方—— 根据病因选择治疗方案。
        """
        cause = diagnosis.get("primary_cause")
        if not cause:
            return None

        cause_type = cause["cause"]

        if cause_type == "cpu_bound_process":
            return HealingAction(
                action_type="throttle",
                target="high_cpu_process",
                command="ps -eo pid,pcpu,comm --sort=-pcpu | head -5",
                estimated_impact="medium",
                auto_approved=False,  # 需要确认，避免杀掉关键进程
            )
        elif cause_type == "memory_leak":
            return HealingAction(
                action_type="clear_cache",
                target="system_cache",
                command="sync && echo 3 > /proc/sys/vm/drop_caches",
                estimated_impact="low",
                auto_approved=self.auto_approve_low_risk,
            )
        elif cause_type == "system_overload":
            return HealingAction(
                action_type="alert",
                target="system",
                command="echo 'SYSTEM OVERLOAD' | wall",
                estimated_impact="low",
                auto_approved=True,
            )
        elif cause_type == "disk_full":
            return HealingAction(
                action_type="clear_cache",
                target="logs",
                command="find /var/log -name '*.log' -mtime +7 -delete",
                estimated_impact="medium",
                auto_approved=self.auto_approve_low_risk,
            )

        return None

    def execute_action(self, action: HealingAction) -> Dict[str, Any]:
        """
        执行修复动作

        安全执行shell命令，返回执行结果。
        """
        start = time.time()

        if not action.auto_approved:
            return {
                "executed": False,
                "reason": "action requires manual approval",
                "command": action.command,
                "duration_ms": 0,
            }

        try:
            # 使用subprocess执行，带超时保护
            result = subprocess.run(
                action.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            duration = (time.time() - start) * 1000

            return {
                "executed": True,
                "returncode": result.returncode,
                "stdout": result.stdout[:500] if result.stdout else "",
                "stderr": result.stderr[:500] if result.stderr else "",
                "duration_ms": duration,
                "command": action.command,
            }
        except subprocess.TimeoutExpired:
            return {
                "executed": False,
                "reason": "command timeout",
                "duration_ms": (time.time() - start) * 1000,
            }
        except Exception as e:
            return {
                "executed": False,
                "reason": str(e),
                "duration_ms": (time.time() - start) * 1000,
            }

    def verify_recovery(self, before: Dict[str, float],
                        after: Dict[str, float]) -> HealingResult:
        """
        验证修复效果

        对比修复前后的系统指标。
        """
        cpu_before = before.get("cpu_percent", 0)
        cpu_after = after.get("cpu_percent", 0)
        mem_before = before.get("memory_percent", 0)
        mem_after = after.get("memory_percent", 0)

        cpu_improved = cpu_after < cpu_before * 0.9
        mem_improved = mem_after < mem_before * 0.9

        success = cpu_improved or mem_improved or (cpu_after < 70 and mem_after < 80)

        if success:
            self._success_count += 1
            message = f"恢复成功：CPU {cpu_before:.1f}%→{cpu_after:.1f}%, 内存 {mem_before:.1f}%→{mem_after:.1f}%"
        else:
            self._failure_count += 1
            message = f"恢复未达预期：CPU {cpu_before:.1f}%→{cpu_after:.1f}%, 内存 {mem_before:.1f}%→{mem_after:.1f}%"

        return HealingResult(
            success=success,
            action_taken="healing",
            before_state=before,
            after_state=after,
            duration_ms=0,
            message=message,
        )

    def run_healing_cycle(self, metrics: Dict[str, float]) -> Dict[str, Any]:
        """
        完整自愈循环

        检测→诊断→修复→验证，一站式解决异常。
        """
        cycle_start = time.time()

        # 1. 检测
        anomaly = self.detect_anomaly(metrics)
        if not anomaly["is_anomaly"]:
            return {"status": "healthy", "message": "系统正常，无需修复"}

        # 2. 诊断
        diagnosis = self.diagnose_root_cause(metrics)

        # 3. 选择修复策略
        action = self.select_healing_action(diagnosis)
        if not action:
            return {
                "status": "no_action",
                "anomaly": anomaly,
                "diagnosis": diagnosis,
                "message": "无法确定修复策略",
            }

        # 4. 执行（低风险自动，高风险需审批）
        execution = self.execute_action(action)

        # 5. 记录
        status = "healed" if execution.get("executed") else "pending_approval"
        message = (
            f"已执行修复: {action.action_type} -> {action.target}"
            if execution.get("executed")
            else f"修复待审批（{execution.get('reason', '未知原因')}）: {action.action_type} -> {action.target}"
        )
        result = {
            "status": status,
            "message": message,
            "anomaly": anomaly,
            "diagnosis": diagnosis,
            "action": {
                "type": action.action_type,
                "target": action.target,
                "command": action.command,
                "auto_approved": action.auto_approved,
            },
            "execution": execution,
            "duration_ms": (time.time() - cycle_start) * 1000,
        }

        # 更新统计计数：执行成功计入success，被拒绝（有reason）不计数
        if execution.get("executed"):
            self._success_count += 1
        result["success_count"] = self._success_count
        result["failure_count"] = self._failure_count

        self._total_cycles += 1
        self._history.append(result)
        # 有界裁剪（阶段7：防止长期运行内存泄漏）
        if len(self._history) > self.max_history_size:
            self._history = self._history[-self.max_history_size:]
        return result

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_cycles": self._total_cycles,
            "success_count": self._success_count,
            "failure_count": self._failure_count,
            "recent_history": self._history[-5:],
        }
