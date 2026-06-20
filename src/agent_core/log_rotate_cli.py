"""
日志轮转CLI模块。

将LogRotator的日志轮转能力暴露到CLI，用户可以：
- 查看日志文件状态（大小、是否需要轮转、归档列表）
- 手动触发日志轮转
- 列出已有归档文件

第一性原理：
- 日志无限增长会耗尽磁盘，轮转是必要的管理手段
- 轮转能力已存在于LogRotator，只需暴露入口
- 用户需要便捷工具查看轮转状态和手动触发轮转
"""

import os
import sys
from typing import Any, Dict, List, Optional

from agent_core.common.logger import get_logger

# 默认日志文件搜索路径（与logs_cli一致）
_DEFAULT_LOG_PATHS = [
    "logs/agent.log",
    "agent.log",
    "logs/self_evolving_agent.log",
    "self_evolving_agent.log",
]

# 默认轮转参数
_DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10MB
_DEFAULT_BACKUP_COUNT = 5

# 颜色
_COLOR_RESET = "\033[0m"
_COLOR_RED = "\033[31m"
_COLOR_GREEN = "\033[32m"
_COLOR_YELLOW = "\033[33m"
_COLOR_CYAN = "\033[36m"
_COLOR_BOLD = "\033[1m"
_COLOR_BLUE = "\033[34m"
_COLOR_MAGENTA = "\033[35m"

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


def _print_warning(msg: str) -> None:
    """打印警告信息。"""
    print(f"{_colorize('[WARN]', _COLOR_YELLOW)} {msg}")


def _format_size(size_bytes: int) -> str:
    """
    格式化文件大小为人类可读形式。

    Args:
        size_bytes: 字节数。

    Returns:
        格式化后的大小字符串。
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def _resolve_log_path(file_arg: Optional[str]) -> Optional[str]:
    """
    解析日志文件路径。

    优先级：--file参数 > 默认搜索路径 > None
    """
    if file_arg:
        if os.path.exists(file_arg):
            return file_arg
        _print_error(f"Log file not found: {file_arg}")
        return None

    for candidate in _DEFAULT_LOG_PATHS:
        if os.path.exists(candidate):
            return candidate

    _print_error(
        "No log file found. Specify with --file <path>. "
        f"Searched: {', '.join(_DEFAULT_LOG_PATHS)}"
    )
    return None


def cmd_log_rotate_status(args) -> int:
    """
    查看日志文件轮转状态。

    显示当前日志文件大小、是否需要轮转、归档列表。
    """
    from agent_core.common.log_rotator import LogRotator

    log_path = _resolve_log_path(getattr(args, "file", None))
    if log_path is None:
        return 1

    max_bytes = getattr(args, "max_bytes", _DEFAULT_MAX_BYTES)
    backup_count = getattr(args, "backup_count", _DEFAULT_BACKUP_COUNT)

    rotator = LogRotator(
        log_path=log_path,
        max_bytes=max_bytes,
        backup_count=backup_count,
    )

    print(_colorize("=== Log Rotation Status ===", _COLOR_BOLD))
    print(f"  Log File:       {log_path}")

    # 文件大小
    if os.path.isfile(log_path):
        size = os.path.getsize(log_path)
        print(f"  Current Size:   {_format_size(size)}")
        print(f"  Max Size:       {_format_size(max_bytes)}")
        print(f"  Backup Count:   {backup_count}")

        # 是否需要轮转
        needs_rotate = rotator.should_rotate()
        if needs_rotate:
            print(f"  Needs Rotate:   {_colorize('YES', _COLOR_RED)}")
        else:
            remaining = max_bytes - size
            print(f"  Needs Rotate:   {_colorize('NO', _COLOR_GREEN)}")
            print(f"  Until Rotate:   {_format_size(remaining)}")
    else:
        print(f"  Current Size:   {_colorize('file not found', _COLOR_RED)}")

    # 归档列表
    archives = rotator.get_archive_list()
    print()
    print(_colorize(f"--- Archives ({len(archives)}) ---", _COLOR_CYAN))
    if archives:
        for archive in archives:
            arch_size = os.path.getsize(archive) if os.path.exists(archive) else 0
            print(f"  {os.path.basename(archive)}  ({_format_size(arch_size)})")
    else:
        print(f"  {_colorize('No archives', _COLOR_YELLOW)}")

    return 0


def cmd_log_rotate_rotate(args) -> int:
    """
    手动触发日志轮转。

    将当前日志文件归档压缩，并创建新的空日志文件。
    """
    from agent_core.common.log_rotator import LogRotator

    log_path = _resolve_log_path(getattr(args, "file", None))
    if log_path is None:
        return 1

    max_bytes = getattr(args, "max_bytes", _DEFAULT_MAX_BYTES)
    backup_count = getattr(args, "backup_count", _DEFAULT_BACKUP_COUNT)
    force = getattr(args, "force", False)

    rotator = LogRotator(
        log_path=log_path,
        max_bytes=max_bytes,
        backup_count=backup_count,
    )

    # 检查是否需要轮转
    needs_rotate = rotator.should_rotate()
    if not needs_rotate and not force:
        size = os.path.getsize(log_path) if os.path.exists(log_path) else 0
        _print_info(
            f"Log file is {size} bytes, below threshold "
            f"({_format_size(max_bytes)}). No rotation needed."
        )
        _print_info("Use --force to rotate anyway.")
        return 0

    _print_info(f"Rotating {log_path}...")

    if needs_rotate:
        # 正常轮转
        success = rotator.rotate()
    else:
        # 强制轮转：直接调用内部方法
        try:
            rotator._do_rotation()
            success = True
        except OSError as exc:
            _print_error(f"Rotation failed: {exc}")
            success = False

    if success:
        _print_success("Log rotated successfully")
        # 显示归档列表
        archives = rotator.get_archive_list()
        if archives:
            print(_colorize("--- Archives ---", _COLOR_CYAN))
            for archive in archives:
                arch_size = os.path.getsize(archive) if os.path.exists(archive) else 0
                print(f"  {os.path.basename(archive)}  ({_format_size(arch_size)})")
        return 0
    else:
        _print_error("Log rotation failed")
        return 1


def cmd_log_rotate_archives(args) -> int:
    """
    列出所有归档文件。

    显示归档文件名、大小和修改时间。
    """
    from agent_core.common.log_rotator import LogRotator

    log_path = _resolve_log_path(getattr(args, "file", None))
    if log_path is None:
        return 1

    backup_count = getattr(args, "backup_count", _DEFAULT_BACKUP_COUNT)

    rotator = LogRotator(
        log_path=log_path,
        backup_count=backup_count,
    )

    archives = rotator.get_archive_list()

    print(_colorize("=== Log Archives ===", _COLOR_BOLD))
    print(f"  Log File: {log_path}")
    print()

    if not archives:
        print(_colorize("No archive files found.", _COLOR_YELLOW))
        return 0

    print(f"{'Archive':<30} {'Size':>10}  Modified")
    print("-" * 60)

    total_size = 0
    for archive in archives:
        size = os.path.getsize(archive) if os.path.exists(archive) else 0
        total_size += size
        mtime = os.path.getmtime(archive) if os.path.exists(archive) else 0

        import time
        mtime_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))

        print(f"{os.path.basename(archive):<30} {_format_size(size):>10}  {mtime_str}")

    print("-" * 60)
    print(f"{'Total':<30} {_format_size(total_size):>10}")
    print(f"\n  Archives: {len(archives)}")
    print(f"  Total Size: {_format_size(total_size)}")

    return 0


def add_log_rotate_subparser(subparsers) -> None:
    """
    注册log-rotate子命令组到CLI解析器。

    Args:
        subparsers: argparse子命令解析器组。
    """
    rotate_parser = subparsers.add_parser(
        "log-rotate",
        help="日志轮转管理（状态/轮转/归档）",
        description="日志轮转管理工具：查看状态、手动轮转、列出归档",
    )
    rotate_sub = rotate_parser.add_subparsers(dest="rotate_action")

    # log-rotate status
    status_parser = rotate_sub.add_parser(
        "status", help="查看日志轮转状态（默认动作）"
    )
    status_parser.add_argument(
        "--file", "-f", default=None,
        help="日志文件路径（默认自动搜索）"
    )
    status_parser.add_argument(
        "--max-bytes", type=int, default=_DEFAULT_MAX_BYTES,
        help=f"最大字节数（默认: {_DEFAULT_MAX_BYTES}）"
    )
    status_parser.add_argument(
        "--backup-count", type=int, default=_DEFAULT_BACKUP_COUNT,
        help=f"备份数量（默认: {_DEFAULT_BACKUP_COUNT}）"
    )

    # log-rotate rotate
    do_rotate_parser = rotate_sub.add_parser(
        "rotate", help="手动触发日志轮转"
    )
    do_rotate_parser.add_argument(
        "--file", "-f", default=None,
        help="日志文件路径"
    )
    do_rotate_parser.add_argument(
        "--max-bytes", type=int, default=_DEFAULT_MAX_BYTES,
        help=f"最大字节数（默认: {_DEFAULT_MAX_BYTES}）"
    )
    do_rotate_parser.add_argument(
        "--backup-count", type=int, default=_DEFAULT_BACKUP_COUNT,
        help=f"备份数量（默认: {_DEFAULT_BACKUP_COUNT}）"
    )
    do_rotate_parser.add_argument(
        "--force", action="store_true",
        help="强制轮转（即使未超过阈值）"
    )

    # log-rotate archives
    archives_parser = rotate_sub.add_parser(
        "archives", help="列出归档文件"
    )
    archives_parser.add_argument(
        "--file", "-f", default=None,
        help="日志文件路径"
    )
    archives_parser.add_argument(
        "--backup-count", type=int, default=_DEFAULT_BACKUP_COUNT,
        help=f"备份数量（默认: {_DEFAULT_BACKUP_COUNT}）"
    )


def handle_log_rotate(args) -> int:
    """
    处理log-rotate子命令分发。

    Args:
        args: 解析后的命令行参数。

    Returns:
        退出码。
    """
    action = getattr(args, "rotate_action", None)

    if action is None or action == "status":
        # 无子动作时默认status
        if not hasattr(args, "file"):
            args.file = None
        if not hasattr(args, "max_bytes"):
            args.max_bytes = _DEFAULT_MAX_BYTES
        if not hasattr(args, "backup_count"):
            args.backup_count = _DEFAULT_BACKUP_COUNT
        return cmd_log_rotate_status(args)
    elif action == "rotate":
        return cmd_log_rotate_rotate(args)
    elif action == "archives":
        return cmd_log_rotate_archives(args)
    else:
        _print_error(f"Unknown log-rotate action: {action}")
        return 1
