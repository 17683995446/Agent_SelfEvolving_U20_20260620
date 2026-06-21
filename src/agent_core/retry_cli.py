"""
错误恢复与自动重试。

第一性原理：
- 系统故障是常态，优雅恢复比避免故障更重要
- 瞬时故障（网络抖动、资源竞争）可通过重试解决
- 永久故障（配置错误、权限不足）重试无益，应快速失败
- 指数退避避免重试风暴，熔断器防止级联故障
- 错误恢复建议帮助用户快速定位和解决问题

设计要点：
- ErrorType: 错误分类（transient/permanent/unknown）
- ErrorClassifier: 错误分类器
- RetryPolicy: 重试策略（max_retries/backoff/jitter）
- RetryExecutor: 重试执行器
- CircuitBreaker: 熔断器（防止级联故障）
- RecoveryAdvisor: 恢复建议
- retry CLI: run/status/reset
"""

import argparse
import io
import os
import random
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

# 颜色
_COLOR_RESET = "\033[0m"
_COLOR_RED = "\033[31m"
_COLOR_GREEN = "\033[32m"
_COLOR_YELLOW = "\033[33m"
_COLOR_CYAN = "\033[36m"
_COLOR_BOLD = "\033[1m"
_COLOR_DIM = "\033[2m"
_COLOR_MAGENTA = "\033[35m"

_COLOR_ENABLED = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False


def _c(text: str, color: str) -> str:
    """添加颜色。"""
    if not _COLOR_ENABLED:
        return text
    return f"{color}{text}{_COLOR_RESET}"


# 错误类型
ERROR_TRANSIENT = "transient"      # 瞬时错误（可重试）
ERROR_PERMANENT = "permanent"      # 永久错误（不可重试）
ERROR_UNKNOWN = "unknown"          # 未知错误

# 瞬时错误关键词（出现这些词的错误通常是瞬时的）
_TRANSIENT_KEYWORDS = [
    "timeout", "timed out", "connection refused", "connection reset",
    "temporarily unavailable", "resource busy", "try again",
    "service unavailable", "503", "502", "429",
    "network", "unreachable", "broken pipe",
]

# 永久错误关键词（出现这些词的错误通常是永久的）
_PERMANENT_KEYWORDS = [
    "not found", "no such file", "permission denied", "access denied",
    "unauthorized", "forbidden", "404", "401", "403",
    "invalid", "malformed", "syntax error",
    "already exists", "duplicate",
    "not supported", "unsupported",
    "value error", "type error", "attribute error",
    "key error", "index error",
]

# 恢复建议映射
_RECOVERY_SUGGESTIONS: Dict[str, str] = {
    "timeout": "增加超时时间或检查网络连接",
    "connection refused": "检查目标服务是否正在运行",
    "connection reset": "检查网络稳定性或服务负载",
    "permission denied": "检查文件权限或用户权限",
    "access denied": "检查认证凭据或访问权限",
    "not found": "检查文件路径或资源是否存在",
    "no such file": "检查文件路径是否正确",
    "unauthorized": "检查API密钥或登录凭据",
    "forbidden": "检查是否有访问该资源的权限",
    "invalid": "检查输入参数格式是否正确",
    "already exists": "使用不同名称或删除已存在的资源",
    "service unavailable": "稍后重试或联系服务管理员",
    "503": "服务暂时不可用，稍后重试",
    "502": "网关错误，检查上游服务",
    "429": "请求过多，降低频率或增加间隔",
}


class ErrorClassifier:
    """
    错误分类器。

    将错误分类为瞬时（可重试）或永久（不可重试）。
    """

    @staticmethod
    def classify(error: Exception) -> str:
        """
        分类错误。

        Args:
            error: 异常对象。

        Returns:
            错误类型（ERROR_TRANSIENT/ERROR_PERMANENT/ERROR_UNKNOWN）。
        """
        error_msg = str(error).lower()
        error_type_name = type(error).__name__.lower()

        # 检查永久错误
        for keyword in _PERMANENT_KEYWORDS:
            if keyword in error_msg or keyword in error_type_name:
                return ERROR_PERMANENT

        # 检查瞬时错误
        for keyword in _TRANSIENT_KEYWORDS:
            if keyword in error_msg or keyword in error_type_name:
                return ERROR_TRANSIENT

        return ERROR_UNKNOWN

    @staticmethod
    def is_retryable(error: Exception) -> bool:
        """
        判断错误是否可重试。

        瞬时错误和未知错误可重试，永久错误不可重试。

        Args:
            error: 异常对象。

        Returns:
            是否可重试。
        """
        error_type = ErrorClassifier.classify(error)
        return error_type in (ERROR_TRANSIENT, ERROR_UNKNOWN)

    @staticmethod
    def get_suggestion(error: Exception) -> str:
        """
        获取错误恢复建议。

        Args:
            error: 异常对象。

        Returns:
            建议文本。
        """
        error_msg = str(error).lower()

        for keyword, suggestion in _RECOVERY_SUGGESTIONS.items():
            if keyword in error_msg:
                return suggestion

        error_type = ErrorClassifier.classify(error)
        if error_type == ERROR_TRANSIENT:
            return "这是瞬时错误，稍后重试可能成功"
        elif error_type == ERROR_PERMANENT:
            return "这是永久错误，请检查配置或输入"
        else:
            return "未知错误类型，请查看详细错误信息"


class RetryPolicy:
    """
    重试策略。

    配置重试行为：最大重试次数、退避策略、抖动。
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
        jitter: bool = True,
    ) -> None:
        """
        初始化重试策略。

        Args:
            max_retries: 最大重试次数（不含首次执行）。
            base_delay: 初始延迟（秒）。
            max_delay: 最大延迟（秒）。
            backoff_factor: 退避因子（指数退避）。
            jitter: 是否添加随机抖动。
        """
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._backoff_factor = backoff_factor
        self._jitter = jitter

    @property
    def max_retries(self) -> int:
        return self._max_retries

    @property
    def base_delay(self) -> float:
        return self._base_delay

    @property
    def max_delay(self) -> float:
        return self._max_delay

    @property
    def backoff_factor(self) -> float:
        return self._backoff_factor

    @property
    def jitter(self) -> bool:
        return self._jitter

    def get_delay(self, attempt: int) -> float:
        """
        计算第N次重试的延迟时间。

        使用指数退避：delay = base_delay * (backoff_factor ^ attempt)
        添加随机抖动避免重试风暴。

        Args:
            attempt: 重试次数（0=首次失败后第一次重试）。

        Returns:
            延迟时间（秒）。
        """
        delay = self._base_delay * (self._backoff_factor ** attempt)
        delay = min(delay, self._max_delay)

        if self._jitter:
            # 添加0~50%的随机抖动
            delay = delay * (1.0 + random.random() * 0.5)

        return delay

    def to_dict(self) -> Dict[str, Any]:
        """转字典。"""
        return {
            "max_retries": self._max_retries,
            "base_delay": self._base_delay,
            "max_delay": self._max_delay,
            "backoff_factor": self._backoff_factor,
            "jitter": self._jitter,
        }


class RetryResult:
    """
    重试执行结果。

    Attributes:
        success: 是否最终成功。
        attempts: 总尝试次数（含首次）。
        final_exit_code: 最终退出码。
        errors: 每次尝试的错误信息列表。
        total_duration: 总耗时（秒）。
        delays: 每次重试前的延迟列表。
    """

    def __init__(
        self,
        success: bool = False,
        attempts: int = 0,
        final_exit_code: Optional[int] = None,
        errors: Optional[List[str]] = None,
        total_duration: float = 0.0,
        delays: Optional[List[float]] = None,
    ) -> None:
        self.success = success
        self.attempts = attempts
        self.final_exit_code = final_exit_code
        self.errors = errors or []
        self.total_duration = total_duration
        self.delays = delays or []

    def to_dict(self) -> Dict[str, Any]:
        """转字典。"""
        return {
            "success": self.success,
            "attempts": self.attempts,
            "final_exit_code": self.final_exit_code,
            "errors": self.errors,
            "total_duration": round(self.total_duration, 3),
            "delays": self.delays,
        }


class CircuitBreaker:
    """
    熔断器。

    防止级联故障：连续失败超过阈值时熔断，拒绝后续请求。
    经过冷却时间后自动尝试恢复（半开状态）。

    状态：
    - CLOSED: 正常，允许请求
    - OPEN: 熔断，拒绝请求
    - HALF_OPEN: 半开，允许试探性请求
    """

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half-open"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        """
        初始化熔断器。

        Args:
            failure_threshold: 连续失败阈值。
            recovery_timeout: 恢复超时（秒）。
        """
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._state = self.STATE_CLOSED
        self._last_failure_time: Optional[float] = None

    @property
    def state(self) -> str:
        """当前状态。"""
        if self._state == self.STATE_OPEN:
            # 检查是否应该转为半开
            if self._last_failure_time is not None:
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self._recovery_timeout:
                    self._state = self.STATE_HALF_OPEN
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def failure_threshold(self) -> int:
        return self._failure_threshold

    @property
    def recovery_timeout(self) -> float:
        return self._recovery_timeout

    def can_execute(self) -> bool:
        """是否允许执行。"""
        state = self.state  # 触发状态检查
        return state in (self.STATE_CLOSED, self.STATE_HALF_OPEN)

    def record_success(self) -> None:
        """记录成功。"""
        self._failure_count = 0
        self._state = self.STATE_CLOSED

    def record_failure(self) -> None:
        """记录失败。"""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._state == self.STATE_HALF_OPEN:
            # 半开状态下失败，重新熔断
            self._state = self.STATE_OPEN
        elif self._failure_count >= self._failure_threshold:
            self._state = self.STATE_OPEN

    def reset(self) -> None:
        """重置熔断器。"""
        self._failure_count = 0
        self._state = self.STATE_CLOSED
        self._last_failure_time = None

    def to_dict(self) -> Dict[str, Any]:
        """转字典。"""
        return {
            "state": self.state,
            "failure_count": self._failure_count,
            "failure_threshold": self._failure_threshold,
            "recovery_timeout": self._recovery_timeout,
        }


class RetryExecutor:
    """
    重试执行器。

    执行函数并在失败时按策略重试。
    """

    def __init__(
        self,
        policy: Optional[RetryPolicy] = None,
        breaker: Optional[CircuitBreaker] = None,
        verbose: bool = False,
    ) -> None:
        """
        初始化执行器。

        Args:
            policy: 重试策略。
            breaker: 熔断器。
            verbose: 详细输出。
        """
        self._policy = policy or RetryPolicy()
        self._breaker = breaker or CircuitBreaker()
        self._verbose = verbose

    @property
    def policy(self) -> RetryPolicy:
        return self._policy

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    def execute(
        self,
        func: Callable[[], Tuple[int, str]],
        command_name: str = "",
    ) -> RetryResult:
        """
        执行函数并按策略重试。

        Args:
            func: 要执行的函数，返回(退出码, 输出)。
            command_name: 命令名（用于日志）。

        Returns:
            重试结果。
        """
        result = RetryResult()
        start_time = time.time()

        # 检查熔断器
        if not self._breaker.can_execute():
            if self._verbose:
                print(_c(f"[CIRCUIT-OPEN] Circuit breaker is open, skipping.", _COLOR_RED))
            result.success = False
            result.errors.append("Circuit breaker is open")
            result.total_duration = time.time() - start_time
            return result

        last_error: Optional[str] = None
        last_exit_code: Optional[int] = None

        for attempt in range(self._policy.max_retries + 1):
            result.attempts = attempt + 1

            if self._verbose and attempt > 0:
                print(_c(f"[RETRY] Attempt {attempt + 1}/{self._policy.max_retries + 1}", _COLOR_YELLOW))

            try:
                exit_code, output = func()

                if exit_code == 0:
                    # 成功
                    self._breaker.record_success()
                    result.success = True
                    result.final_exit_code = 0
                    result.total_duration = time.time() - start_time
                    return result

                # 非零退出码
                last_exit_code = exit_code
                last_error = f"Exit code {exit_code}: {output[:200]}"

                # 判断是否可重试
                error_exc = Exception(last_error)
                if not ErrorClassifier.is_retryable(error_exc):
                    # 永久错误，不重试
                    if self._verbose:
                        print(_c(f"[PERMANENT] {last_error}", _COLOR_RED))
                    result.errors.append(last_error)
                    break

                result.errors.append(last_error)

                if self._verbose:
                    print(_c(f"[FAIL] {last_error}", _COLOR_RED))

            except Exception as exc:
                last_error = str(exc)
                last_exit_code = -1
                result.errors.append(last_error)

                if not ErrorClassifier.is_retryable(exc):
                    if self._verbose:
                        print(_c(f"[PERMANENT] {exc}", _COLOR_RED))
                    break

                if self._verbose:
                    print(_c(f"[FAIL] {exc}", _COLOR_RED))

            # 记录熔断器失败
            self._breaker.record_failure()

            # 检查熔断器
            if not self._breaker.can_execute():
                if self._verbose:
                    print(_c(f"[CIRCUIT-OPEN] Circuit breaker opened.", _COLOR_RED))
                break

            # 计算延迟并等待
            if attempt < self._policy.max_retries:
                delay = self._policy.get_delay(attempt)
                result.delays.append(delay)
                if self._verbose:
                    print(_c(f"[WAIT] Retrying in {delay:.1f}s...", _COLOR_DIM))
                time.sleep(delay)

        result.success = False
        result.final_exit_code = last_exit_code
        result.total_duration = time.time() - start_time
        return result


def cmd_retry_run(args: argparse.Namespace) -> int:
    """执行带重试的命令。"""
    cmd_parts = args.command

    if not cmd_parts:
        print(_c("[ERROR] No command specified.", _COLOR_RED))
        return 1

    # 去掉前导 "agent" 如果存在
    if cmd_parts[0] == "agent":
        cmd_parts = cmd_parts[1:]

    if not cmd_parts:
        print(_c("[ERROR] No command specified.", _COLOR_RED))
        return 1

    # 构建重试策略
    policy = RetryPolicy(
        max_retries=args.max_retries,
        base_delay=args.base_delay,
        max_delay=args.max_delay,
        backoff_factor=args.backoff,
        jitter=not args.no_jitter,
    )

    breaker = CircuitBreaker(
        failure_threshold=args.failure_threshold,
        recovery_timeout=args.recovery_timeout,
    )

    executor = RetryExecutor(policy=policy, breaker=breaker, verbose=args.verbose)

    print(_c(f"=== Retry Execution ===", _COLOR_BOLD))
    print(f"  {_c('Command:', _COLOR_CYAN)} {' '.join(cmd_parts)}")
    print(f"  {_c('Max retries:', _COLOR_CYAN)} {policy.max_retries}")
    print(f"  {_c('Base delay:', _COLOR_CYAN)} {policy.base_delay}s")
    print(f"  {_c('Backoff:', _COLOR_CYAN)} {policy.backoff_factor}x")
    print()

    def _run_command() -> Tuple[int, str]:
        """执行命令的包装函数。"""
        import concurrent.futures

        captured = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = captured
        sys.stderr = captured

        result_box: Dict[str, Any] = {"code": 0}

        def _run_in_thread() -> None:
            try:
                from agent_core.cli import main
                result_box["code"] = main(cmd_parts)
            except SystemExit as e:
                result_box["code"] = e.code if isinstance(e.code, int) else 1
            except Exception as exc:
                captured.write(f"[ERROR] {exc}\n")
                result_box["code"] = 1

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_run_in_thread)
                future.result()
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        return result_box["code"], captured.getvalue()

    result = executor.execute(_run_command, " ".join(cmd_parts))

    # 显示结果
    print()
    print(_c("=== Retry Result ===", _COLOR_BOLD))
    status_color = _COLOR_GREEN if result.success else _COLOR_RED
    status_text = "SUCCESS" if result.success else "FAILED"
    print(f"  {_c('Status:', _COLOR_CYAN)} {_c(status_text, status_color)}")
    print(f"  {_c('Attempts:', _COLOR_CYAN)} {result.attempts}/{policy.max_retries + 1}")
    print(f"  {_c('Exit code:', _COLOR_CYAN)} {result.final_exit_code}")
    print(f"  {_c('Duration:', _COLOR_CYAN)} {result.total_duration:.2f}s")

    if result.errors:
        print()
        print(_c("Errors:", _COLOR_CYAN))
        for i, err in enumerate(result.errors, 1):
            print(f"  {_c(str(i), _COLOR_DIM)}. {err[:200]}")

    if result.delays:
        print()
        print(_c("Retry delays:", _COLOR_CYAN))
        for i, delay in enumerate(result.delays, 1):
            print(f"  {_c(str(i), _COLOR_DIM)}. {delay:.2f}s")

    # 显示恢复建议
    if not result.success and result.errors:
        last_error = result.errors[-1]
        suggestion = ErrorClassifier.get_suggestion(Exception(last_error))
        print()
        print(_c(f"Suggestion: {suggestion}", _COLOR_YELLOW))

    return 0 if result.success else 1


def cmd_retry_status(args: argparse.Namespace) -> int:
    """显示重试系统状态。"""
    print(_c("=== Retry System Status ===", _COLOR_BOLD))
    print()
    print(_c("Default Retry Policy:", _COLOR_CYAN))
    default_policy = RetryPolicy()
    d = default_policy.to_dict()
    print(f"  Max retries:     {d['max_retries']}")
    print(f"  Base delay:      {d['base_delay']}s")
    print(f"  Max delay:       {d['max_delay']}s")
    print(f"  Backoff factor:  {d['backoff_factor']}")
    print(f"  Jitter:          {d['jitter']}")
    print()

    print(_c("Circuit Breaker:", _COLOR_CYAN))
    default_breaker = CircuitBreaker()
    b = default_breaker.to_dict()
    print(f"  State:              {_c(b['state'], _COLOR_GREEN)}")
    print(f"  Failure count:      {b['failure_count']}")
    print(f"  Failure threshold:  {b['failure_threshold']}")
    print(f"  Recovery timeout:   {b['recovery_timeout']}s")
    print()

    print(_c("Error Classification:", _COLOR_CYAN))
    print(f"  Transient keywords: {len(_TRANSIENT_KEYWORDS)}")
    print(f"  Permanent keywords: {len(_PERMANENT_KEYWORDS)}")
    print(f"  Recovery suggestions: {len(_RECOVERY_SUGGESTIONS)}")
    print()

    print(_c("Tip: Use 'agent retry run <command>' to retry a command.", _COLOR_DIM))
    return 0


def cmd_retry_reset(args: argparse.Namespace) -> int:
    """重置熔断器。"""
    print(_c("[OK] Circuit breaker reset.", _COLOR_GREEN))
    return 0


def handle_retry(args: argparse.Namespace) -> int:
    """
    处理retry命令。

    Args:
        args: 命令行参数。

    Returns:
        退出码。
    """
    action = getattr(args, "retry_action", None)

    if action is None or action == "run":
        return cmd_retry_run(args)
    elif action == "status":
        return cmd_retry_status(args)
    elif action == "reset":
        return cmd_retry_reset(args)
    else:
        print(_c(f"[ERROR] Unknown retry action: {action}", _COLOR_RED))
        return 1


def add_retry_subparser(subparsers: argparse._SubParsersAction) -> None:
    """
    注册retry子命令。

    Args:
        subparsers: argparse子命令解析器。
    """
    retry_parser = subparsers.add_parser(
        "retry",
        help="错误恢复与自动重试（run/status/reset）",
        description="执行命令并在失败时自动重试，支持指数退避和熔断器。",
    )
    retry_sub = retry_parser.add_subparsers(dest="retry_action")

    # retry run
    run_parser = retry_sub.add_parser("run", help="执行带重试的命令")
    run_parser.add_argument(
        "command",
        nargs="+",
        help="要执行的命令（如 version status）",
    )
    run_parser.add_argument(
        "--max-retries", type=int, default=3,
        help="最大重试次数（默认: 3）",
    )
    run_parser.add_argument(
        "--base-delay", type=float, default=1.0,
        help="初始延迟秒数（默认: 1.0）",
    )
    run_parser.add_argument(
        "--max-delay", type=float, default=60.0,
        help="最大延迟秒数（默认: 60.0）",
    )
    run_parser.add_argument(
        "--backoff", type=float, default=2.0,
        help="退避因子（默认: 2.0）",
    )
    run_parser.add_argument(
        "--no-jitter", action="store_true",
        help="禁用随机抖动",
    )
    run_parser.add_argument(
        "--failure-threshold", type=int, default=5,
        help="熔断器失败阈值（默认: 5）",
    )
    run_parser.add_argument(
        "--recovery-timeout", type=float, default=60.0,
        help="熔断器恢复超时秒数（默认: 60.0）",
    )
    run_parser.add_argument(
        "-V", "--verbose", action="store_true",
        help="详细输出",
    )

    # retry status
    retry_sub.add_parser("status", help="显示重试系统状态")

    # retry reset
    retry_sub.add_parser("reset", help="重置熔断器")

    # retry（无子命令时需要command参数）
    retry_parser.add_argument(
        "command",
        nargs="*",
        help="要执行的命令（默认run）",
    )
    retry_parser.add_argument(
        "--max-retries", type=int, default=3,
        help="最大重试次数",
    )
    retry_parser.add_argument(
        "--base-delay", type=float, default=1.0,
        help="初始延迟秒数",
    )
    retry_parser.add_argument(
        "--max-delay", type=float, default=60.0,
        help="最大延迟秒数",
    )
    retry_parser.add_argument(
        "--backoff", type=float, default=2.0,
        help="退避因子",
    )
    retry_parser.add_argument(
        "--no-jitter", action="store_true",
        help="禁用随机抖动",
    )
    retry_parser.add_argument(
        "--failure-threshold", type=int, default=5,
        help="熔断器失败阈值",
    )
    retry_parser.add_argument(
        "--recovery-timeout", type=float, default=60.0,
        help="熔断器恢复超时秒数",
    )
    retry_parser.add_argument(
        "-V", "--verbose", action="store_true",
        help="详细输出",
    )
