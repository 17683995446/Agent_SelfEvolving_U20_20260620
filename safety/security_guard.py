"""
安全护栏

第一性原理：免疫系统有"自身耐受"机制——不会攻击自身组织。
自主执行系统必须有等价的安全护栏：
1. 命令注入防御（拒绝含恶意元字符的命令）
2. 危险命令拦截（黑名单 + 正则）
3. 审计日志（who/what/when/result/before/after）
4. 回滚机制（执行失败时自动回滚）

设计原则：
- 默认拒绝（deny-by-default）：不在白名单的命令一律拒绝
- 纵深防御：多层检查，任一层拦截即拒绝
- 可审计：每次执行有完整审计记录
- 可回滚：每个动作配套回滚命令
"""

from __future__ import annotations

import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# 危险模式检测
# =============================================================================

# 命令注入的典型元字符模式（出现在参数中即拦截）
INJECTION_PATTERNS = [
    (re.compile(r';\s*(rm|del|format|mkfs)'), "分号后跟删除命令"),
    (re.compile(r'\|\s*(sh|bash|zsh|python|perl)'), "管道到shell解释器"),
    (re.compile(r'\$\(.*\)'), "命令替换 $(...)"),
    (re.compile(r'`[^`]+`'), "反引号命令替换"),
    (re.compile(r'>\s*/dev/sd[a-z]'), "重定向到块设备"),
    (re.compile(r'\brm\s+-rf\s+/(?!tmp)'), "rm -rf 根目录（允许/tmp）"),
    (re.compile(r'\bmkfs\b'), "格式化文件系统"),
    (re.compile(r'\bdd\s+.*of=/dev/'), "dd写入块设备"),
    (re.compile(r':\(\)\s*\{'), "fork bomb"),
    (re.compile(r'\bchmod\s+-R\s+777\s+/'), "递归777根目录"),
]

# 绝对禁止的命令前缀（即使白名单中有也拒绝）
FORBIDDEN_PREFIXES = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=/dev/zero of=/dev/",
    ":(){",  # fork bomb
    "chmod -R 777 /",
]


@dataclass
class SecurityCheckResult:
    """安全检查结果"""
    allowed: bool
    reason: str = ""
    risk_level: str = "unknown"  # safe/low/medium/high/blocked
    violations: List[str] = field(default_factory=list)


@dataclass
class AuditRecord:
    """审计记录"""
    timestamp: float
    command: str
    allowed: bool
    executed: bool
    success: bool
    return_code: int
    duration_ms: float
    before_state: Dict[str, float] = field(default_factory=dict)
    after_state: Dict[str, float] = field(default_factory=dict)
    reason: str = ""
    stderr: str = ""
    rollback_executed: bool = False
    rollback_success: bool = False


class SecurityGuard:
    """
    安全护栏

    多层防御：
    1. 注入检测：正则匹配危险元字符模式
    2. 黑名单：绝对禁止的命令前缀
    3. 白名单：只允许已知安全的命令前缀（由调用方提供）
    4. 风险评级：safe/low/medium/high
    """

    def __init__(self,
                 whitelist: Optional[List[str]] = None,
                 max_risk_level: str = "low",
                 max_audit_log_size: int = 1000):
        """
        Args:
            whitelist: 允许的命令前缀列表（None=用默认白名单）
            max_risk_level: 允许的最高风险等级
            max_audit_log_size: 审计日志最大条数（阶段7：防止长期运行内存泄漏）
        """
        self.whitelist = whitelist or self._default_whitelist()
        self.max_risk_level = max_risk_level
        self.max_audit_log_size = max_audit_log_size
        self._audit_log: List[AuditRecord] = []
        # 全局计数器（不受审计日志裁剪影响）
        self._total_checks = 0
        self._total_allowed = 0
        self._total_blocked = 0
        self._total_executed = 0
        self._total_success = 0
        self._total_rollback = 0
        self._risk_order = {"safe": 0, "low": 1, "medium": 2, "high": 3, "blocked": 99}

    def _record_audit(self, audit: AuditRecord) -> None:
        """记录审计日志（阶段7：含全局计数+有界裁剪）"""
        self._total_checks += 1
        if audit.allowed:
            self._total_allowed += 1
        else:
            self._total_blocked += 1
        if audit.executed:
            self._total_executed += 1
        if audit.success:
            self._total_success += 1
        if audit.rollback_executed:
            self._total_rollback += 1
        self._audit_log.append(audit)
        # 有界裁剪：超过上限时丢弃最旧记录
        if len(self._audit_log) > self.max_audit_log_size:
            self._audit_log = self._audit_log[-self.max_audit_log_size:]

    def _default_whitelist(self) -> List[str]:
        """默认安全白名单（只读+低风险操作）"""
        return [
            # 只读查询（注意：前缀要精确，避免"w"匹配"wget"）
            "ps ", "top ", "htop", "free", "df ", "du ", "ls ", "cat ",
            "uptime", "who ", "w ", "last ",
            # 系统状态
            "systemctl status ", "systemctl is-active ",
            # 网络诊断
            "ping -c", "netstat ", "ss ", "ip addr", "ip route",
            # 日志查看
            "journalctl ", "tail ", "head ",
            # 安全的清理（精确路径）
            "find /tmp -type f -mtime", "find /var/log -name '*.log' -mtime",
            # 进程信号（低风险）
            "kill -TERM ", "kill -HUP ",
            # 回滚/状态命令
            "echo ",
        ]

    def check(self, command: str) -> SecurityCheckResult:
        """
        安全检查（多层防御）

        Returns:
            SecurityCheckResult: allowed=True 才可执行
        """
        violations = []
        cmd = command.strip()

        # 1. 空命令
        if not cmd:
            return SecurityCheckResult(allowed=False, reason="空命令", risk_level="blocked")

        # 2. 注入模式检测
        for pattern, desc in INJECTION_PATTERNS:
            if pattern.search(cmd):
                violations.append(f"注入模式: {desc}")

        # 3. 黑名单前缀
        for forbidden in FORBIDDEN_PREFIXES:
            if cmd.startswith(forbidden):
                violations.append(f"黑名单命令: {forbidden}")

        if violations:
            return SecurityCheckResult(
                allowed=False,
                reason="; ".join(violations),
                risk_level="blocked",
                violations=violations,
            )

        # 4. 白名单检查
        if not self._is_whitelisted(cmd):
            return SecurityCheckResult(
                allowed=False,
                reason=f"命令不在白名单: {cmd[:50]}",
                risk_level="blocked",
                violations=["非白名单命令"],
            )

        # 5. 风险评级
        risk = self._assess_risk(cmd)
        if self._risk_order.get(risk, 99) > self._risk_order.get(self.max_risk_level, 99):
            return SecurityCheckResult(
                allowed=False,
                reason=f"风险等级 {risk} 超过上限 {self.max_risk_level}",
                risk_level=risk,
            )

        return SecurityCheckResult(allowed=True, reason="通过安全检查", risk_level=risk)

    def _is_whitelisted(self, command: str) -> bool:
        """白名单前缀匹配"""
        return any(command.startswith(prefix) for prefix in self.whitelist)

    def _assess_risk(self, command: str) -> str:
        """评估命令风险等级"""
        # 高风险
        if any(k in command for k in ["kill -9", "kill -KILL", "pkill", "reboot", "shutdown", "halt"]):
            return "high"
        # 中风险（注意：用空格分隔的词匹配，避免"delete"误匹配"-delete"中的子串）
        # kill -TERM / kill -HUP 是中风险（终止进程）
        if any(k in command for k in ["kill -TERM", "kill -HUP", "systemctl restart"]):
            return "medium"
        # rm 命令是中风险（删除文件）
        if command.startswith("rm ") or " rm " in command:
            return "medium"
        # 低风险（find -delete 在白名单精确路径下算低风险）
        if any(k in command for k in ["find ", "echo ", "mkdir ", "touch ", "cp ", "mv "]):
            return "low"
        # 只读 = 安全
        return "safe"

    def safe_execute(self,
                     command: str,
                     timeout: float = 30.0,
                     before_state: Optional[Dict[str, float]] = None,
                     rollback_command: Optional[str] = None) -> Tuple[bool, AuditRecord]:
        """
        安全执行命令

        流程：check → execute → audit → (失败则rollback)

        Returns:
            (success, audit_record)
        """
        start = time.time()
        before = before_state or {}

        # 1. 安全检查
        check_result = self.check(command)

        if not check_result.allowed:
            audit = AuditRecord(
                timestamp=start, command=command,
                allowed=False, executed=False, success=False,
                return_code=-1, duration_ms=0,
                before_state=before, reason=check_result.reason,
            )
            self._record_audit(audit)
            print(f"  [SecurityGuard] BLOCKED: {command[:50]} - {check_result.reason}")
            return False, audit

        # 2. 执行（用shlex参数化，避免shell=True的注入风险）
        try:
            # 对于简单命令用shlex.split，复杂管道仍需shell但已通过注入检查
            if "|" in command or "&&" in command or ">" in command:
                # 管道/重定向命令需要shell，但已通过注入检查
                proc = subprocess.run(command, shell=True, capture_output=True,
                                      text=True, timeout=timeout)
            else:
                args = shlex.split(command)
                proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)

            duration = (time.time() - start) * 1000
            success = proc.returncode == 0
            after = {}  # 调用方可传入

            audit = AuditRecord(
                timestamp=start, command=command,
                allowed=True, executed=True, success=success,
                return_code=proc.returncode, duration_ms=duration,
                before_state=before, after_state=after,
                stderr=proc.stderr[:200] if proc.stderr else "",
            )

            # 3. 失败且有回滚命令 → 自动回滚
            if not success and rollback_command:
                rollback_check = self.check(rollback_command)
                if rollback_check.allowed:
                    try:
                        rb_proc = subprocess.run(
                            shlex.split(rollback_command) if "|" not in rollback_command
                            else rollback_command,
                            shell="|" in rollback_command,
                            capture_output=True, text=True, timeout=timeout
                        )
                        audit.rollback_executed = True
                        audit.rollback_success = (rb_proc.returncode == 0)
                        print(f"  [SecurityGuard] ROLLBACK: {rollback_command[:50]} "
                              f"success={audit.rollback_success}")
                    except Exception as e:
                        audit.rollback_executed = True
                        audit.rollback_success = False
                        audit.reason = f"rollback error: {e}"

            self._record_audit(audit)
            return success, audit

        except subprocess.TimeoutExpired:
            duration = (time.time() - start) * 1000
            audit = AuditRecord(
                timestamp=start, command=command,
                allowed=True, executed=True, success=False,
                return_code=-1, duration_ms=duration,
                before_state=before, reason="timeout",
            )
            self._record_audit(audit)
            return False, audit
        except Exception as e:
            duration = (time.time() - start) * 1000
            audit = AuditRecord(
                timestamp=start, command=command,
                allowed=True, executed=True, success=False,
                return_code=-1, duration_ms=duration,
                before_state=before, reason=str(e),
            )
            self._record_audit(audit)
            return False, audit

    def get_audit_log(self, limit: int = 100) -> List[AuditRecord]:
        """获取审计日志"""
        return self._audit_log[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        total = self._total_checks
        allowed = self._total_allowed
        blocked = self._total_blocked
        executed = self._total_executed
        success = self._total_success
        rolled_back = self._total_rollback
        return {
            "total_checks": total,
            "allowed": allowed,
            "blocked": blocked,
            "executed": executed,
            "success_count": success,
            "failure_count": executed - success,
            "rollback_count": rolled_back,
            "block_rate": blocked / total if total > 0 else 0.0,
            "audit_records": len(self._audit_log),
        }
