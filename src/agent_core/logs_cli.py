"""
日志查看/过滤/分析CLI模块。

将LogAnalyzer的日志分析能力暴露到CLI，用户无需手写grep/awk即可：
- 查看日志（支持级别过滤、行数限制）
- 实时跟踪日志（tail -f语义）
- 智能分析日志（异常检测、错误趋势、洞察报告）
- 关键词搜索日志

第一性原理：
- 日志是系统运行的"病历"，用户需要便捷工具查阅而非手写管道
- 分析能力已存在于LogAnalyzer，只需暴露入口
- 统一CLI入口降低认知负荷：agent logs <action>
"""

import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_core.common.logger import get_logger

# 默认日志文件搜索路径（按优先级）
_DEFAULT_LOG_PATHS = [
    "logs/agent.log",
    "agent.log",
    "logs/self_evolving_agent.log",
    "self_evolving_agent.log",
]

# 颜色
_COLOR_RESET = "\033[0m"
_COLOR_RED = "\033[31m"
_COLOR_GREEN = "\033[32m"
_COLOR_YELLOW = "\033[33m"
_COLOR_CYAN = "\033[36m"
_COLOR_BOLD = "\033[1m"
_COLOR_BLUE = "\033[34m"
_COLOR_MAGENTA = "\033[35m"

# 级别到颜色的映射
_LEVEL_COLORS = {
    "DEBUG": _COLOR_BLUE,
    "INFO": _COLOR_GREEN,
    "WARNING": _COLOR_YELLOW,
    "ERROR": _COLOR_RED,
    "CRITICAL": _COLOR_MAGENTA,
}

_COLOR_ENABLED = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False


def _colorize(text: str, color: str) -> str:
    """添加颜色（非TTY环境不添加）。"""
    if not _COLOR_ENABLED:
        return text
    return f"{color}{text}{_COLOR_RESET}"


def _print_error(msg: str) -> None:
    """打印错误信息。"""
    print(f"{_colorize('[ERROR]', _COLOR_RED)} {msg}", file=sys.stderr)


def _print_info(msg: str) -> None:
    """打印信息。"""
    print(f"{_colorize('[INFO]', _COLOR_BLUE)} {msg}")


def _print_success(msg: str) -> None:
    """打印成功信息。"""
    print(f"{_colorize('[OK]', _COLOR_GREEN)} {msg}")


def _resolve_log_path(file_arg: Optional[str]) -> Optional[str]:
    """
    解析日志文件路径。

    优先级：--file参数 > 默认搜索路径 > None

    Args:
        file_arg: 用户通过--file指定的路径。

    Returns:
        存在的日志文件路径，或None。
    """
    if file_arg:
        if os.path.isfile(file_arg):
            return file_arg
        _print_error(f"Log file not found: {file_arg}")
        return None

    # 搜索默认路径
    for candidate in _DEFAULT_LOG_PATHS:
        if os.path.isfile(candidate):
            return candidate

    _print_error(
        "No log file found. Specify with --file <path>. "
        f"Searched: {', '.join(_DEFAULT_LOG_PATHS)}"
    )
    return None


def _colorize_log_line(line: str) -> str:
    """根据日志级别着色一行日志。"""
    if not _COLOR_ENABLED:
        return line
    # 匹配 [LEVEL] 模式
    match = re.search(r'\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\]', line)
    if match:
        level = match.group(1)
        color = _LEVEL_COLORS.get(level, _COLOR_RESET)
        return f"{color}{line}{_COLOR_RESET}"
    return line


def cmd_logs_show(args) -> int:
    """
    显示日志文件内容。

    支持按级别过滤和行数限制。
    """
    log_path = _resolve_log_path(getattr(args, "file", None))
    if log_path is None:
        return 1

    lines_limit = getattr(args, "lines", 50)
    level_filter = getattr(args, "level", None)

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
    except OSError as exc:
        _print_error(f"Failed to read log file: {exc}")
        return 1

    # 级别过滤
    if level_filter:
        filtered = [
            line for line in all_lines
            if f"[{level_filter}]" in line
        ]
    else:
        filtered = all_lines

    # 取最后N行
    display_lines = filtered[-lines_limit:] if lines_limit > 0 else filtered

    print(_colorize(f"=== {log_path} (last {len(display_lines)} lines) ===",
                    _COLOR_BOLD))
    for line in display_lines:
        print(_colorize_log_line(line.rstrip()))

    return 0


def cmd_logs_tail(args) -> int:
    """
    实时跟踪日志文件（类似tail -f）。

    持续输出新增日志行，直到Ctrl+C。
    """
    log_path = _resolve_log_path(getattr(args, "file", None))
    if log_path is None:
        return 1

    _print_info(f"Tailing {log_path} (Ctrl+C to stop)...")

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            # 先输出已有内容最后10行
            lines = f.readlines()
            for line in lines[-10:]:
                print(_colorize_log_line(line.rstrip()))

            # 持续跟踪
            interval = 0.5
            while True:
                line = f.readline()
                if line:
                    print(_colorize_log_line(line.rstrip()))
                else:
                    time.sleep(interval)
    except KeyboardInterrupt:
        print(_colorize("\nStopped.", _COLOR_CYAN))
        return 0
    except OSError as exc:
        _print_error(f"Failed to tail log file: {exc}")
        return 1


def cmd_logs_analyze(args) -> int:
    """
    使用LogAnalyzer智能分析日志。

    检测异常模式、错误频率趋势、生成洞察报告。
    """
    log_path = _resolve_log_path(getattr(args, "file", None))
    if log_path is None:
        return 1

    # 延迟导入LogAnalyzer（位于core/目录）
    import sys as _sys
    core_dir = os.path.join(os.getcwd(), "core")
    if os.path.isdir(core_dir) and core_dir not in _sys.path:
        _sys.path.insert(0, core_dir)

    try:
        from log_analyzer import LogAnalyzer
    except ImportError:
        _print_error(
            "LogAnalyzer not available. Ensure core/ directory is in path."
        )
        return 1

    analyzer = LogAnalyzer()
    entries = analyzer.parse_log_file(Path(log_path))

    if not entries:
        _print_error(f"No parseable log entries found in {log_path}")
        return 1

    print(_colorize("=== Log Analysis Report ===", _COLOR_BOLD))
    print(f"  File:           {log_path}")
    print(f"  Parsed Entries: {len(entries)}")

    # 统计
    stats = analyzer.get_stats()
    print(f"  Error Rate:     {stats['error_rate']*100:.1f}%")
    print()

    # 错误频率趋势
    freq = analyzer.analyze_error_frequency()
    print(_colorize("--- Error Frequency ---", _COLOR_CYAN))
    print(f"  Total Entries:  {freq['total_entries']}")
    print(f"  Error Count:    {freq['error_count']}")
    print(f"  Error Rate:     {freq['error_rate']*100:.1f}%")
    trend = freq['trend']
    trend_color = _COLOR_RED if trend == "increasing" else _COLOR_GREEN if trend == "decreasing" else _COLOR_YELLOW
    print(f"  Trend:          {_colorize(trend, trend_color)}")
    print(f"  First Half:     {freq['first_half_rate']*100:.1f}%")
    print(f"  Second Half:    {freq['second_half_rate']*100:.1f}%")
    print()

    # 异常模式检测
    anomalies = analyzer.detect_anomaly_patterns()
    print(_colorize(f"--- Anomaly Patterns ({len(anomalies)}) ---", _COLOR_CYAN))
    if anomalies:
        for a in anomalies:
            severity = a.get('severity', 0)
            sev_color = _COLOR_RED if severity > 0.5 else _COLOR_YELLOW
            anomaly_type = a.get('type', 'unknown')
            print(f"  {_colorize(f'[{anomaly_type}]', sev_color)} "
                  f"(severity: {severity:.2f})")
            print(f"    {a.get('description', '')}")
    else:
        print(f"  {_colorize('No anomalies detected', _COLOR_GREEN)}")
    print()

    # 洞察报告
    insights = analyzer.generate_insights()
    print(_colorize(f"--- Insights ({len(insights)}) ---", _COLOR_CYAN))
    if insights:
        for insight in insights:
            print(f"  {_colorize('•', _COLOR_MAGENTA)} {insight}")
    else:
        print(f"  {_colorize('No specific insights', _COLOR_YELLOW)}")

    return 0


def cmd_logs_grep(args) -> int:
    """
    在日志中搜索关键词。

    支持正则表达式和上下文行。
    """
    log_path = _resolve_log_path(getattr(args, "file", None))
    if log_path is None:
        return 1

    pattern_str = getattr(args, "pattern", None)
    if not pattern_str:
        _print_error("Pattern is required for grep")
        return 1

    context = getattr(args, "context", 0)
    ignore_case = getattr(args, "ignore_case", False)

    flags = re.IGNORECASE if ignore_case else 0
    try:
        pattern = re.compile(pattern_str, flags)
    except re.error as exc:
        _print_error(f"Invalid regex pattern: {exc}")
        return 1

    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError as exc:
        _print_error(f"Failed to read log file: {exc}")
        return 1

    matches = []
    for i, line in enumerate(lines):
        if pattern.search(line):
            matches.append(i)

    if not matches:
        print(_colorize("No matches found", _COLOR_YELLOW))
        return 0

    match_word = "match" if len(matches) == 1 else "matches"
    print(_colorize(f"=== {len(matches)} {match_word} in {log_path} ===",
                    _COLOR_BOLD))

    for idx in matches:
        # 上下文行
        start = max(0, idx - context)
        end = min(len(lines), idx + context + 1)
        for j in range(start, end):
            prefix = ">>" if j == idx else "  "
            line_content = lines[j].rstrip()
            if j == idx:
                # 高亮匹配部分
                line_content = pattern.sub(
                    lambda m: _colorize(m.group(), _COLOR_BOLD),
                    line_content,
                ) if _COLOR_ENABLED else line_content
            print(f"{prefix} {_colorize_log_line(line_content)}")
        if context > 0 and idx != matches[-1]:
            print(_colorize("--", _COLOR_CYAN))

    return 0


def add_logs_subparser(subparsers) -> None:
    """
    注册logs子命令组到CLI解析器。

    Args:
        subparsers: argparse子命令解析器组。
    """
    logs_parser = subparsers.add_parser(
        "logs",
        help="日志查看/过滤/分析",
        description="日志查看、过滤、智能分析工具",
    )
    logs_sub = logs_parser.add_subparsers(dest="logs_action")

    # logs show
    show_parser = logs_sub.add_parser(
        "show", help="显示日志内容（默认动作）"
    )
    show_parser.add_argument(
        "--file", "-f", default=None,
        help="日志文件路径（默认自动搜索）"
    )
    show_parser.add_argument(
        "--lines", "-n", type=int, default=50,
        help="显示最后N行（默认50）"
    )
    show_parser.add_argument(
        "--level", default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="按日志级别过滤"
    )

    # logs tail
    tail_parser = logs_sub.add_parser(
        "tail", help="实时跟踪日志（tail -f）"
    )
    tail_parser.add_argument(
        "--file", "-f", default=None,
        help="日志文件路径"
    )

    # logs analyze
    analyze_parser = logs_sub.add_parser(
        "analyze", help="智能分析日志（异常检测、趋势、洞察）"
    )
    analyze_parser.add_argument(
        "--file", "-f", default=None,
        help="日志文件路径"
    )

    # logs grep
    grep_parser = logs_sub.add_parser(
        "grep", help="在日志中搜索关键词（支持正则）"
    )
    grep_parser.add_argument(
        "pattern", help="搜索模式（正则表达式）"
    )
    grep_parser.add_argument(
        "--file", "-f", default=None,
        help="日志文件路径"
    )
    grep_parser.add_argument(
        "--context", "-C", type=int, default=0,
        help="上下文行数（默认0）"
    )
    grep_parser.add_argument(
        "--ignore-case", "-i", action="store_true",
        help="忽略大小写"
    )


def handle_logs(args) -> int:
    """
    处理logs子命令分发。

    Args:
        args: 解析后的命令行参数。

    Returns:
        退出码。
    """
    action = getattr(args, "logs_action", None)

    if action is None or action == "show":
        # 无子动作时默认show
        if action is None:
            # 确保args有file和lines属性
            if not hasattr(args, "file"):
                args.file = None
            if not hasattr(args, "lines"):
                args.lines = 50
            if not hasattr(args, "level"):
                args.level = None
        return cmd_logs_show(args)
    elif action == "tail":
        return cmd_logs_tail(args)
    elif action == "analyze":
        return cmd_logs_analyze(args)
    elif action == "grep":
        return cmd_logs_grep(args)
    else:
        _print_error(f"Unknown logs action: {action}")
        return 1
