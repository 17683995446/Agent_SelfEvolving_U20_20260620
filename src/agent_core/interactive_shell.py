"""
交互式Shell。

提供实时交互式命令行界面，降低调试与运维认知负荷。

第一性原理：
- 对话式交互：生物通过对话式反馈学习，实时交互降低认知负荷
- 即时反馈：命令立即执行并返回结果，无需编写脚本
- 渐进式探索：从简单命令到复杂操作，用户按需深入

设计要点：
- 基于cmd.Cmd：标准库，零依赖
- 命令补全：Tab自动补全命令名
- 历史记录：上下键浏览历史命令
- 脚本模式：支持从文件批量执行命令
- 友好提示：每个命令有帮助信息
"""

import cmd
import json
import os
import sys
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from agent_core.common.logger import get_logger

# 默认Dashboard端口
_DEFAULT_PORT = 8080

# 颜色
_COLOR_RESET = "\033[0m"
_COLOR_RED = "\033[31m"
_COLOR_GREEN = "\033[32m"
_COLOR_YELLOW = "\033[33m"
_COLOR_CYAN = "\033[36m"
_COLOR_BOLD = "\033[1m"
_COLOR_BLUE = "\033[34m"


def _c(text: str, color: str) -> str:
    """添加颜色。"""
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{_COLOR_RESET}"


class AgentShell(cmd.Cmd):
    """
    Agent交互式Shell。

    提供状态查询、配置管理、预测触发等交互式命令。
    """

    intro = _c(
        "=== Self-Evolving Agent Interactive Shell ===\n"
        "Type 'help' or '?' to list commands. Type 'exit' to quit.\n",
        _COLOR_CYAN,
    )
    prompt = _c("agent> ", _COLOR_GREEN)

    def __init__(
        self,
        port: int = _DEFAULT_PORT,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__()
        self._port = port
        self._config = config or {}
        self._logger = get_logger()
        self._history: List[str] = []

    @property
    def _base_url(self) -> str:
        return f"http://127.0.0.1:{self._port}"

    def _api_get(self, path: str) -> Optional[Dict[str, Any]]:
        """GET请求Dashboard API。"""
        url = f"{self._base_url}{path}"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError:
            print(_c(
                f"Cannot connect to Agent at port {self._port}. "
                f"Is it running? Use 'agent start' to start.",
                _COLOR_RED,
            ))
            return None
        except Exception as exc:
            print(_c(f"Request failed: {exc}", _COLOR_RED))
            return None

    def _record_history(self, line: str) -> None:
        """记录命令历史。"""
        self._history.append(line)

    # === 状态命令 ===

    def do_status(self, arg: str) -> None:
        """
        显示Agent运行状态。

        用法: status
        """
        data = self._api_get("/api/status")
        if data is None:
            return

        print(_c("=== Agent Status ===", _COLOR_BOLD))
        print(f"  Status:       {_c(data.get('status', 'unknown'), _COLOR_CYAN)}")
        print(f"  Cycle Count:  {data.get('cycle_count', 0)}")
        print(f"  Interrupts:   {data.get('interrupt_count', 0)}")

        errors = data.get("recent_errors", [])
        if errors:
            print(f"  {_c('Recent Errors:', _COLOR_YELLOW)} ({len(errors)})")
            for err in errors[-5:]:
                print(f"    - {err}")

        rewards = data.get("recent_rewards", [])
        if rewards:
            avg = sum(rewards) / len(rewards)
            print(f"  Avg Reward:   {avg:.3f} (last {len(rewards)})")

        task = data.get("current_task")
        if task:
            print(f"  Current Task: {task}")

    def do_metrics(self, arg: str) -> None:
        """
        显示Prometheus格式指标。

        用法: metrics
        """
        url = f"{self._base_url}/metrics"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                content = resp.read().decode("utf-8")
            print(content)
        except urllib.error.URLError:
            print(_c(
                f"Cannot connect to Agent at port {self._port}.",
                _COLOR_RED,
            ))

    def do_health(self, arg: str) -> None:
        """
        查询Agent健康状态。

        用法: health
        """
        data = self._api_get("/api/status")
        if data is None:
            return

        status = data.get("status", "unknown")
        if status == "running" or status == "healthy":
            print(_c(f"[HEALTHY] Agent is {status}", _COLOR_GREEN))
        else:
            print(_c(f"[{status.upper()}] Agent status: {status}", _COLOR_YELLOW))

    # === 配置命令 ===

    def do_config(self, arg: str) -> None:
        """
        查看或修改配置。

        用法:
          config              # 显示全部配置
          config <key>        # 显示指定配置项
          config <key> <val>  # 修改配置项
        """
        parts = arg.split(None, 1)
        if not parts:
            # 显示全部配置
            data = self._api_get("/api/status")
            if data is None:
                return
            config = data.get("config", {})
            print(_c("=== Current Configuration ===", _COLOR_BOLD))
            for key in sorted(config.keys()):
                print(f"  {key}: {config[key]}")
            return

        key = parts[0]
        if len(parts) == 1:
            # 显示单个配置项
            data = self._api_get("/api/status")
            if data is None:
                return
            config = data.get("config", {})
            if key in config:
                print(f"  {key} = {config[key]}")
            else:
                print(_c(f"Config key '{key}' not found", _COLOR_RED))
        else:
            # 修改配置项
            value = parts[1]
            print(_c(
                f"Config modification not supported in read-only shell. "
                f"Edit config file and restart agent.",
                _COLOR_YELLOW,
            ))

    # === 诊断命令 ===

    def do_profile(self, arg: str) -> None:
        """
        显示性能分析（cProfile）。

        用法: profile [lines]
        """
        lines = 10
        if arg:
            try:
                lines = int(arg)
            except ValueError:
                print(_c("Invalid line count", _COLOR_RED))
                return

        url = f"{self._base_url}/profile"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                content = resp.read().decode("utf-8")
            # 显示前N行
            for line in content.split("\n")[:lines]:
                print(line)
        except urllib.error.URLError:
            print(_c(
                f"Cannot connect to Agent at port {self._port}.",
                _COLOR_RED,
            ))

    def do_errors(self, arg: str) -> None:
        """
        显示最近错误。

        用法: errors [count]
        """
        count = 10
        if arg:
            try:
                count = int(arg)
            except ValueError:
                print(_c("Invalid count", _COLOR_RED))
                return

        data = self._api_get("/api/status")
        if data is None:
            return

        errors = data.get("recent_errors", [])
        if not errors:
            print(_c("No recent errors", _COLOR_GREEN))
            return

        print(_c(f"=== Recent Errors (last {count}) ===", _COLOR_BOLD))
        for err in errors[-count:]:
            print(f"  {_c('•', _COLOR_RED)} {err}")

    # === 系统命令 ===

    def do_port(self, arg: str) -> None:
        """
        设置Dashboard端口。

        用法: port <number>
        """
        if not arg:
            print(f"Current port: {self._port}")
            return
        try:
            self._port = int(arg)
            print(_c(f"Port set to {self._port}", _COLOR_GREEN))
        except ValueError:
            print(_c("Invalid port number", _COLOR_RED))

    def do_history(self, arg: str) -> None:
        """
        显示命令历史。

        用法: history
        """
        if not self._history:
            print("No commands in history")
            return
        for i, cmd_line in enumerate(self._history, 1):
            print(f"  {i:3d}  {cmd_line}")

    # === 日志命令（U-6）===

    def do_logs(self, arg: str) -> None:
        """
        日志查看/过滤/分析。

        用法:
          logs                       # 显示最近日志（默认50行）
          logs show                  # 显示日志
          logs show -n 100           # 显示最后100行
          logs show --level ERROR    # 只显示ERROR级别
          logs analyze               # 智能分析日志
          logs grep <pattern>        # 搜索关键词
          logs grep <pattern> -i     # 忽略大小写搜索
          logs tail                  # 实时跟踪日志

        选项:
          -f, --file <path>    指定日志文件路径
          -n, --lines <N>      显示行数（默认50）
          --level <LEVEL>      按级别过滤
          -C, --context <N>    上下文行数（grep）
          -i, --ignore-case    忽略大小写（grep）
        """
        from agent_core.logs_cli import handle_logs
        from agent_core.cli import _build_parser

        # 复用CLI解析器处理参数
        parser = _build_parser()
        try:
            args = parser.parse_args(["logs"] + arg.split())
        except SystemExit:
            return

        result = handle_logs(args)
        if result != 0:
            print(_c(f"Command failed (exit code: {result})", _COLOR_RED))

    # === 插件命令（U-7）===

    def do_plugin(self, arg: str) -> None:
        """
        插件管理（列出/加载/验证/健康检查）。

        用法:
          plugin                              # 列出可用插件
          plugin list                         # 列出可用插件
          plugin list --dir ./my_plugins      # 指定插件目录
          plugin load -f <file> -c <Class>    # 加载并验证插件
          plugin info -f <file> -c <Class>    # 查看插件信息
          plugin health -f <file> -c <Class>  # 插件健康检查

        选项:
          -f, --file <path>     插件文件路径
          -c, --class <name>    插件类名
          --config <json>       初始化配置（JSON字符串）
          -d, --dir <path>      插件目录（list命令）
        """
        from agent_core.plugin_cli import handle_plugin
        from agent_core.cli import _build_parser

        parser = _build_parser()
        try:
            args = parser.parse_args(["plugin"] + arg.split())
        except SystemExit:
            return

        result = handle_plugin(args)
        if result != 0:
            print(_c(f"Command failed (exit code: {result})", _COLOR_RED))

    # === 日志轮转命令（U-8）===

    def do_log_rotate(self, arg: str) -> None:
        """
        日志轮转管理（状态/轮转/归档）。

        用法:
          log-rotate                          # 查看轮转状态
          log-rotate status                   # 查看轮转状态
          log-rotate rotate                   # 手动触发轮转
          log-rotate rotate --force           # 强制轮转
          log-rotate archives                 # 列出归档文件

        选项:
          -f, --file <path>       日志文件路径
          --max-bytes <N>         最大字节数
          --backup-count <N>      备份数量
          --force                 强制轮转
        """
        from agent_core.log_rotate_cli import handle_log_rotate
        from agent_core.cli import _build_parser

        parser = _build_parser()
        try:
            args = parser.parse_args(["log-rotate"] + arg.split())
        except SystemExit:
            return

        result = handle_log_rotate(args)
        if result != 0:
            print(_c(f"Command failed (exit code: {result})", _COLOR_RED))

    # === 配置命令（U-9）===

    def do_config_diff(self, arg: str) -> None:
        """
        配置管理（diff/show/validate）。

        用法:
          config-diff -a <fileA> -b <fileB>   # 比较两个配置文件
          config show                          # 显示生效配置
          config validate                      # 验证配置

        选项:
          -a, --file-a <path>    配置文件A
          -b, --file-b <path>    配置文件B
          --env <env>            环境（show/validate）
          --config <path>        配置文件路径（show/validate）
        """
        from agent_core.config_cli import handle_config
        from agent_core.cli import _build_parser

        # 支持 config-diff 作为快捷方式
        if arg and not arg.startswith("-"):
            # 如果第一个参数不是选项，当作 diff 子命令
            parts = arg.split(None, 1)
            if parts[0] in ("diff", "show", "validate"):
                full_arg = arg
            else:
                full_arg = f"diff {arg}"
        else:
            full_arg = f"diff {arg}" if arg else ""

        parser = _build_parser()
        try:
            args = parser.parse_args(["config"] + full_arg.split())
        except SystemExit:
            return

        result = handle_config(args)
        if result != 0:
            print(_c(f"Command failed (exit code: {result})", _COLOR_RED))

    # === 数据命令（U-10）===

    def do_data(self, arg: str) -> None:
        """
        数据管理（导出/导入/统计）。

        用法:
          data                              # 显示数据统计
          data stats                        # 显示数据统计
          data export -o <file>             # 导出经验数据为JSON
          data import <file>                # 导入经验数据
          data import <file> --merge        # 合并导入（不清空）

        选项:
          -o, --output <path>   输出文件路径（export）
          --db <path>           数据库路径
          --limit <N>           导出条数限制（export）
          --merge               合并模式（import）
        """
        from agent_core.data_cli import handle_data
        from agent_core.cli import _build_parser

        parser = _build_parser()
        try:
            args = parser.parse_args(["data"] + arg.split())
        except SystemExit:
            return

        result = handle_data(args)
        if result != 0:
            print(_c(f"Command failed (exit code: {result})", _COLOR_RED))

    def do_wizard(self, arg: str) -> None:
        """
        交互式配置向导（U-12）。

        用法:
          wizard                    # 交互式向导
          wizard --yes              # 非交互模式（全部默认值）
          wizard <directory>        # 指定项目目录
        """
        from agent_core.wizard_cli import handle_wizard
        from agent_core.cli import _build_parser

        parser = _build_parser()
        try:
            args = parser.parse_args(["wizard"] + arg.split())
        except SystemExit:
            return

        result = handle_wizard(args)
        if result != 0:
            print(_c(f"Command failed (exit code: {result})", _COLOR_RED))

    def do_alias(self, arg: str) -> None:
        """
        命令别名管理（U-13）。

        用法:
          alias                    # 列出所有别名
          alias list               # 列出所有别名
          alias add <name> <cmd>   # 添加别名
          alias remove <name>      # 删除别名
          alias clear              # 清除所有用户别名
        """
        from agent_core.alias_cli import handle_alias
        from agent_core.cli import _build_parser

        parser = _build_parser()
        try:
            args = parser.parse_args(["alias"] + arg.split())
        except SystemExit:
            return

        result = handle_alias(args)
        if result != 0:
            print(_c(f"Command failed (exit code: {result})", _COLOR_RED))

    def do_overview(self, arg: str) -> None:
        """
        系统概览（U-14）。

        用法:
          overview                    # 文本格式概览
          overview --format json      # JSON格式
          overview --env prod         # 指定环境
        """
        from agent_core.overview_cli import handle_overview
        from agent_core.cli import _build_parser

        parser = _build_parser()
        try:
            args = parser.parse_args(["overview"] + arg.split())
        except SystemExit:
            return

        result = handle_overview(args)
        if result != 0:
            print(_c(f"Command failed (exit code: {result})", _COLOR_RED))

    def do_template(self, arg: str) -> None:
        """
        配置模板管理（U-17）。

        用法:
          template                    # 列出所有模板
          template list               # 列出所有模板
          template show <name>        # 查看模板详情
          template apply <name>       # 应用模板生成配置
          template apply <name> --env prod  # 指定环境
          template save <name> <file> # 保存配置为模板
          template delete <name>      # 删除用户模板
        """
        from agent_core.template_cli import handle_template
        from agent_core.cli import _build_parser

        parser = _build_parser()
        try:
            args = parser.parse_args(["template"] + arg.split())
        except SystemExit:
            return

        result = handle_template(args)
        if result != 0:
            print(_c(f"Command failed (exit code: {result})", _COLOR_RED))

    def do_exit(self, arg: str) -> bool:
        """
        退出Shell。

        用法: exit
        """
        print(_c("Goodbye!", _COLOR_CYAN))
        return True

    def do_quit(self, arg: str) -> bool:
        """退出Shell（同exit）。"""
        return self.do_exit(arg)

    def do_EOF(self, arg: str) -> bool:
        """Ctrl+D退出。"""
        print()
        return self.do_exit(arg)

    def do_help(self, arg: str) -> None:
        """显示帮助。"""
        if arg:
            super().do_help(arg)
        else:
            print(_c("=== Available Commands ===", _COLOR_BOLD))
            print()
            print(_c("Status:", _COLOR_CYAN))
            print("  status    - Show agent running status")
            print("  health    - Quick health check")
            print("  metrics   - Show Prometheus metrics")
            print("  errors    - Show recent errors")
            print("  profile   - Show performance profile")
            print()
            print(_c("Config:", _COLOR_CYAN))
            print("  config    - View/modify configuration")
            print()
            print(_c("Logs:", _COLOR_CYAN))
            print("  logs      - View/analyze/search logs")
            print()
            print(_c("Plugins:", _COLOR_CYAN))
            print("  plugin    - List/load/validate plugins")
            print()
            print(_c("Log Rotation:", _COLOR_CYAN))
            print("  log-rotate - Manage log rotation")
            print()
            print(_c("Config:", _COLOR_CYAN))
            print("  config-diff - Compare/show/validate config")
            print("  wizard    - Interactive onboarding wizard")
            print("  template  - Manage config templates")
            print()
            print(_c("Data:", _COLOR_CYAN))
            print("  data      - Export/import/stats data")
            print()
            print(_c("System:", _COLOR_CYAN))
            print("  port      - Set dashboard port")
            print("  history   - Show command history")
            print("  alias     - Manage command aliases")
            print("  overview  - System overview")
            print("  exit      - Quit shell")
            print()
            print(_c("Type 'help <command>' for detailed help.", _COLOR_YELLOW))

    def precmd(self, line: str) -> str:
        """命令预处理：记录历史。"""
        if line.strip() and not line.startswith("history"):
            self._record_history(line.strip())
        return line

    def emptyline(self) -> None:
        """空行不重复上一条命令。"""
        pass

    def default(self, line: str) -> None:
        """
        未知命令处理：提供建议（U-11）。

        当用户输入的命令没有对应的do_方法时，
        基于相似度建议最接近的命令。
        """
        from agent_core.help_cli import suggest_command, format_suggestions

        # 提取命令名（第一个词）
        cmd_name = line.strip().split()[0] if line.strip() else ""

        # Shell可用命令列表
        shell_commands = [
            "status", "metrics", "health", "config", "profile",
            "errors", "port", "history", "logs", "plugin",
            "log-rotate", "config-diff", "data", "wizard", "alias",
            "overview", "template", "exit", "quit", "help",
        ]

        print(_c(f"[ERROR] Unknown command: {cmd_name}", _COLOR_RED))

        suggestions = suggest_command(cmd_name, shell_commands)
        suggestion_text = format_suggestions(suggestions)
        if suggestion_text:
            print(f"  {suggestion_text}")
        print(_c("  Type 'help' to see all available commands.", _COLOR_YELLOW))

    def _complete_command(self, text: str, commands: List[str]) -> List[str]:
        """命令补全辅助。"""
        if not text:
            return commands
        return [cmd for cmd in commands if cmd.startswith(text)]

    def complete_config(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        """config命令补全。"""
        config_keys = [
            "app_name", "log_level", "online_interval_seconds",
            "offline_interval_seconds", "memory_capacity",
            "exploration_rate", "epsilon", "interrupt_threshold",
        ]
        return self._complete_command(text, config_keys)


def run_shell(
    port: int = _DEFAULT_PORT,
    config: Optional[Dict[str, Any]] = None,
    script: Optional[str] = None,
) -> int:
    """
    运行交互式Shell。

    Args:
        port: Dashboard端口。
        config: 配置字典。
        script: 脚本文件路径（批量执行命令）。

    Returns:
        退出码。
    """
    shell = AgentShell(port=port, config=config)

    if script:
        # 脚本模式：从文件读取命令批量执行
        if not os.path.exists(script):
            print(_c(f"Script file not found: {script}", _COLOR_RED))
            return 1
        try:
            with open(script, "r", encoding="utf-8") as f:
                commands = f.readlines()
            for cmd_line in commands:
                cmd_line = cmd_line.strip()
                if cmd_line and not cmd_line.startswith("#"):
                    print(f"{_c('agent>', _COLOR_GREEN)} {cmd_line}")
                    shell.onecmd(cmd_line)
        except OSError as exc:
            print(_c(f"Failed to read script: {exc}", _COLOR_RED))
            return 1
        return 0

    # 交互模式
    try:
        shell.cmdloop()
    except KeyboardInterrupt:
        print(_c("\nGoodbye!", _COLOR_CYAN))
    return 0
