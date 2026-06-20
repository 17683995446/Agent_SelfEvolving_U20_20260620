"""
智能帮助与命令建议系统。

第一性原理：
- 用户犯错是常态，系统应主动纠正而非报错
- 帮助应上下文感知：根据用户输入提供最相关的信息
- 命令建议基于相似度算法，降低用户记忆负担
- 好的帮助系统让新用户30秒内找到所需命令

设计要点：
- suggest_command: 基于编辑距离的模糊匹配
- cmd_help: 分类组织的增强帮助，支持特定命令详情
- handle_unknown_command: 未知命令时主动建议
- 命令分类：按功能域组织，降低认知负担
"""

import argparse
import difflib
import sys
from typing import Any, Dict, List, Optional, Tuple

# 输出颜色（与cli.py一致）
_COLOR_RESET = "\033[0m"
_COLOR_RED = "\033[31m"
_COLOR_GREEN = "\033[32m"
_COLOR_YELLOW = "\033[33m"
_COLOR_BLUE = "\033[34m"
_COLOR_CYAN = "\033[36m"
_COLOR_BOLD = "\033[1m"
_COLOR_DIM = "\033[2m"

_COLOR_ENABLED = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False


def _colorize(text: str, color: str) -> str:
    """添加颜色（非TTY环境不添加）。"""
    if not _COLOR_ENABLED:
        return text
    return f"{color}{text}{_COLOR_RESET}"


# 命令元数据：描述、分类、示例
COMMAND_METADATA: Dict[str, Dict[str, Any]] = {
    "start": {
        "category": "Lifecycle",
        "summary": "启动Agent",
        "description": "使用指定环境配置启动自驱进化Agent。支持dry-run模式验证配置。",
        "examples": [
            "agent start                    # 使用默认配置启动",
            "agent start --env prod         # 使用生产环境配置",
            "agent start --config my.yaml   # 使用指定配置文件",
            "agent start --dry-run          # 验证配置但不启动",
        ],
    },
    "status": {
        "category": "Lifecycle",
        "summary": "查询Agent运行状态",
        "description": "通过Dashboard API查询当前运行的Agent状态、周期数、错误等。",
        "examples": [
            "agent status                   # 查询默认端口状态",
            "agent status --port 9090       # 查询指定端口",
        ],
    },
    "health": {
        "category": "Lifecycle",
        "summary": "健康检查",
        "description": "初始化Agent并执行健康检查，验证各子系统是否正常。",
        "examples": [
            "agent health                   # 健康检查",
            "agent health --env prod        # 生产环境健康检查",
        ],
    },
    "dashboard": {
        "category": "Lifecycle",
        "summary": "启动独立Dashboard服务",
        "description": "启动Web监控面板，提供可视化状态查看。",
        "examples": [
            "agent dashboard                # 默认端口8080",
            "agent dashboard --port 9090    # 指定端口",
        ],
    },
    "version": {
        "category": "System",
        "summary": "显示版本信息",
        "description": "显示Agent版本、Python版本和安装路径。",
        "examples": [
            "agent version                  # 显示版本",
        ],
    },
    "shell": {
        "category": "Interaction",
        "summary": "启动交互式Shell",
        "description": "进入交互式命令行，支持所有子命令和脚本批量执行。",
        "examples": [
            "agent shell                    # 交互式Shell",
            "agent shell --script cmds.txt  # 批量执行脚本",
        ],
    },
    "init": {
        "category": "Configuration",
        "summary": "生成项目脚手架",
        "description": "在指定目录生成完整项目结构，含配置文件、目录结构和示例代码。",
        "examples": [
            "agent init myproject           # 生成项目",
            "agent init myproject --name myapp  # 指定应用名",
            "agent init myproject --yes     # 跳过交互确认",
        ],
    },
    "logs": {
        "category": "Data",
        "summary": "日志查看/过滤/分析",
        "description": "查看、搜索、分析日志文件，支持实时跟踪和智能异常检测。",
        "examples": [
            "agent logs show                # 查看最近日志",
            "agent logs show -n 100         # 查看最近100行",
            "agent logs show --level ERROR  # 只看ERROR级别",
            "agent logs grep \"error\" -i   # 搜索关键词",
            "agent logs analyze             # 智能分析",
            "agent logs tail                # 实时跟踪",
        ],
    },
    "plugin": {
        "category": "Extensibility",
        "summary": "插件管理",
        "description": "列出、加载验证、查看信息和健康检查插件模块。",
        "examples": [
            "agent plugin list              # 列出可用插件",
            "agent plugin load -f plug.py -c MyPlugin   # 加载验证",
            "agent plugin info -f plug.py -c MyPlugin   # 查看信息",
            "agent plugin health -f plug.py -c MyPlugin # 健康检查",
        ],
    },
    "log-rotate": {
        "category": "Data",
        "summary": "日志轮转管理",
        "description": "查看轮转状态、手动触发轮转、列出归档文件。",
        "examples": [
            "agent log-rotate status        # 查看轮转状态",
            "agent log-rotate rotate        # 手动轮转",
            "agent log-rotate rotate --force  # 强制轮转",
            "agent log-rotate archives      # 列出归档",
        ],
    },
    "config": {
        "category": "Configuration",
        "summary": "配置管理",
        "description": "比较配置差异、显示生效配置、验证配置有效性。",
        "examples": [
            "agent config diff -a base.yaml -b prod.yaml  # 比较差异",
            "agent config show               # 显示生效配置",
            "agent config validate           # 验证配置",
        ],
    },
    "data": {
        "category": "Data",
        "summary": "数据导出/导入/统计",
        "description": "导出经验数据为JSON、导入数据、查看数据统计。",
        "examples": [
            "agent data export               # 导出为JSON",
            "agent data import backup.json   # 导入数据",
            "agent data import backup.json --merge  # 合并导入",
            "agent data stats                # 数据统计",
        ],
    },
    "help": {
        "category": "System",
        "summary": "显示帮助信息",
        "description": "显示命令分类帮助或特定命令的详细帮助和示例。",
        "examples": [
            "agent help                      # 显示分类帮助",
            "agent help start                # 显示start命令详情",
            "agent help logs                 # 显示logs命令详情",
        ],
    },
    "wizard": {
        "category": "Configuration",
        "summary": "交互式配置向导",
        "description": "交互式向导引导生成配置文件，适合首次使用。支持非交互模式。",
        "examples": [
            "agent wizard                    # 交互式向导",
            "agent wizard myproject          # 指定项目目录",
            "agent wizard --yes              # 非交互模式（全部默认值）",
        ],
    },
    "alias": {
        "category": "System",
        "summary": "命令别名管理",
        "description": "管理命令别名，支持内置别名和用户自定义别名。别名让高频命令更短。",
        "examples": [
            "agent alias list                # 列出所有别名",
            "agent alias add go start        # 添加别名 go→start",
            "agent alias remove go           # 删除别名",
            "agent alias clear               # 清除所有用户别名",
        ],
    },
    "overview": {
        "category": "System",
        "summary": "系统概览（一键查看全貌）",
        "description": "聚合显示系统全貌：配置状态、日志摘要、数据统计、插件信息、运行状态。支持text/json格式。",
        "examples": [
            "agent overview                  # 文本格式概览",
            "agent overview --format json    # JSON格式概览",
            "agent overview --env prod       # 指定环境",
        ],
    },
    "history": {
        "category": "System",
        "summary": "命令历史管理",
        "description": "管理命令历史，支持持久化、搜索和统计。历史跨会话保留。",
        "examples": [
            "agent history                   # 列出最近历史",
            "agent history list -n 50        # 列出最近50条",
            "agent history search start      # 搜索含start的命令",
            "agent history search log --regex # 正则搜索",
            "agent history stats             # 历史统计",
            "agent history clear             # 清除历史",
        ],
    },
}

# 分类显示顺序
_CATEGORY_ORDER = ["Lifecycle", "Configuration", "Data", "Extensibility", "Interaction", "System"]


def suggest_command(
    input_cmd: str,
    available_cmds: List[str],
    max_suggestions: int = 3,
    cutoff: float = 0.4,
) -> List[str]:
    """
    基于相似度建议最接近的命令。

    使用difflib.SequenceMatcher计算相似度比率，
    返回按相似度降序排列的最接近命令列表。

    Args:
        input_cmd: 用户输入的（可能错误的）命令。
        available_cmds: 可用命令列表。
        max_suggestions: 最大建议数。
        cutoff: 相似度阈值（0~1），低于此值不建议。

    Returns:
        建议命令列表（按相似度降序）。
    """
    if not input_cmd or not available_cmds:
        return []

    # 精确匹配优先
    if input_cmd in available_cmds:
        return [input_cmd]

    # difflib模糊匹配
    matches = difflib.get_close_matches(
        input_cmd, available_cmds, n=max_suggestions, cutoff=cutoff
    )
    return matches


def suggest_subcommand(
    input_sub: str,
    available_subs: List[str],
    max_suggestions: int = 3,
) -> List[str]:
    """
    建议子命令（如logs的show/tail/analyze/grep）。

    Args:
        input_sub: 用户输入的子命令。
        available_subs: 可用子命令列表。
        max_suggestions: 最大建议数。

    Returns:
        建议子命令列表。
    """
    return suggest_command(input_sub, available_subs, max_suggestions)


def format_suggestions(suggestions: List[str]) -> str:
    """
    格式化建议输出。

    Args:
        suggestions: 建议命令列表。

    Returns:
        格式化的建议字符串。
    """
    if not suggestions:
        return ""
    if len(suggestions) == 1:
        return f"Did you mean: {_colorize(suggestions[0], _COLOR_CYAN)}?"
    cmds = ", ".join(_colorize(s, _COLOR_CYAN) for s in suggestions)
    return f"Did you mean one of: {cmds}?"


def handle_unknown_command(
    input_cmd: str,
    available_cmds: List[str],
) -> int:
    """
    处理未知命令：报错并提供建议。

    Args:
        input_cmd: 用户输入的未知命令。
        available_cmds: 可用命令列表。

    Returns:
        退出码（始终为1，表示错误）。
    """
    print(
        f"{_colorize('[ERROR]', _COLOR_RED)} "
        f"Unknown command: {_colorize(input_cmd, _COLOR_BOLD)}",
        file=sys.stderr,
    )

    suggestions = suggest_command(input_cmd, available_cmds)
    suggestion_text = format_suggestions(suggestions)
    if suggestion_text:
        print(f"  {suggestion_text}", file=sys.stderr)

    print(
        f"  Run {_colorize('agent help', _COLOR_CYAN)} to see all available commands.",
        file=sys.stderr,
    )
    return 1


def cmd_help(args: argparse.Namespace) -> int:
    """
    增强帮助系统。

    支持两种模式：
    1. agent help           - 显示分类命令列表
    2. agent help <command> - 显示特定命令的详细帮助和示例

    Args:
        args: 命令行参数，含可选的command字段。

    Returns:
        退出码（0成功，1命令不存在）。
    """
    target_cmd = getattr(args, "command_name", None)

    if target_cmd:
        return _show_command_detail(target_cmd)
    else:
        return _show_category_help()


def _show_category_help() -> int:
    """显示分类命令列表。"""
    print(_colorize("Self-Evolving Agent - Command Reference", _COLOR_BOLD))
    print()
    print("Usage: agent <command> [options]")
    print()
    print(_colorize("Commands by category:", _COLOR_CYAN))
    print()

    for category in _CATEGORY_ORDER:
        # 收集该分类下的命令
        cmds_in_category = [
            (name, meta)
            for name, meta in COMMAND_METADATA.items()
            if meta["category"] == category
        ]
        if not cmds_in_category:
            continue

        print(f"  {_colorize(category, _COLOR_YELLOW)}:")
        for name, meta in sorted(cmds_in_category):
            summary = meta["summary"]
            print(f"    {_colorize(name, _COLOR_GREEN):<16} {summary}")
        print()

    print(_colorize("Tips:", _COLOR_CYAN))
    print(f"  {_colorize('agent help <command>', _COLOR_DIM)}  Show detailed help for a command")
    print(f"  {_colorize('agent <command> --help', _COLOR_DIM)}  Show command options")
    print(f"  {_colorize('agent shell', _COLOR_DIM)}  Enter interactive shell")
    print()
    print(_colorize("Global Options:", _COLOR_CYAN))
    print(f"  {_colorize('--format text|json|table', _COLOR_DIM)}  Output format")
    print(f"  {_colorize('--no-color', _COLOR_DIM)}  Disable colors (accessibility)")
    print(f"  {_colorize('--quiet, -q', _COLOR_DIM)}  Quiet mode (errors only)")
    print(f"  {_colorize('--verbose, -V', _COLOR_DIM)}  Verbose mode (debug info)")
    return 0


def _show_command_detail(command: str) -> int:
    """
    显示特定命令的详细帮助。

    Args:
        command: 命令名。

    Returns:
        退出码。
    """
    if command not in COMMAND_METADATA:
        print(
            f"{_colorize('[ERROR]', _COLOR_RED)} "
            f"No help available for: {_colorize(command, _COLOR_BOLD)}",
            file=sys.stderr,
        )
        available = list(COMMAND_METADATA.keys())
        suggestions = suggest_command(command, available)
        suggestion_text = format_suggestions(suggestions)
        if suggestion_text:
            print(f"  {suggestion_text}", file=sys.stderr)
        return 1

    meta = COMMAND_METADATA[command]
    print(_colorize(f"agent {command}", _COLOR_BOLD))
    print()
    print(f"  {_colorize('Summary:', _COLOR_CYAN)} {meta['summary']}")
    print(f"  {_colorize('Category:', _COLOR_CYAN)} {meta['category']}")
    print()
    print(f"  {_colorize('Description:', _COLOR_CYAN)}")
    # 描述文本换行缩进
    desc_lines = meta["description"].split("\n")
    for line in desc_lines:
        print(f"    {line}")
    print()

    examples = meta.get("examples", [])
    if examples:
        print(f"  {_colorize('Examples:', _COLOR_CYAN)}")
        for ex in examples:
            print(f"    {_colorize(ex, _COLOR_DIM)}")
        print()

    print(
        f"  Run {_colorize(f'agent {command} --help', _COLOR_CYAN)} "
        f"for full option list."
    )
    return 0


def add_help_subparser(subparsers: argparse._SubParsersAction) -> None:
    """
    注册help子命令。

    Args:
        subparsers: argparse子命令解析器。
    """
    help_parser = subparsers.add_parser(
        "help",
        help="显示帮助信息（agent help [command]）",
        description="显示命令分类帮助或特定命令的详细帮助和示例。",
    )
    help_parser.add_argument(
        "command_name",
        nargs="?",
        default=None,
        help="要查看详情的命令名（可选）",
    )


def get_all_commands() -> List[str]:
    """获取所有可用命令列表（含help）。"""
    return list(COMMAND_METADATA.keys())


def get_commands_by_category() -> Dict[str, List[str]]:
    """按分类获取命令列表。"""
    result: Dict[str, List[str]] = {}
    for name, meta in COMMAND_METADATA.items():
        cat = meta["category"]
        result.setdefault(cat, []).append(name)
    return result
