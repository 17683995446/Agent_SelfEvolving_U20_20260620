"""
命令别名与快捷操作。

第一性原理：
- 高频操作应有最短路径，减少击键次数
- 别名是肌肉记忆的延伸，让常用命令更顺手
- 用户自定义别名让系统适应个人习惯
- 别名解析应在命令分发前执行，对后续逻辑透明

设计要点：
- BUILTIN_ALIASES: 内置常用别名（只读）
- AliasManager: 别名管理器，支持加载/保存用户自定义别名
- resolve_alias: 将别名解析为完整命令
- alias CLI: list/add/remove/clear
- 别名存储在 .agent_aliases.json（项目级）
"""

import argparse
import json
import os
import sys
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


# 内置别名（只读，不可删除）
BUILTIN_ALIASES: Dict[str, str] = {
    # 生命周期快捷
    "s": "start",
    "st": "status",
    "h": "health",
    "v": "version",
    # 日志快捷
    "lg": "logs",
    "lr": "log-rotate",
    # 配置快捷
    "cfg": "config",
    "wiz": "wizard",
    # 数据快捷
    "d": "data",
    # 帮助快捷
    "?": "help",
}

# 别名存储文件名
_ALIAS_FILE = ".agent_aliases.json"


class AliasManager:
    """
    别名管理器。

    管理内置别名和用户自定义别名。
    用户别名存储在项目级 .agent_aliases.json 文件中。
    """

    def __init__(self, project_dir: Optional[str] = None) -> None:
        """
        初始化别名管理器。

        Args:
            project_dir: 项目目录（None时使用当前目录）。
        """
        self._project_dir = project_dir or os.getcwd()
        self._user_aliases: Dict[str, str] = {}
        self._load()

    @property
    def alias_file_path(self) -> str:
        """别名文件路径。"""
        return os.path.join(self._project_dir, _ALIAS_FILE)

    def _load(self) -> None:
        """从文件加载用户别名。"""
        path = self.alias_file_path
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._user_aliases = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._user_aliases = {}

    def _save(self) -> bool:
        """保存用户别名到文件。"""
        path = self.alias_file_path
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._user_aliases, f, indent=2, ensure_ascii=False)
            return True
        except OSError:
            return False

    def get_all(self) -> Dict[str, str]:
        """获取所有别名（内置+用户）。"""
        merged = dict(BUILTIN_ALIASES)
        merged.update(self._user_aliases)
        return merged

    def get_builtin(self) -> Dict[str, str]:
        """获取内置别名。"""
        return dict(BUILTIN_ALIASES)

    def get_user(self) -> Dict[str, str]:
        """获取用户别名。"""
        return dict(self._user_aliases)

    def add(self, alias: str, command: str) -> bool:
        """
        添加用户别名。

        Args:
            alias: 别名。
            command: 目标命令。

        Returns:
            是否成功添加。
        """
        if not alias or not command:
            return False
        # 不允许覆盖内置别名
        if alias in BUILTIN_ALIASES:
            return False
        self._user_aliases[alias] = command
        return self._save()

    def remove(self, alias: str) -> bool:
        """
        删除用户别名。

        Args:
            alias: 要删除的别名。

        Returns:
            是否成功删除。
        """
        if alias in BUILTIN_ALIASES:
            return False
        if alias not in self._user_aliases:
            return False
        del self._user_aliases[alias]
        return self._save()

    def clear(self) -> bool:
        """清除所有用户别名。"""
        self._user_aliases = {}
        return self._save()

    def is_builtin(self, alias: str) -> bool:
        """是否是内置别名。"""
        return alias in BUILTIN_ALIASES

    def resolve(self, alias: str) -> Optional[str]:
        """
        解析别名为目标命令。

        支持链式解析（A→B→C），防止循环引用。

        Args:
            alias: 别名。

        Returns:
            目标命令，未找到返回None。
        """
        all_aliases = self.get_all()
        visited = set()
        current = alias

        while current in all_aliases:
            if current in visited:
                # 循环引用
                return None
            visited.add(current)
            current = all_aliases[current]

        return current if current != alias else None


def resolve_alias(
    alias: str,
    manager: Optional[AliasManager] = None,
) -> str:
    """
    解析别名为完整命令。

    便捷函数：如果别名存在则返回目标命令，否则返回原值。

    Args:
        alias: 可能是别名的字符串。
        manager: 别名管理器（None时创建默认）。

    Returns:
        解析后的命令（或原值）。
    """
    if manager is None:
        manager = AliasManager()
    resolved = manager.resolve(alias)
    return resolved if resolved else alias


def resolve_command_args(
    argv: List[str],
    manager: Optional[AliasManager] = None,
) -> List[str]:
    """
    解析命令行参数中的别名。

    仅替换第一个token（命令名），保留其余参数。

    Args:
        argv: 原始命令行参数。
        manager: 别名管理器。

    Returns:
        解析后的命令行参数。
    """
    if not argv:
        return argv
    if manager is None:
        manager = AliasManager()
    resolved = manager.resolve(argv[0])
    if resolved:
        return [resolved] + argv[1:]
    return argv


def cmd_alias_list(args: argparse.Namespace) -> int:
    """列出所有别名。"""
    manager = AliasManager()
    all_aliases = manager.get_all()

    print(_c("=== Command Aliases ===", _COLOR_BOLD))
    print()

    # 内置别名
    print(_c("Built-in:", _COLOR_CYAN))
    for alias, cmd in sorted(BUILTIN_ALIASES.items()):
        print(f"  {_c(alias, _COLOR_GREEN):<10} → {cmd}")
    print()

    # 用户别名
    user_aliases = manager.get_user()
    if user_aliases:
        print(_c("User-defined:", _COLOR_CYAN))
        for alias, cmd in sorted(user_aliases.items()):
            print(f"  {_c(alias, _COLOR_GREEN):<10} → {cmd}")
    else:
        print(_c("User-defined: (none)", _COLOR_DIM))
    print()
    print(_c("Tip: Use 'agent alias add <name> <command>' to add custom aliases.", _COLOR_DIM))

    return 0


def cmd_alias_add(args: argparse.Namespace) -> int:
    """添加用户别名。"""
    manager = AliasManager()

    alias = args.name
    command = args.target

    if manager.is_builtin(alias):
        print(_c(f"[ERROR] Cannot override built-in alias: {alias}", _COLOR_RED))
        return 1

    if manager.add(alias, command):
        print(_c(f"[OK] Alias added: {alias} → {command}", _COLOR_GREEN))
        return 0
    else:
        print(_c(f"[ERROR] Failed to add alias", _COLOR_RED))
        return 1


def cmd_alias_remove(args: argparse.Namespace) -> int:
    """删除用户别名。"""
    manager = AliasManager()
    alias = args.name

    if manager.is_builtin(alias):
        print(_c(f"[ERROR] Cannot remove built-in alias: {alias}", _COLOR_RED))
        return 1

    if manager.remove(alias):
        print(_c(f"[OK] Alias removed: {alias}", _COLOR_GREEN))
        return 0
    else:
        print(_c(f"[ERROR] Alias not found: {alias}", _COLOR_RED))
        return 1


def cmd_alias_clear(args: argparse.Namespace) -> int:
    """清除所有用户别名。"""
    manager = AliasManager()
    if manager.clear():
        print(_c("[OK] All user aliases cleared.", _COLOR_GREEN))
        return 0
    else:
        print(_c("[ERROR] Failed to clear aliases", _COLOR_RED))
        return 1


def handle_alias(args: argparse.Namespace) -> int:
    """
    处理alias命令。

    Args:
        args: 命令行参数。

    Returns:
        退出码。
    """
    action = getattr(args, "alias_action", None)

    if action is None or action == "list":
        return cmd_alias_list(args)
    elif action == "add":
        return cmd_alias_add(args)
    elif action == "remove":
        return cmd_alias_remove(args)
    elif action == "clear":
        return cmd_alias_clear(args)
    else:
        print(_c(f"[ERROR] Unknown alias action: {action}", _COLOR_RED))
        return 1


def add_alias_subparser(subparsers: argparse._SubParsersAction) -> None:
    """
    注册alias子命令。

    Args:
        subparsers: argparse子命令解析器。
    """
    alias_parser = subparsers.add_parser(
        "alias",
        help="命令别名管理（list/add/remove/clear）",
        description="管理命令别名，支持内置和用户自定义别名。",
    )
    alias_sub = alias_parser.add_subparsers(dest="alias_action")

    # alias list（默认）
    alias_sub.add_parser("list", help="列出所有别名")

    # alias add
    add_parser = alias_sub.add_parser("add", help="添加用户别名")
    add_parser.add_argument("name", help="别名名称")
    add_parser.add_argument("target", help="目标命令")

    # alias remove
    remove_parser = alias_sub.add_parser("remove", help="删除用户别名")
    remove_parser.add_argument("name", help="要删除的别名")

    # alias clear
    alias_sub.add_parser("clear", help="清除所有用户别名")
