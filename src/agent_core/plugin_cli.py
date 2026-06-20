"""
插件管理CLI模块。

将PluginManager/PluginRegistry的插件管理能力暴露到CLI，用户可以：
- 列出目录中的可用插件
- 加载并验证插件（初始化→健康检查→关闭）
- 查看插件元信息
- 对插件执行健康检查

第一性原理：
- 插件是系统的"可扩展肢体"，用户需要便捷工具验证和管理
- 管理能力已存在于PluginManager/PluginRegistry，只需暴露入口
- 独立验证模式：加载→检查→关闭，无需运行Agent即可测试插件
"""

import asyncio
import importlib.util
import inspect
import json
import os
import sys
from typing import Any, Dict, List, Optional

from agent_core.common.logger import get_logger

# 默认插件目录
_DEFAULT_PLUGIN_DIR = "plugins"

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


def _find_plugin_classes(file_path: str) -> List[Dict[str, str]]:
    """
    扫描Python文件，找出所有ModuleInterface子类。

    Args:
        file_path: Python文件路径。

    Returns:
        插件类信息列表，每项包含class_name和module_name。
    """
    # 延迟导入避免循环依赖
    from agent_core.common.interfaces import ModuleInterface

    if not os.path.isfile(file_path):
        return []

    try:
        spec = importlib.util.spec_from_file_location(
            f"plugin_scan_{os.path.basename(file_path)}", file_path
        )
        if spec is None or spec.loader is None:
            return []
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:
        return []

    plugins = []
    for name, obj in inspect.getmembers(module, inspect.isclass):
        if (
            obj is not ModuleInterface
            and issubclass(obj, ModuleInterface)
            and obj.__module__ == module.__name__
        ):
            # module_name是property，无法不实例化获取
            # 检查是否定义了module_name property
            has_module_name = "module_name" in obj.__dict__
            plugins.append({
                "class_name": name,
                "module_name": f"<requires instantiation: {name}>" if has_module_name else name,
                "file": file_path,
            })

    return plugins


def cmd_plugin_list(args) -> int:
    """
    列出目录中的可用插件。

    扫描指定目录（默认./plugins/）中的Python文件，
    找出所有ModuleInterface子类。
    """
    plugin_dir = getattr(args, "dir", _DEFAULT_PLUGIN_DIR)

    if not os.path.isdir(plugin_dir):
        _print_info(f"Plugin directory not found: {plugin_dir}")
        _print_info(
            "Create a plugins/ directory and place your plugin files there, "
            "or specify with --dir <path>"
        )
        return 0

    print(_colorize(f"=== Plugins in {plugin_dir}/ ===", _COLOR_BOLD))
    print()

    found_any = False
    for filename in sorted(os.listdir(plugin_dir)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        file_path = os.path.join(plugin_dir, filename)
        plugins = _find_plugin_classes(file_path)

        if plugins:
            found_any = True
            print(_colorize(f"  {filename}", _COLOR_CYAN))
            for p in plugins:
                print(f"    class:    {p['class_name']}")
                print(f"    module:   {p['module_name']}")
                print()
        else:
            # 检查文件是否可导入但有错误
            try:
                spec = importlib.util.spec_from_file_location(
                    f"scan_{filename}", file_path
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
            except Exception as exc:
                print(_colorize(f"  {filename} (import error: {exc})",
                                _COLOR_YELLOW))
                print()

    if not found_any:
        _print_info("No valid plugins found.")
        _print_info(
            "Plugins must be Python classes inheriting from ModuleInterface."
        )

    return 0


async def _load_and_validate_plugin(
    file_path: str,
    class_name: str,
    config: Dict[str, Any],
) -> Optional[Any]:
    """
    加载并验证插件。

    Args:
        file_path: 插件文件路径。
        class_name: 插件类名。
        config: 初始化配置。

    Returns:
        加载的插件实例，或None。
    """
    from agent_core.common.plugin_registry import PluginRegistry

    registry = PluginRegistry()
    ok = await registry.load_from_path(file_path, class_name, config)
    if not ok:
        return None

    # 获取插件实例
    plugins = registry.list_plugins()
    if not plugins:
        return None

    return registry.get_plugin(plugins[-1])


async def cmd_plugin_load_async(args) -> int:
    """加载并验证插件（异步实现）。"""
    file_path = getattr(args, "file", None)
    class_name = getattr(args, "class_name", None)

    if not file_path:
        _print_error("Plugin file is required (--file <path>)")
        return 1
    if not class_name:
        _print_error("Plugin class name is required (--class <name>)")
        return 1

    if not os.path.isfile(file_path):
        _print_error(f"Plugin file not found: {file_path}")
        return 1

    # 解析配置
    config_str = getattr(args, "config", None)
    config: Dict[str, Any] = {}
    if config_str:
        try:
            config = json.loads(config_str)
        except json.JSONDecodeError as exc:
            _print_error(f"Invalid config JSON: {exc}")
            return 1

    _print_info(f"Loading plugin: {class_name} from {file_path}")

    from agent_core.common.plugin_registry import PluginRegistry

    registry = PluginRegistry()
    ok = await registry.load_from_path(file_path, class_name, config)

    if not ok:
        _print_error("Plugin load failed")
        return 1

    plugin_names = registry.list_plugins()
    if not plugin_names:
        _print_error("Plugin loaded but not registered")
        return 1

    plugin = registry.get_plugin(plugin_names[-1])
    _print_success(f"Plugin loaded: {plugin.module_name}")
    print(f"  Version: {plugin.version}")

    # 执行健康检查
    _print_info("Running health check...")
    try:
        health = await plugin.health_check()
        status = health.get("status", "unknown")
        if status == "healthy":
            _print_success(f"Health check: {status}")
        else:
            _print_warning(f"Health check: {status}")
        print(f"  Details: {json.dumps(health, ensure_ascii=False, default=str)}")
    except Exception as exc:
        _print_error(f"Health check failed: {exc}")

    # 关闭插件
    _print_info("Shutting down plugin...")
    try:
        await plugin.shutdown()
        _print_success("Plugin shut down cleanly")
    except Exception as exc:
        _print_error(f"Shutdown failed: {exc}")

    return 0


def cmd_plugin_load(args) -> int:
    """加载并验证插件。"""
    return asyncio.run(cmd_plugin_load_async(args))


async def cmd_plugin_info_async(args) -> int:
    """查看插件元信息（异步实现）。"""
    file_path = getattr(args, "file", None)
    class_name = getattr(args, "class_name", None)

    if not file_path:
        _print_error("Plugin file is required (--file <path>)")
        return 1
    if not class_name:
        _print_error("Plugin class name is required (--class <name>)")
        return 1

    if not os.path.isfile(file_path):
        _print_error(f"Plugin file not found: {file_path}")
        return 1

    # 扫描文件中的插件类
    plugins = _find_plugin_classes(file_path)
    target = None
    for p in plugins:
        if p["class_name"] == class_name:
            target = p
            break

    if target is None:
        _print_error(
            f"Class '{class_name}' not found in {file_path}. "
            f"Available: {', '.join(p['class_name'] for p in plugins) or 'none'}"
        )
        return 1

    print(_colorize("=== Plugin Info ===", _COLOR_BOLD))
    print(f"  File:        {file_path}")
    print(f"  Class:       {target['class_name']}")
    print(f"  Module Name: {target['module_name']}")

    # 尝试获取版本（需要实例化，但不初始化）
    try:
        spec = importlib.util.spec_from_file_location(
            "plugin_info", file_path
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            cls = getattr(module, class_name, None)
            if cls:
                # 检查是否有version属性
                version = getattr(cls, "version", None)
                if isinstance(version, property):
                    print(f"  Version:     <requires instantiation>")
                elif version:
                    print(f"  Version:     {version}")
    except Exception as exc:
        print(f"  Version:     <error: {exc}>")

    return 0


def cmd_plugin_info(args) -> int:
    """查看插件元信息。"""
    return asyncio.run(cmd_plugin_info_async(args))


async def cmd_plugin_health_async(args) -> int:
    """对插件执行健康检查（异步实现）。"""
    file_path = getattr(args, "file", None)
    class_name = getattr(args, "class_name", None)

    if not file_path or not class_name:
        _print_error("Both --file and --class are required")
        return 1

    if not os.path.isfile(file_path):
        _print_error(f"Plugin file not found: {file_path}")
        return 1

    config_str = getattr(args, "config", None)
    config: Dict[str, Any] = {}
    if config_str:
        try:
            config = json.loads(config_str)
        except json.JSONDecodeError as exc:
            _print_error(f"Invalid config JSON: {exc}")
            return 1

    _print_info(f"Loading plugin for health check: {class_name}")

    plugin = await _load_and_validate_plugin(file_path, class_name, config)
    if plugin is None:
        _print_error("Plugin load failed")
        return 1

    print(_colorize("=== Plugin Health Check ===", _COLOR_BOLD))
    print(f"  Plugin:  {plugin.module_name}")
    print(f"  Version: {plugin.version}")

    try:
        health = await plugin.health_check()
        status = health.get("status", "unknown")
        if status == "healthy":
            _print_success(f"Status: {status}")
        elif status == "degraded":
            _print_warning(f"Status: {status}")
        else:
            _print_error(f"Status: {status}")

        print(_colorize("--- Details ---", _COLOR_CYAN))
        for key, value in health.items():
            if key != "status":
                print(f"  {key}: {value}")
    except Exception as exc:
        _print_error(f"Health check failed: {exc}")
        return 1
    finally:
        try:
            await plugin.shutdown()
        except Exception:
            pass

    return 0 if status == "healthy" else 1


def cmd_plugin_health(args) -> int:
    """对插件执行健康检查。"""
    return asyncio.run(cmd_plugin_health_async(args))


def add_plugin_subparser(subparsers) -> None:
    """
    注册plugin子命令组到CLI解析器。

    Args:
        subparsers: argparse子命令解析器组。
    """
    plugin_parser = subparsers.add_parser(
        "plugin",
        help="插件管理（列出/加载/验证/健康检查）",
        description="插件管理工具：列出可用插件、加载验证、健康检查",
    )
    plugin_sub = plugin_parser.add_subparsers(dest="plugin_action")

    # plugin list
    list_parser = plugin_sub.add_parser(
        "list", help="列出目录中的可用插件"
    )
    list_parser.add_argument(
        "--dir", "-d", default=_DEFAULT_PLUGIN_DIR,
        help=f"插件目录（默认: {_DEFAULT_PLUGIN_DIR}）"
    )

    # plugin load
    load_parser = plugin_sub.add_parser(
        "load", help="加载并验证插件（初始化→健康检查→关闭）"
    )
    load_parser.add_argument(
        "--file", "-f", required=True,
        help="插件文件路径"
    )
    load_parser.add_argument(
        "--class", "-c", dest="class_name", required=True,
        help="插件类名"
    )
    load_parser.add_argument(
        "--config", default=None,
        help="初始化配置（JSON字符串）"
    )

    # plugin info
    info_parser = plugin_sub.add_parser(
        "info", help="查看插件元信息（不加载）"
    )
    info_parser.add_argument(
        "--file", "-f", required=True,
        help="插件文件路径"
    )
    info_parser.add_argument(
        "--class", "-c", dest="class_name", required=True,
        help="插件类名"
    )

    # plugin health
    health_parser = plugin_sub.add_parser(
        "health", help="对插件执行健康检查"
    )
    health_parser.add_argument(
        "--file", "-f", required=True,
        help="插件文件路径"
    )
    health_parser.add_argument(
        "--class", "-c", dest="class_name", required=True,
        help="插件类名"
    )
    health_parser.add_argument(
        "--config", default=None,
        help="初始化配置（JSON字符串）"
    )


def handle_plugin(args) -> int:
    """
    处理plugin子命令分发（同步入口，用于Shell）。

    Args:
        args: 解析后的命令行参数。

    Returns:
        退出码。
    """
    return asyncio.run(handle_plugin_async(args))


async def handle_plugin_async(args) -> int:
    """
    处理plugin子命令分发（异步入口，用于CLI）。

    Args:
        args: 解析后的命令行参数。

    Returns:
        退出码。
    """
    action = getattr(args, "plugin_action", None)

    if action is None or action == "list":
        # 无子动作时默认list
        if not hasattr(args, "dir"):
            args.dir = _DEFAULT_PLUGIN_DIR
        return cmd_plugin_list(args)
    elif action == "load":
        return await cmd_plugin_load_async(args)
    elif action == "info":
        return await cmd_plugin_info_async(args)
    elif action == "health":
        return await cmd_plugin_health_async(args)
    else:
        _print_error(f"Unknown plugin action: {action}")
        return 1
