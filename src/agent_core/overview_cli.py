"""
系统概览仪表盘。

第一性原理：
- 用户需要快速判断系统全貌，而非逐个命令查询
- 概览应聚合关键信息：配置、日志、数据、插件状态
- 信息分层展示：摘要→详情，用户按需深入
- 支持多格式输出（text/json），适应不同场景

设计要点：
- collect_overview: 收集系统各维度信息
- format_overview_text: 文本格式输出
- format_overview_json: JSON格式输出
- overview CLI: --format text/json, --section 选择性显示
- 聚合：配置状态/日志摘要/数据统计/插件信息/运行状态
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

# 颜色
_COLOR_RESET = "\033[0m"
_COLOR_RED = "\033[31m"
_COLOR_GREEN = "\033[32m"
_COLOR_YELLOW = "\033[33m"
_COLOR_BLUE = "\033[34m"
_COLOR_CYAN = "\033[36m"
_COLOR_BOLD = "\033[1m"
_COLOR_DIM = "\033[2m"

_COLOR_ENABLED = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False


def _c(text: str, color: str) -> str:
    """添加颜色。"""
    if not _COLOR_ENABLED:
        return text
    return f"{color}{text}{_COLOR_RESET}"


def _status_icon(ok: bool) -> str:
    """状态图标。"""
    if _COLOR_ENABLED:
        return _c("[OK]", _COLOR_GREEN) if ok else _c("[FAIL]", _COLOR_RED)
    return "[OK]" if ok else "[FAIL]"


def collect_config_info(env: str = "dev") -> Dict[str, Any]:
    """
    收集配置信息。

    Args:
        env: 环境名。

    Returns:
        配置信息字典。
    """
    info: Dict[str, Any] = {
        "env": env,
        "config_loaded": False,
        "config_path": None,
        "item_count": 0,
        "valid": False,
        "errors": [],
    }

    try:
        from agent_core.common.config_validator import ConfigValidator
        from agent_core.common.environment_config import EnvironmentConfig

        config_dir = os.environ.get(
            "AGENT_CONFIG_DIR",
            os.path.join(os.getcwd(), "config"),
        )

        if os.path.exists(config_dir):
            env_config = EnvironmentConfig(config_dir=config_dir)
            config = env_config.all_config
            if config:
                info["config_loaded"] = True
                info["config_path"] = config_dir
                info["item_count"] = len(config)

                validator = ConfigValidator()
                ok, errors = validator.validate(config)
                info["valid"] = ok
                info["errors"] = errors
    except Exception as exc:
        info["errors"] = [str(exc)]

    return info


def collect_log_info() -> Dict[str, Any]:
    """
    收集日志信息。

    Returns:
        日志信息字典。
    """
    info: Dict[str, Any] = {
        "log_files": [],
        "total_size": 0,
        "total_lines": 0,
        "error_count": 0,
        "warning_count": 0,
    }

    # 查找日志文件
    log_dirs = ["logs", "log", "."]
    log_patterns = [".log", ".log."]
    log_files: List[Dict[str, Any]] = []

    for log_dir in log_dirs:
        if not os.path.isdir(log_dir):
            continue
        try:
            for fname in os.listdir(log_dir):
                fpath = os.path.join(log_dir, fname)
                if not os.path.isfile(fpath):
                    continue
                if not any(p in fname for p in log_patterns):
                    continue
                try:
                    size = os.path.getsize(fpath)
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    line_count = len(lines)
                    errors = sum(1 for l in lines if "ERROR" in l)
                    warnings = sum(1 for l in lines if "WARNING" in l)

                    log_files.append({
                        "path": fpath,
                        "size": size,
                        "lines": line_count,
                        "errors": errors,
                        "warnings": warnings,
                    })
                    info["total_size"] += size
                    info["total_lines"] += line_count
                    info["error_count"] += errors
                    info["warning_count"] += warnings
                except OSError:
                    pass
        except OSError:
            pass

    info["log_files"] = log_files
    return info


def collect_data_info() -> Dict[str, Any]:
    """
    收集数据信息。

    Returns:
        数据信息字典。
    """
    info: Dict[str, Any] = {
        "db_exists": False,
        "db_path": None,
        "experience_count": 0,
        "config_snapshots": 0,
        "runtime_state_count": 0,
    }

    db_path = os.path.join(os.getcwd(), "agent_memory.db")
    if os.path.exists(db_path):
        info["db_exists"] = True
        info["db_path"] = db_path
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # experiences表
            try:
                cursor.execute("SELECT COUNT(*) FROM experiences")
                info["experience_count"] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                pass

            # config_snapshots表
            try:
                cursor.execute("SELECT COUNT(*) FROM config_snapshots")
                info["config_snapshots"] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                pass

            # runtime_state表
            try:
                cursor.execute("SELECT COUNT(*) FROM runtime_state")
                info["runtime_state_count"] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                pass

            conn.close()
        except Exception:
            pass

    return info


def collect_plugin_info() -> Dict[str, Any]:
    """
    收集插件信息。

    Returns:
        插件信息字典。
    """
    info: Dict[str, Any] = {
        "plugin_count": 0,
        "plugins": [],
    }

    try:
        from agent_core.common.plugin_registry import PluginRegistry
        registry = PluginRegistry()
        plugins = registry.list_plugins()
        info["plugin_count"] = len(plugins)
        info["plugins"] = [
            {"name": p} for p in plugins
        ] if plugins else []
    except Exception:
        pass

    return info


def collect_runtime_info(port: int = 8080) -> Dict[str, Any]:
    """
    收集运行时信息（通过Dashboard API）。

    Args:
        port: Dashboard端口。

    Returns:
        运行时信息字典。
    """
    info: Dict[str, Any] = {
        "agent_running": False,
        "status": "stopped",
        "port": port,
    }

    try:
        import urllib.request
        import urllib.error

        url = f"http://127.0.0.1:{port}/api/status"
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            info["agent_running"] = True
            info["status"] = data.get("status", "unknown")
            info["cycle_count"] = data.get("cycle_count", 0)
            info["interrupt_count"] = data.get("interrupt_count", 0)
    except (urllib.error.URLError, Exception):
        pass

    return info


def collect_overview(
    env: str = "dev",
    port: int = 8080,
) -> Dict[str, Any]:
    """
    收集系统全貌信息。

    Args:
        env: 环境名。
        port: Dashboard端口。

    Returns:
        包含所有维度信息的字典。
    """
    return {
        "config": collect_config_info(env),
        "logs": collect_log_info(),
        "data": collect_data_info(),
        "plugins": collect_plugin_info(),
        "runtime": collect_runtime_info(port),
    }


def format_overview_text(overview: Dict[str, Any]) -> str:
    """
    格式化概览为文本。

    Args:
        overview: 概览数据。

    Returns:
        格式化的文本。
    """
    lines: List[str] = []

    lines.append(_c("=" * 60, _COLOR_CYAN))
    lines.append(_c("  System Overview", _COLOR_BOLD))
    lines.append(_c("=" * 60, _COLOR_CYAN))
    lines.append("")

    # 配置
    config = overview.get("config", {})
    lines.append(_c("--- Configuration ---", _COLOR_BLUE))
    lines.append(f"  Environment:    {config.get('env', 'dev')}")
    lines.append(f"  Config loaded:  {_status_icon(config.get('config_loaded', False))}")
    if config.get("config_path"):
        lines.append(f"  Config path:    {config['config_path']}")
    lines.append(f"  Config items:   {config.get('item_count', 0)}")
    valid = config.get("valid", False)
    lines.append(f"  Config valid:   {_status_icon(valid)}")
    if config.get("errors"):
        for err in config["errors"][:3]:
            lines.append(f"    {_c('- ' + str(err), _COLOR_RED)}")
    lines.append("")

    # 运行时
    runtime = overview.get("runtime", {})
    lines.append(_c("--- Runtime ---", _COLOR_BLUE))
    running = runtime.get("agent_running", False)
    lines.append(f"  Agent running:  {_status_icon(running)}")
    lines.append(f"  Status:         {runtime.get('status', 'stopped')}")
    if running:
        lines.append(f"  Cycle count:    {runtime.get('cycle_count', 0)}")
        lines.append(f"  Interrupts:     {runtime.get('interrupt_count', 0)}")
    lines.append(f"  Dashboard port: {runtime.get('port', 8080)}")
    lines.append("")

    # 日志
    logs = overview.get("logs", {})
    lines.append(_c("--- Logs ---", _COLOR_BLUE))
    log_files = logs.get("log_files", [])
    lines.append(f"  Log files:      {len(log_files)}")
    lines.append(f"  Total size:     {_format_size(logs.get('total_size', 0))}")
    lines.append(f"  Total lines:    {logs.get('total_lines', 0)}")
    lines.append(f"  Errors:         {_c(str(logs.get('error_count', 0)), _COLOR_RED) if logs.get('error_count', 0) > 0 else logs.get('error_count', 0)}")
    lines.append(f"  Warnings:       {_c(str(logs.get('warning_count', 0)), _COLOR_YELLOW) if logs.get('warning_count', 0) > 0 else logs.get('warning_count', 0)}")
    lines.append("")

    # 数据
    data = overview.get("data", {})
    lines.append(_c("--- Data ---", _COLOR_BLUE))
    db_exists = data.get("db_exists", False)
    lines.append(f"  Database:       {_status_icon(db_exists)}")
    if db_exists:
        lines.append(f"  DB path:        {data.get('db_path', '')}")
        lines.append(f"  Experiences:    {data.get('experience_count', 0)}")
        lines.append(f"  Config snapshots: {data.get('config_snapshots', 0)}")
        lines.append(f"  Runtime states: {data.get('runtime_state_count', 0)}")
    lines.append("")

    # 插件
    plugins = overview.get("plugins", {})
    lines.append(_c("--- Plugins ---", _COLOR_BLUE))
    lines.append(f"  Plugin count:   {plugins.get('plugin_count', 0)}")
    plugin_list = plugins.get("plugins", [])
    if plugin_list:
        for p in plugin_list[:5]:
            lines.append(f"    - {p.get('name', 'unknown')}")
    lines.append("")

    lines.append(_c("=" * 60, _COLOR_CYAN))
    return "\n".join(lines)


def format_overview_json(overview: Dict[str, Any]) -> str:
    """
    格式化概览为JSON。

    Args:
        overview: 概览数据。

    Returns:
        JSON字符串。
    """
    return json.dumps(overview, indent=2, ensure_ascii=False, default=str)


def _format_size(size: int) -> str:
    """格式化文件大小。"""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.1f} GB"


def cmd_overview(args: argparse.Namespace) -> int:
    """
    CLI入口：显示系统概览。

    Args:
        args: 命令行参数。

    Returns:
        退出码。
    """
    fmt = getattr(args, "format", "text")
    env = getattr(args, "env", "dev")
    port = getattr(args, "port", 8080)

    overview = collect_overview(env=env, port=port)

    if fmt == "json":
        print(format_overview_json(overview))
    else:
        print(format_overview_text(overview))

    return 0


def handle_overview(args: argparse.Namespace) -> int:
    """处理overview命令（同步入口）。"""
    return cmd_overview(args)


def add_overview_subparser(subparsers: argparse._SubParsersAction) -> None:
    """
    注册overview子命令。

    Args:
        subparsers: argparse子命令解析器。
    """
    overview_parser = subparsers.add_parser(
        "overview",
        help="系统概览（一键查看全貌）",
        description="显示系统全貌：配置/日志/数据/插件/运行状态。",
    )
    overview_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="输出格式（默认: text）",
    )
    overview_parser.add_argument(
        "--env",
        default="dev",
        help="环境（默认: dev）",
    )
    overview_parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Dashboard端口（默认: 8080）",
    )
