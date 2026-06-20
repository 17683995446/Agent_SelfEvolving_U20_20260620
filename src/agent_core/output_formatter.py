"""
输出格式化与无障碍工具。

第一性原理：
- 不同场景需要不同输出形式：人看text，机器看json，对比看table
- 无障碍：色盲/视障用户需要无颜色模式
- 输出级别：quiet适合脚本，verbose适合调试
- 统一格式化让所有命令输出一致

设计要点：
- OutputFormatter: 统一输出格式化器
  - format: text/json/table
  - color_enabled: 颜色开关
  - verbosity: quiet/normal/verbose
- format_table: 表格格式化
- format_kv: 键值对格式化
- format_list: 列表格式化
- 全局 --format, --no-color, --quiet, --verbose 参数
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Union

# 颜色
_COLOR_RESET = "\033[0m"
_COLOR_RED = "\033[31m"
_COLOR_GREEN = "\033[32m"
_COLOR_YELLOW = "\033[33m"
_COLOR_BLUE = "\033[34m"
_COLOR_CYAN = "\033[36m"
_COLOR_BOLD = "\033[1m"
_COLOR_DIM = "\033[2m"


class OutputFormatter:
    """
    统一输出格式化器。

    支持三种格式：text（默认）、json、table。
    支持颜色开关和输出级别控制。

    用法:
        fmt = OutputFormatter(format="text", color_enabled=True)
        fmt.print_kv({"name": "agent", "version": "1.0"})
        fmt.print_table([{"name": "a", "value": 1}], columns=["name", "value"])
        fmt.print_list(["item1", "item2"])
    """

    def __init__(
        self,
        format: str = "text",
        color_enabled: Optional[bool] = None,
        verbosity: str = "normal",
    ) -> None:
        """
        初始化格式化器。

        Args:
            format: 输出格式（text/json/table）。
            color_enabled: 是否启用颜色（None时自动检测TTY）。
            verbosity: 输出级别（quiet/normal/verbose）。
        """
        self._format = format
        self._verbosity = verbosity
        if color_enabled is not None:
            self._color_enabled = color_enabled
        else:
            self._color_enabled = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False

    @property
    def format(self) -> str:
        """当前格式。"""
        return self._format

    @property
    def color_enabled(self) -> bool:
        """颜色是否启用。"""
        return self._color_enabled

    @property
    def verbosity(self) -> str:
        """输出级别。"""
        return self._verbosity

    @property
    def is_quiet(self) -> bool:
        """是否静默模式。"""
        return self._verbosity == "quiet"

    @property
    def is_verbose(self) -> bool:
        """是否详细模式。"""
        return self._verbosity == "verbose"

    def colorize(self, text: str, color: str) -> str:
        """添加颜色。"""
        if not self._color_enabled:
            return text
        return f"{color}{text}{_COLOR_RESET}"

    def print(self, msg: str = "", end: str = "\n") -> None:
        """打印（quiet模式不输出）。"""
        if not self.is_quiet:
            print(msg, end=end)

    def print_info(self, msg: str) -> None:
        """打印信息。"""
        if self.is_quiet:
            return
        prefix = self.colorize("[INFO]", _COLOR_BLUE)
        print(f"{prefix} {msg}")

    def print_success(self, msg: str) -> None:
        """打印成功。"""
        if self.is_quiet:
            return
        prefix = self.colorize("[OK]", _COLOR_GREEN)
        print(f"{prefix} {msg}")

    def print_warning(self, msg: str) -> None:
        """打印警告。"""
        if self.is_quiet:
            return
        prefix = self.colorize("[WARN]", _COLOR_YELLOW)
        print(f"{prefix} {msg}")

    def print_error(self, msg: str) -> None:
        """打印错误（始终输出，即使quiet）。"""
        prefix = self.colorize("[ERROR]", _COLOR_RED)
        print(f"{prefix} {msg}", file=sys.stderr)

    def print_verbose(self, msg: str) -> None:
        """打印详细信息（仅verbose模式）。"""
        if not self.is_verbose:
            return
        prefix = self.colorize("[DEBUG]", _COLOR_DIM)
        print(f"{prefix} {msg}")

    def print_kv(
        self,
        data: Dict[str, Any],
        title: Optional[str] = None,
    ) -> None:
        """
        打印键值对。

        Args:
            data: 键值对数据。
            title: 可选标题。
        """
        if self.is_quiet:
            return

        if self._format == "json":
            output = data
            if title:
                output = {"title": title, "data": data}
            print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
            return

        if title:
            print(self.colorize(f"=== {title} ===", _COLOR_BOLD))
            print()

        max_key_len = max(len(str(k)) for k in data.keys()) if data else 0
        for key, value in data.items():
            key_str = str(key).ljust(max_key_len)
            print(f"  {self.colorize(key_str, _COLOR_CYAN)}: {value}")

    def print_table(
        self,
        rows: List[Dict[str, Any]],
        columns: Optional[List[str]] = None,
        title: Optional[str] = None,
    ) -> None:
        """
        打印表格。

        Args:
            rows: 行数据（字典列表）。
            columns: 列名（None时自动从第一行获取）。
            title: 可选标题。
        """
        if self.is_quiet:
            return

        if not rows:
            if title:
                print(self.colorize(f"=== {title} ===", _COLOR_BOLD))
            print("(empty)")
            return

        if self._format == "json":
            output = rows
            if title:
                output = {"title": title, "rows": rows}
            print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
            return

        if columns is None:
            columns = list(rows[0].keys())

        if title:
            print(self.colorize(f"=== {title} ===", _COLOR_BOLD))
            print()

        # 计算列宽
        col_widths: Dict[str, int] = {}
        for col in columns:
            max_width = len(str(col))
            for row in rows:
                val = str(row.get(col, ""))
                if len(val) > max_width:
                    max_width = len(val)
            col_widths[col] = max_width

        # 表头
        header = "  ".join(
            self.colorize(str(col).ljust(col_widths[col]), _COLOR_BOLD)
            for col in columns
        )
        print(header)
        print("  ".join("-" * col_widths[col] for col in columns))

        # 数据行
        for row in rows:
            line = "  ".join(
                str(row.get(col, "")).ljust(col_widths[col])
                for col in columns
            )
            print(line)

    def print_list(
        self,
        items: List[Any],
        title: Optional[str] = None,
        numbered: bool = False,
    ) -> None:
        """
        打印列表。

        Args:
            items: 列表项。
            title: 可选标题。
            numbered: 是否编号。
        """
        if self.is_quiet:
            return

        if self._format == "json":
            output = items
            if title:
                output = {"title": title, "items": items}
            print(json.dumps(output, indent=2, ensure_ascii=False, default=str))
            return

        if title:
            print(self.colorize(f"=== {title} ===", _COLOR_BOLD))
            print()

        if not items:
            print("(empty)")
            return

        for i, item in enumerate(items, 1):
            if numbered:
                print(f"  {self.colorize(str(i) + '.', _COLOR_CYAN)} {item}")
            else:
                print(f"  - {item}")

    def print_json(self, data: Any) -> None:
        """直接打印JSON。"""
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def create_formatter(args: argparse.Namespace) -> OutputFormatter:
    """
    从命令行参数创建格式化器。

    Args:
        args: 命令行参数（含format/no_color/quiet/verbose属性）。

    Returns:
        OutputFormatter实例。
    """
    fmt = getattr(args, "format", "text")
    no_color = getattr(args, "no_color", False)
    quiet = getattr(args, "quiet", False)
    verbose = getattr(args, "verbose", False)

    if quiet:
        verbosity = "quiet"
    elif verbose:
        verbosity = "verbose"
    else:
        verbosity = "normal"

    color_enabled = False if no_color else None

    return OutputFormatter(
        format=fmt,
        color_enabled=color_enabled,
        verbosity=verbosity,
    )


def add_global_format_args(parser: argparse.ArgumentParser) -> None:
    """
    添加全局格式化参数到parser。

    添加 --format, --no-color, --quiet, --verbose 参数。

    Args:
        parser: argparse解析器。
    """
    parser.add_argument(
        "--format",
        choices=["text", "json", "table"],
        default="text",
        help="输出格式（默认: text）",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="禁用颜色输出（无障碍模式）",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="静默模式（仅输出错误）",
    )
    parser.add_argument(
        "--verbose", "-V",
        action="store_true",
        help="详细模式（输出调试信息）",
    )


def format_table(
    rows: List[Dict[str, Any]],
    columns: Optional[List[str]] = None,
) -> str:
    """
    格式化表格为字符串。

    Args:
        rows: 行数据。
        columns: 列名。

    Returns:
        格式化的表格字符串。
    """
    if not rows:
        return "(empty)"

    if columns is None:
        columns = list(rows[0].keys())

    col_widths: Dict[str, int] = {}
    for col in columns:
        max_width = len(str(col))
        for row in rows:
            val = str(row.get(col, ""))
            if len(val) > max_width:
                max_width = len(val)
        col_widths[col] = max_width

    lines: List[str] = []
    header = "  ".join(str(col).ljust(col_widths[col]) for col in columns)
    lines.append(header)
    lines.append("  ".join("-" * col_widths[col] for col in columns))
    for row in rows:
        line = "  ".join(
            str(row.get(col, "")).ljust(col_widths[col])
            for col in columns
        )
        lines.append(line)

    return "\n".join(lines)


def format_kv(data: Dict[str, Any]) -> str:
    """
    格式化键值对为字符串。

    Args:
        data: 键值对数据。

    Returns:
        格式化的字符串。
    """
    if not data:
        return "(empty)"

    max_key_len = max(len(str(k)) for k in data.keys())
    lines: List[str] = []
    for key, value in data.items():
        key_str = str(key).ljust(max_key_len)
        lines.append(f"  {key_str}: {value}")
    return "\n".join(lines)
