"""
命令历史持久化与搜索。

第一性原理：
- 用户经常重复执行命令，历史应跨会话保留
- 历史搜索让用户快速找到之前用过的命令
- 历史记录是用户行为的镜像，帮助理解使用模式
- 持久化历史让CLI像Shell一样有记忆

设计要点：
- HistoryManager: 历史管理器，持久化到 .agent_history.json
- record: 记录命令（含时间戳、退出码）
- search: 按关键词/正则搜索历史
- stats: 历史统计（最常用命令、使用频率）
- history CLI: list/search/stats/clear
- 容量限制：默认保留最近1000条
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
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


# 历史文件名
_HISTORY_FILE = ".agent_history.json"

# 默认最大历史记录数
_DEFAULT_MAX_ENTRIES = 1000


class HistoryEntry:
    """历史记录条目。"""

    def __init__(
        self,
        command: str,
        timestamp: Optional[float] = None,
        exit_code: Optional[int] = None,
    ) -> None:
        """
        初始化历史条目。

        Args:
            command: 命令字符串。
            timestamp: 时间戳（None时使用当前时间）。
            exit_code: 退出码。
        """
        self.command = command
        self.timestamp = timestamp if timestamp is not None else time.time()
        self.exit_code = exit_code

    def to_dict(self) -> Dict[str, Any]:
        """转为字典。"""
        return {
            "command": self.command,
            "timestamp": self.timestamp,
            "exit_code": self.exit_code,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoryEntry":
        """从字典创建。"""
        return cls(
            command=data.get("command", ""),
            timestamp=data.get("timestamp"),
            exit_code=data.get("exit_code"),
        )

    def format_time(self) -> str:
        """格式化时间。"""
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.timestamp))


class HistoryManager:
    """
    命令历史管理器。

    持久化命令历史到文件，支持搜索和统计。
    """

    def __init__(
        self,
        project_dir: Optional[str] = None,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
    ) -> None:
        """
        初始化历史管理器。

        Args:
            project_dir: 项目目录（None时使用当前目录）。
            max_entries: 最大记录数。
        """
        self._project_dir = project_dir or os.getcwd()
        self._max_entries = max_entries
        self._entries: List[HistoryEntry] = []
        self._load()

    @property
    def history_file_path(self) -> str:
        """历史文件路径。"""
        return os.path.join(self._project_dir, _HISTORY_FILE)

    def _load(self) -> None:
        """从文件加载历史。"""
        path = self.history_file_path
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = [
                    HistoryEntry.from_dict(item)
                    for item in data.get("entries", [])
                ]
            except (json.JSONDecodeError, OSError, KeyError):
                self._entries = []

    def _save(self) -> bool:
        """保存历史到文件。"""
        path = self.history_file_path
        try:
            data = {
                "entries": [e.to_dict() for e in self._entries],
                "version": 1,
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except OSError:
            return False

    def record(
        self,
        command: str,
        exit_code: Optional[int] = None,
    ) -> None:
        """
        记录命令到历史。

        Args:
            command: 命令字符串。
            exit_code: 退出码。
        """
        if not command or not command.strip():
            return

        # 不记录history命令自身（避免污染）
        parts = command.strip().split()
        if parts and parts[0] in ("history", "exit", "quit"):
            return

        entry = HistoryEntry(command=command.strip(), exit_code=exit_code)
        self._entries.append(entry)

        # 容量限制：保留最近的记录
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        self._save()

    def get_all(self) -> List[HistoryEntry]:
        """获取所有历史记录。"""
        return list(self._entries)

    def get_recent(self, count: int = 20) -> List[HistoryEntry]:
        """
        获取最近的记录。

        Args:
            count: 返回条数。

        Returns:
            最近的记录列表。
        """
        return self._entries[-count:] if count > 0 else []

    def search(
        self,
        pattern: str,
        use_regex: bool = False,
        ignore_case: bool = False,
    ) -> List[HistoryEntry]:
        """
        搜索历史记录。

        Args:
            pattern: 搜索模式（关键词或正则）。
            use_regex: 是否使用正则表达式。
            ignore_case: 是否忽略大小写。

        Returns:
            匹配的记录列表。
        """
        results: List[HistoryEntry] = []

        if use_regex:
            flags = re.IGNORECASE if ignore_case else 0
            try:
                regex = re.compile(pattern, flags)
            except re.error:
                return results
            for entry in self._entries:
                if regex.search(entry.command):
                    results.append(entry)
        else:
            search_in = pattern.lower() if ignore_case else pattern
            for entry in self._entries:
                cmd = entry.command.lower() if ignore_case else entry.command
                if search_in in cmd:
                    results.append(entry)

        return results

    def stats(self) -> Dict[str, Any]:
        """
        获取历史统计。

        Returns:
            统计信息字典。
        """
        if not self._entries:
            return {
                "total": 0,
                "unique_commands": 0,
                "top_commands": [],
                "time_range": None,
            }

        # 命令频率统计（取命令的第一个词）
        cmd_counter: Counter = Counter()
        for entry in self._entries:
            parts = entry.command.split()
            if parts:
                cmd_counter[parts[0]] += 1

        top_commands = [
            {"command": cmd, "count": count}
            for cmd, count in cmd_counter.most_common(10)
        ]

        timestamps = [e.timestamp for e in self._entries]
        time_range = {
            "first": min(timestamps),
            "last": max(timestamps),
        }

        return {
            "total": len(self._entries),
            "unique_commands": len(cmd_counter),
            "top_commands": top_commands,
            "time_range": time_range,
        }

    def clear(self) -> bool:
        """清除所有历史。"""
        self._entries = []
        return self._save()

    def count(self) -> int:
        """记录数。"""
        return len(self._entries)


def cmd_history_list(args: argparse.Namespace) -> int:
    """列出历史记录。"""
    manager = HistoryManager()
    count = getattr(args, "limit", 20)
    entries = manager.get_recent(count)

    if not entries:
        print(_c("No command history.", _COLOR_DIM))
        return 0

    print(_c("=== Command History ===", _COLOR_BOLD))
    print()
    for i, entry in enumerate(entries, 1):
        time_str = entry.format_time()
        exit_str = ""
        if entry.exit_code is not None:
            if entry.exit_code == 0:
                exit_str = _c(" [OK]", _COLOR_GREEN)
            else:
                exit_str = _c(f" [exit:{entry.exit_code}]", _COLOR_RED)
        print(f"  {i:4d}  {_c(time_str, _COLOR_DIM)}  {entry.command}{exit_str}")

    print()
    print(_c(f"Total: {manager.count()} entries (showing last {len(entries)})",
             _COLOR_DIM))
    return 0


def cmd_history_search(args: argparse.Namespace) -> int:
    """搜索历史记录。"""
    manager = HistoryManager()
    pattern = args.pattern
    use_regex = getattr(args, "regex", False)
    ignore_case = not getattr(args, "case_sensitive", False)

    results = manager.search(pattern, use_regex=use_regex, ignore_case=ignore_case)

    if not results:
        print(_c(f"No matches for: {pattern}", _COLOR_DIM))
        return 0

    print(_c(f"=== Search Results ({len(results)} matches) ===", _COLOR_BOLD))
    print()
    for i, entry in enumerate(results, 1):
        time_str = entry.format_time()
        # 高亮匹配部分
        cmd = entry.command
        if not use_regex and not ignore_case:
            cmd = cmd.replace(pattern, _c(pattern, _COLOR_YELLOW))
        elif not use_regex and ignore_case:
            # 简单高亮（忽略大小写）
            lower_cmd = cmd.lower()
            lower_pattern = pattern.lower()
            idx = lower_cmd.find(lower_pattern)
            if idx >= 0:
                cmd = (cmd[:idx] + _c(cmd[idx:idx+len(pattern)], _COLOR_YELLOW)
                       + cmd[idx+len(pattern):])
        print(f"  {i:4d}  {_c(time_str, _COLOR_DIM)}  {cmd}")

    return 0


def cmd_history_stats(args: argparse.Namespace) -> int:
    """显示历史统计。"""
    manager = HistoryManager()
    stats = manager.stats()

    print(_c("=== History Statistics ===", _COLOR_BOLD))
    print()
    print(f"  Total entries:      {stats['total']}")
    print(f"  Unique commands:    {stats['unique_commands']}")

    time_range = stats.get("time_range")
    if time_range:
        first = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time_range["first"]))
        last = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time_range["last"]))
        print(f"  First command:      {first}")
        print(f"  Last command:       {last}")

    top = stats.get("top_commands", [])
    if top:
        print()
        print(_c("  Top Commands:", _COLOR_CYAN))
        for item in top[:10]:
            print(f"    {item['command']:<20} {item['count']} times")

    return 0


def cmd_history_clear(args: argparse.Namespace) -> int:
    """清除历史。"""
    manager = HistoryManager()
    if manager.clear():
        print(_c("[OK] History cleared.", _COLOR_GREEN))
        return 0
    else:
        print(_c("[ERROR] Failed to clear history.", _COLOR_RED))
        return 1


def handle_history(args: argparse.Namespace) -> int:
    """
    处理history命令。

    Args:
        args: 命令行参数。

    Returns:
        退出码。
    """
    action = getattr(args, "history_action", None)

    if action is None or action == "list":
        return cmd_history_list(args)
    elif action == "search":
        return cmd_history_search(args)
    elif action == "stats":
        return cmd_history_stats(args)
    elif action == "clear":
        return cmd_history_clear(args)
    else:
        print(_c(f"[ERROR] Unknown history action: {action}", _COLOR_RED))
        return 1


def add_history_subparser(subparsers: argparse._SubParsersAction) -> None:
    """
    注册history子命令。

    Args:
        subparsers: argparse子命令解析器。
    """
    history_parser = subparsers.add_parser(
        "history",
        help="命令历史管理（list/search/stats/clear）",
        description="管理命令历史，支持持久化和搜索。",
    )
    history_sub = history_parser.add_subparsers(dest="history_action")

    # history list（默认）
    list_parser = history_sub.add_parser("list", help="列出最近历史")
    list_parser.add_argument(
        "--limit", "-n",
        type=int,
        default=20,
        help="返回条数（默认: 20）",
    )

    # history search
    search_parser = history_sub.add_parser("search", help="搜索历史")
    search_parser.add_argument("pattern", help="搜索模式")
    search_parser.add_argument(
        "--regex", "-r",
        action="store_true",
        help="使用正则表达式",
    )
    search_parser.add_argument(
        "--case-sensitive", "-s",
        action="store_true",
        help="区分大小写",
    )

    # history stats
    history_sub.add_parser("stats", help="显示历史统计")

    # history clear
    history_sub.add_parser("clear", help="清除所有历史")
