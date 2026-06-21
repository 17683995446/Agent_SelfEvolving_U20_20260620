"""
批量操作与管道支持。

第一性原理：
- 用户经常需要执行多个相关命令，逐个手动执行繁琐易错
- 批量执行让自动化成为可能，降低重复劳动
- 管道支持让命令输出可链式传递，提升组合能力
- 条件执行（&&/||/;）让操作流程可表达依赖关系

设计要点：
- BatchExecutor: 批量执行器
- 支持顺序/条件/管道三种执行模式
- 支持从文件或内联字符串加载命令
- 支持注释（#）和空行
- 支持dry-run预览
- 支持continue-on-error
- 执行结果跟踪（成功/失败/跳过）
- batch CLI: run/preview
"""

import argparse
import io
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

# 颜色
_COLOR_RESET = "\033[0m"
_COLOR_RED = "\033[31m"
_COLOR_GREEN = "\033[32m"
_COLOR_YELLOW = "\033[33m"
_COLOR_CYAN = "\033[36m"
_COLOR_BOLD = "\033[1m"
_COLOR_DIM = "\033[2m"

_COLOR_ENABLED = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False


def _c(text: str, color: str) -> str:
    """添加颜色。"""
    if not _COLOR_ENABLED:
        return text
    return f"{color}{text}{_COLOR_RESET}"


# 操作符定义
_OP_AND = "&&"   # 前一命令成功才执行下一个
_OP_OR = "||"    # 前一命令失败才执行下一个
_OP_SEMI = ";"   # 无条件顺序执行
_OP_PIPE = "|"   # 管道（输出传递）

_ALL_OPS = {_OP_AND, _OP_OR, _OP_SEMI, _OP_PIPE}


class BatchResult:
    """
    单条命令执行结果。

    Attributes:
        command: 执行的命令。
        exit_code: 退出码（None表示未执行）。
        output: 输出文本。
        skipped: 是否被跳过（条件不满足）。
        duration: 执行时长（秒）。
    """

    def __init__(
        self,
        command: str,
        exit_code: Optional[int] = None,
        output: str = "",
        skipped: bool = False,
        duration: float = 0.0,
    ) -> None:
        self.command = command
        self.exit_code = exit_code
        self.output = output
        self.skipped = skipped
        self.duration = duration

    @property
    def success(self) -> bool:
        """是否成功。"""
        return self.exit_code == 0

    @property
    def executed(self) -> bool:
        """是否实际执行（非跳过）。"""
        return not self.skipped

    def to_dict(self) -> Dict[str, Any]:
        """转字典。"""
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "output": self.output,
            "skipped": self.skipped,
            "duration": self.duration,
            "success": self.success,
        }


def parse_batch_content(content: str) -> List[str]:
    """
    解析批量内容为命令列表。

    规则：
    - 每行一条命令（支持行内操作符 &&/||/;/|）
    - #开头为注释，忽略
    - 空行忽略
    - 行尾续行符\\支持多行命令

    Args:
        content: 批量内容文本。

    Returns:
        命令列表。
    """
    if not content:
        return []

    commands: List[str] = []
    lines = content.splitlines()

    # 处理续行符
    merged_lines: List[str] = []
    buffer = ""
    for line in lines:
        stripped = line.rstrip()
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
        else:
            buffer += stripped
            merged_lines.append(buffer)
            buffer = ""
    if buffer:
        merged_lines.append(buffer)

    for line in merged_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        commands.append(stripped)

    return commands


def parse_command_chain(command: str) -> List[Tuple[str, str]]:
    """
    解析带操作符的命令链。

    将 "cmd1 && cmd2 || cmd3" 解析为:
    [("cmd1", ""), ("cmd2", "&&"), ("cmd3", "||")]

    Args:
        command: 命令链字符串。

    Returns:
        (命令, 前置操作符) 列表。第一条命令的操作符为空字符串。
    """
    if not command:
        return []

    # 按操作符分割（保留操作符）
    # 操作符附加到后续命令上（前置操作符）
    parts: List[Tuple[str, str]] = []
    remaining = command.strip()
    current_cmd = ""
    pending_op = ""
    i = 0

    while i < len(remaining):
        # 检查两个字符的操作符
        two_char = remaining[i:i + 2]
        if two_char in (_OP_AND, _OP_OR):
            if current_cmd.strip():
                parts.append((current_cmd.strip(), pending_op))
                current_cmd = ""
            pending_op = two_char
            i += 2
            continue

        # 检查单字符操作符
        one_char = remaining[i]
        if one_char == _OP_SEMI or one_char == _OP_PIPE:
            if current_cmd.strip():
                parts.append((current_cmd.strip(), pending_op))
                current_cmd = ""
            pending_op = one_char
            i += 1
            continue

        current_cmd += remaining[i]
        i += 1

    if current_cmd.strip():
        parts.append((current_cmd.strip(), pending_op))

    return parts


class BatchExecutor:
    """
    批量命令执行器。

    执行命令列表，支持条件执行和管道。
    """

    def __init__(
        self,
        continue_on_error: bool = False,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> None:
        """
        初始化执行器。

        Args:
            continue_on_error: 出错时是否继续执行后续命令。
            dry_run: 仅预览不实际执行。
            verbose: 详细输出。
        """
        self._continue_on_error = continue_on_error
        self._dry_run = dry_run
        self._verbose = verbose
        self._results: List[BatchResult] = []

    @property
    def results(self) -> List[BatchResult]:
        """所有执行结果。"""
        return list(self._results)

    def execute(self, commands: List[str]) -> List[BatchResult]:
        """
        执行命令列表。

        Args:
            commands: 命令列表。

        Returns:
            执行结果列表。
        """
        self._results = []

        for cmd in commands:
            result = self._execute_command(cmd)
            self._results.append(result)

            # 非continue_on_error模式下，失败即停止
            if not self._continue_on_error and result.executed and not result.success:
                # 标记后续为跳过
                idx = commands.index(cmd)
                for remaining_cmd in commands[idx + 1:]:
                    self._results.append(BatchResult(
                        command=remaining_cmd,
                        skipped=True,
                    ))
                break

        return self._results

    def _execute_command(self, command: str) -> BatchResult:
        """
        执行单条命令（可能含操作符链）。

        Args:
            command: 命令字符串。

        Returns:
            执行结果。
        """
        chain = parse_command_chain(command)

        if not chain:
            return BatchResult(command=command, exit_code=0)

        if self._dry_run:
            # dry-run模式：仅打印不执行
            print(_c(f"[DRY-RUN] {command}", _COLOR_DIM))
            return BatchResult(command=command, exit_code=0, output="[dry-run]")

        last_result: Optional[BatchResult] = None
        last_output = ""

        for cmd_text, op in chain:
            # 判断是否需要执行
            should_execute = True

            if op == _OP_AND and last_result is not None:
                # &&: 前一命令成功才执行
                should_execute = last_result.success
            elif op == _OP_OR and last_result is not None:
                # ||: 前一命令失败才执行
                should_execute = not last_result.success
            elif op == _OP_SEMI:
                # ;: 无条件执行
                should_execute = True
            elif op == _OP_PIPE:
                # |: 管道，无条件执行，但传递前一命令输出
                should_execute = True

            if not should_execute:
                if self._verbose:
                    print(_c(f"[SKIP] {cmd_text} (条件不满足)", _COLOR_YELLOW))
                last_result = BatchResult(
                    command=cmd_text,
                    skipped=True,
                )
                continue

            # 执行命令
            if self._verbose:
                print(_c(f"[RUN] {cmd_text}", _COLOR_CYAN))

            start_time = time.time()
            exit_code, output = self._run_cli_command(cmd_text, last_output if op == _OP_PIPE else "")
            duration = time.time() - start_time

            last_result = BatchResult(
                command=cmd_text,
                exit_code=exit_code,
                output=output,
                duration=duration,
            )
            last_output = output

            # 显示输出
            if output and self._verbose:
                for line in output.splitlines():
                    print(f"  {line}")

            # 状态指示
            if exit_code == 0:
                if self._verbose:
                    print(_c(f"[OK] {cmd_text} ({duration:.2f}s)", _COLOR_GREEN))
            else:
                if self._verbose:
                    print(_c(f"[FAIL] {cmd_text} (exit={exit_code})", _COLOR_RED))

        return last_result or BatchResult(command=command, exit_code=0)

    def _run_cli_command(self, cmd_text: str, stdin_input: str = "") -> Tuple[int, str]:
        """
        执行单条CLI命令。

        使用线程池在独立线程中执行，避免asyncio.run()嵌套问题
        （batch本身在asyncio.run中，子命令也通过main()调用asyncio.run）。

        Args:
            cmd_text: 命令文本。
            stdin_input: 标准输入内容（管道）。

        Returns:
            (退出码, 输出文本)。
        """
        # 解析参数
        parts = cmd_text.split()
        if not parts:
            return 0, ""

        # 去掉前导 "agent" 如果存在
        if parts[0] == "agent":
            parts = parts[1:]

        if not parts:
            return 0, ""

        # 捕获stdout（在线程外设置，线程内继承）
        captured = io.StringIO()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_stdin = sys.stdin

        if stdin_input:
            sys.stdin = io.StringIO(stdin_input)

        sys.stdout = captured
        sys.stderr = captured

        # 在独立线程中执行，避免asyncio事件循环嵌套
        import concurrent.futures
        result_box: Dict[str, Any] = {"code": 0}

        def _run_in_thread() -> None:
            try:
                from agent_core.cli import main
                result_box["code"] = main(parts)
            except SystemExit as e:
                result_box["code"] = e.code if isinstance(e.code, int) else 1
            except Exception as exc:
                captured.write(f"[ERROR] {exc}\n")
                result_box["code"] = 1

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_run_in_thread)
                future.result()
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.stdin = old_stdin

        return result_box["code"], captured.getvalue()

    def summary(self) -> Dict[str, Any]:
        """
        生成执行摘要。

        Returns:
            摘要字典。
        """
        total = len(self._results)
        executed = sum(1 for r in self._results if r.executed)
        skipped = sum(1 for r in self._results if r.skipped)
        succeeded = sum(1 for r in self._results if r.executed and r.success)
        failed = sum(1 for r in self._results if r.executed and not r.success)
        total_duration = sum(r.duration for r in self._results)

        return {
            "total": total,
            "executed": executed,
            "skipped": skipped,
            "succeeded": succeeded,
            "failed": failed,
            "total_duration": round(total_duration, 3),
            "all_success": failed == 0 and skipped == 0,
        }


def cmd_batch_run(args: argparse.Namespace) -> int:
    """执行批量命令。"""
    # 获取命令源
    commands: List[str] = []

    if args.file:
        # 从文件读取
        if not os.path.exists(args.file):
            print(_c(f"[ERROR] Batch file not found: {args.file}", _COLOR_RED))
            return 1
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as exc:
            print(_c(f"[ERROR] Failed to read batch file: {exc}", _COLOR_RED))
            return 1
        commands = parse_batch_content(content)
    elif args.commands:
        # 内联命令
        commands = parse_batch_content(args.commands)
    else:
        # 从stdin读取
        try:
            content = sys.stdin.read()
            commands = parse_batch_content(content)
        except Exception:
            pass

    if not commands:
        print(_c("[WARN] No commands to execute.", _COLOR_YELLOW))
        return 0

    # 显示要执行的命令
    print(_c(f"=== Batch Execution ({len(commands)} commands) ===", _COLOR_BOLD))
    if args.dry_run:
        print(_c("[DRY-RUN MODE]", _COLOR_YELLOW))
    print()

    for i, cmd in enumerate(commands, 1):
        print(f"  {_c(str(i), _COLOR_DIM)}. {cmd}")
    print()

    # 执行
    executor = BatchExecutor(
        continue_on_error=args.continue_on_error,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    executor.execute(commands)

    # 显示摘要
    summary = executor.summary()
    print()
    print(_c("=== Summary ===", _COLOR_BOLD))
    print(f"  {_c('Total:', _COLOR_CYAN)}      {summary['total']}")
    print(f"  {_c('Executed:', _COLOR_CYAN)}   {summary['executed']}")
    print(f"  {_c('Succeeded:', _COLOR_GREEN)} {summary['succeeded']}")
    print(f"  {_c('Failed:', _COLOR_RED)}     {summary['failed']}")
    print(f"  {_c('Skipped:', _COLOR_YELLOW)}  {summary['skipped']}")
    print(f"  {_c('Duration:', _COLOR_CYAN)}   {summary['total_duration']}s")

    return 0 if summary["failed"] == 0 else 1


def cmd_batch_preview(args: argparse.Namespace) -> int:
    """预览批量命令（不执行）。"""
    # 强制dry-run
    args.dry_run = True
    args.verbose = True
    return cmd_batch_run(args)


def handle_batch(args: argparse.Namespace) -> int:
    """
    处理batch命令。

    Args:
        args: 命令行参数。

    Returns:
        退出码。
    """
    action = getattr(args, "batch_action", None)

    if action is None or action == "run":
        return cmd_batch_run(args)
    elif action == "preview":
        return cmd_batch_preview(args)
    else:
        print(_c(f"[ERROR] Unknown batch action: {action}", _COLOR_RED))
        return 1


def add_batch_subparser(subparsers: argparse._SubParsersAction) -> None:
    """
    注册batch子命令。

    Args:
        subparsers: argparse子命令解析器。
    """
    batch_parser = subparsers.add_parser(
        "batch",
        help="批量执行命令（支持&&/||/;/|操作符）",
        description="批量执行多个命令，支持条件执行、管道和文件加载。",
    )
    batch_sub = batch_parser.add_subparsers(dest="batch_action")

    # batch run
    run_parser = batch_sub.add_parser("run", help="执行批量命令")
    run_parser.add_argument(
        "-f", "--file",
        default=None,
        help="批量命令文件路径",
    )
    run_parser.add_argument(
        "-c", "--commands",
        default=None,
        help="内联命令字符串（用换行分隔）",
    )
    run_parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="出错时继续执行后续命令",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览不实际执行",
    )
    run_parser.add_argument(
        "-V", "--verbose",
        action="store_true",
        help="详细输出",
    )

    # batch preview
    preview_parser = batch_sub.add_parser("preview", help="预览批量命令（不执行）")
    preview_parser.add_argument(
        "-f", "--file",
        default=None,
        help="批量命令文件路径",
    )
    preview_parser.add_argument(
        "-c", "--commands",
        default=None,
        help="内联命令字符串",
    )

    # batch（无子命令时默认run）
    batch_parser.add_argument(
        "-f", "--file",
        default=None,
        help="批量命令文件路径（默认run）",
    )
    batch_parser.add_argument(
        "-c", "--commands",
        default=None,
        help="内联命令字符串（默认run）",
    )
    batch_parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="出错时继续执行",
    )
    batch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览",
    )
    batch_parser.add_argument(
        "-V", "--verbose",
        action="store_true",
        help="详细输出",
    )
