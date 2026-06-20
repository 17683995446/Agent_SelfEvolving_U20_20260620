"""
配置管理CLI模块。

提供配置diff、验证和dry-run能力：
- config diff: 比较两个配置文件的差异
- config show: 显示当前生效配置
- config validate: 验证配置文件

第一性原理：
- 配置变更是高风险操作，用户需要预览差异和验证
- 配置能力已存在于ConfigValidator/EnvironmentConfig，只需暴露入口
- dry-run让用户在启动前确认配置正确，避免运行时失败
"""

import copy
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

from agent_core.common.logger import get_logger

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


def _load_yaml_file(path: str) -> Dict[str, Any]:
    """
    加载YAML配置文件。

    Args:
        path: 文件路径。

    Returns:
        配置字典，失败时返回空字典。
    """
    if not os.path.isfile(path):
        _print_error(f"Config file not found: {path}")
        return {}

    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        _print_error("PyYAML not installed. Install with: pip install pyyaml")
        return {}
    except (yaml.YAMLError if 'yaml' in dir() else Exception) as exc:
        _print_error(f"Failed to parse YAML: {exc}")
        return {}
    except OSError as exc:
        _print_error(f"Failed to read file: {exc}")
        return {}


def _flatten_config(
    config: Dict[str, Any], prefix: str = ""
) -> Dict[str, Any]:
    """
    将嵌套配置字典展平为点号分隔的键值对。

    Args:
        config: 配置字典。
        prefix: 键前缀。

    Returns:
        展平后的字典 {key: value}。
    """
    result = {}
    for key, value in config.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(_flatten_config(value, full_key))
        else:
            result[full_key] = value
    return result


def _compute_diff(
    config_a: Dict[str, Any], config_b: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[Tuple[Any, Any], str]]:
    """
    计算两个配置字典的差异。

    Args:
        config_a: 配置A。
        config_b: 配置B。

    Returns:
        (added, removed, changed) 元组：
        - added: B中有但A中没有的键
        - removed: A中有但B中没有的键
        - changed: 值不同的键 {key: (old_value, new_value)}
    """
    flat_a = _flatten_config(config_a)
    flat_b = _flatten_config(config_b)

    added = {}
    removed = {}
    changed = {}

    for key, value in flat_b.items():
        if key not in flat_a:
            added[key] = value
        elif flat_a[key] != value:
            changed[key] = (flat_a[key], value)

    for key, value in flat_a.items():
        if key not in flat_b:
            removed[key] = value

    return added, removed, changed


def cmd_config_diff(args) -> int:
    """
    比较两个配置文件的差异。

    显示新增、删除和修改的配置项。
    """
    file_a = getattr(args, "file_a", None)
    file_b = getattr(args, "file_b", None)

    if not file_a or not file_b:
        _print_error("Two config files are required: --file-a <path> --file-b <path>")
        return 1

    config_a = _load_yaml_file(file_a)
    config_b = _load_yaml_file(file_b)

    if not config_a and not config_b:
        return 1

    added, removed, changed = _compute_diff(config_a, config_b)

    print(_colorize("=== Configuration Diff ===", _COLOR_BOLD))
    print(f"  File A: {file_a}")
    print(f"  File B: {file_b}")
    print()

    has_diff = bool(added or removed or changed)

    # 新增项
    if added:
        print(_colorize(f"--- Added ({len(added)}) ---", _COLOR_GREEN))
        for key in sorted(added.keys()):
            print(f"  {_colorize('+', _COLOR_GREEN)} {key}: {added[key]}")
        print()

    # 删除项
    if removed:
        print(_colorize(f"--- Removed ({len(removed)}) ---", _COLOR_RED))
        for key in sorted(removed.keys()):
            print(f"  {_colorize('-', _COLOR_RED)} {key}: {removed[key]}")
        print()

    # 修改项
    if changed:
        print(_colorize(f"--- Changed ({len(changed)}) ---", _COLOR_YELLOW))
        for key in sorted(changed.keys()):
            old_val, new_val = changed[key]
            print(f"  {_colorize('~', _COLOR_YELLOW)} {key}:")
            print(f"      {_colorize(f'- {old_val}', _COLOR_RED)}")
            print(f"      {_colorize(f'+ {new_val}', _COLOR_GREEN)}")
        print()

    if not has_diff:
        print(_colorize("No differences found. Configurations are identical.",
                        _COLOR_GREEN))
    else:
        total = len(added) + len(removed) + len(changed)
        print(_colorize(f"Total: {total} differences", _COLOR_BOLD))

    return 0


def cmd_config_show(args) -> int:
    """
    显示当前生效配置。

    加载base + env配置，显示合并后的最终配置。
    """
    from agent_core.cli import _load_config, _DEFAULT_ENV

    env = getattr(args, "env", _DEFAULT_ENV)
    config_path = getattr(args, "config", None)

    # 静默加载配置
    with patch_print():
        config = _load_config(env, config_path)

    if not config:
        _print_error("Failed to load configuration")
        return 1

    print(_colorize("=== Effective Configuration ===", _COLOR_BOLD))
    print(f"  Environment: {env}")
    if config_path:
        print(f"  Config File: {config_path}")
    print()

    flat = _flatten_config(config)
    for key in sorted(flat.keys()):
        value = flat[key]
        print(f"  {key}: {value}")

    print()
    print(f"  Total: {len(flat)} configuration items")

    return 0


def cmd_config_validate(args) -> int:
    """
    验证配置文件。

    检查配置项的类型、范围和依赖约束。
    """
    from agent_core.cli import _load_config, _DEFAULT_ENV
    from agent_core.common.config_validator import ConfigValidator

    env = getattr(args, "env", _DEFAULT_ENV)
    config_path = getattr(args, "config", None)

    # 静默加载配置
    with patch_print():
        config = _load_config(env, config_path)

    if not config:
        _print_error("Failed to load configuration")
        return 1

    validator = ConfigValidator()
    ok, errors = validator.validate(config)

    print(_colorize("=== Configuration Validation ===", _COLOR_BOLD))
    print(f"  Environment: {env}")
    if config_path:
        print(f"  Config File: {config_path}")
    print()

    if ok:
        _print_success("Configuration is valid")
        print(f"  Validated: {len(config)} configuration items")
        return 0
    else:
        _print_error(f"Configuration validation failed ({len(errors)} errors)")
        for err in errors:
            print(f"  {_colorize('•', _COLOR_RED)} {err}")
        return 1


class patch_print:
    """临时抑制cli模块的_print_info/_print_warning/_print_error输出。"""

    def __enter__(self):
        self._patches = []
        import agent_core.cli as _cli_mod
        for func_name in ["_print_info", "_print_warning", "_print_error", "_print_success"]:
            p = patch.object(_cli_mod, func_name, lambda *a, **kw: None)
            self._patches.append(p)
            p.start()
        return self

    def __exit__(self, *args):
        for p in self._patches:
            p.stop()


def add_config_subparser(subparsers) -> None:
    """
    注册config子命令组到CLI解析器。

    Args:
        subparsers: argparse子命令解析器组。
    """
    config_parser = subparsers.add_parser(
        "config",
        help="配置管理（diff/show/validate）",
        description="配置管理工具：比较差异、查看生效配置、验证配置",
    )
    config_sub = config_parser.add_subparsers(dest="config_action")

    # config diff
    diff_parser = config_sub.add_parser(
        "diff", help="比较两个配置文件的差异"
    )
    diff_parser.add_argument(
        "--file-a", "-a", required=True,
        help="配置文件A（基准）"
    )
    diff_parser.add_argument(
        "--file-b", "-b", required=True,
        help="配置文件B（对比）"
    )

    # config show
    show_parser = config_sub.add_parser(
        "show", help="显示当前生效配置"
    )
    show_parser.add_argument(
        "--env", default="dev",
        help="环境 (dev/prod/test, 默认: dev)"
    )
    show_parser.add_argument(
        "--config", default=None,
        help="配置文件路径（覆盖--env）"
    )

    # config validate
    validate_parser = config_sub.add_parser(
        "validate", help="验证配置文件"
    )
    validate_parser.add_argument(
        "--env", default="dev",
        help="环境 (dev/prod/test, 默认: dev)"
    )
    validate_parser.add_argument(
        "--config", default=None,
        help="配置文件路径（覆盖--env）"
    )


def handle_config(args) -> int:
    """
    处理config子命令分发。

    Args:
        args: 解析后的命令行参数。

    Returns:
        退出码。
    """
    action = getattr(args, "config_action", None)

    if action is None:
        # 无子动作时显示帮助
        _print_info("Use 'agent config diff/show/validate' to manage configuration")
        return 0
    elif action == "diff":
        return cmd_config_diff(args)
    elif action == "show":
        return cmd_config_show(args)
    elif action == "validate":
        return cmd_config_validate(args)
    else:
        _print_error(f"Unknown config action: {action}")
        return 1
