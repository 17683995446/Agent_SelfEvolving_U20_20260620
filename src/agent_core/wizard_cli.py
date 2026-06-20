"""
交互式向导（Onboarding Wizard）。

第一性原理：
- 新用户面对空白配置会迷茫，需要引导
- 向导将复杂决策分解为简单步骤，每步只问一个问题
- 合理默认值让用户可直接回车跳过，降低决策负担
- 首次运行检测：主动识别新用户并触发向导

设计要点：
- detect_first_run: 检测首次运行标志（无config/、无.db）
- OnboardingWizard: 多步骤交互式配置生成
- 步骤：欢迎 → 应用信息 → 环境 → 运行参数 → 高级配置（可选） → 确认 → 生成
- 支持非交互模式（--yes跳过，使用全部默认值）
- 生成配置文件并给出下一步指引
"""

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

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


# 首次运行标志文件/目录
_FIRST_RUN_MARKERS = [
    "config",
    "config/base.yaml",
    "agent_memory.db",
    ".agent_initialized",
]


def detect_first_run(project_dir: Optional[str] = None) -> bool:
    """
    检测是否首次运行。

    首次运行定义：当前目录下没有任何已初始化标志。
    标志包括：config/目录、config/base.yaml、agent_memory.db、.agent_initialized

    Args:
        project_dir: 项目目录（None时使用当前目录）。

    Returns:
        True表示首次运行，False表示已初始化。
    """
    base_dir = project_dir or os.getcwd()

    for marker in _FIRST_RUN_MARKERS:
        path = os.path.join(base_dir, marker)
        if os.path.exists(path):
            return False

    return True


def mark_initialized(project_dir: Optional[str] = None) -> None:
    """
    标记已初始化（写入标志文件）。

    Args:
        project_dir: 项目目录（None时使用当前目录）。
    """
    base_dir = project_dir or os.getcwd()
    marker_path = os.path.join(base_dir, ".agent_initialized")
    try:
        with open(marker_path, "w", encoding="utf-8") as f:
            f.write("# Agent initialized marker\n")
    except OSError:
        pass


class OnboardingWizard:
    """
    交互式配置向导。

    通过多步骤问答引导用户生成配置文件。
    每步提供合理默认值，用户可直接回车跳过。
    """

    def __init__(self, interactive: bool = True) -> None:
        """
        初始化向导。

        Args:
            interactive: 是否交互式（False时使用全部默认值）。
        """
        self._interactive = interactive
        self._config: Dict[str, Any] = {}
        self._app_name = "my_agent"
        self._env = "dev"
        self._project_dir = "."

    def run(self, project_dir: str = ".") -> Tuple[bool, Dict[str, Any]]:
        """
        运行向导。

        Args:
            project_dir: 项目目录。

        Returns:
            (成功与否, 生成的配置字典)。
        """
        self._project_dir = os.path.abspath(project_dir)

        self._show_welcome()

        if self._interactive:
            self._step_app_info()
            self._step_environment()
            self._step_runtime_params()
            if self._step_advanced_prompt():
                self._step_advanced_config()
        else:
            self._use_defaults()

        self._build_config()

        if self._interactive:
            if not self._step_confirm():
                print(_c("\nOnboarding cancelled.", _COLOR_YELLOW))
                return False, {}

        # 生成配置文件
        success = self._generate_config()
        if success:
            self._show_next_steps()
            mark_initialized(self._project_dir)

        return success, self._config

    def _show_welcome(self) -> None:
        """显示欢迎信息。"""
        print(_c("=" * 60, _COLOR_CYAN))
        print(_c("  Welcome to Self-Evolving Agent Onboarding Wizard", _COLOR_BOLD))
        print(_c("=" * 60, _COLOR_CYAN))
        print()
        print("This wizard will guide you through initial setup.")
        print("Press Enter at any prompt to accept the default value.")
        print()

    def _step_app_info(self) -> None:
        """步骤1：应用信息。"""
        print(_c("--- Step 1: Application Info ---", _COLOR_BLUE))
        self._app_name = self._ask("Application name", self._app_name)
        print()

    def _step_environment(self) -> None:
        """步骤2：环境选择。"""
        print(_c("--- Step 2: Environment ---", _COLOR_BLUE))
        print("  Choose your deployment environment:")
        print(f"    {_c('dev', _COLOR_GREEN)}  - Development (verbose logging, fast loops)")
        print(f"    {_c('prod', _COLOR_GREEN)} - Production (optimized, stable)")
        print(f"    {_c('test', _COLOR_GREEN)} - Testing (isolated, temporary)")
        self._env = self._ask_choice(
            "Environment", ["dev", "prod", "test"], self._env
        )
        print()

    def _step_runtime_params(self) -> None:
        """步骤3：运行参数。"""
        print(_c("--- Step 3: Runtime Parameters ---", _COLOR_BLUE))

        defaults = self._get_env_defaults(self._env)

        online = self._ask_float(
            "Online loop interval (seconds)",
            defaults["online_interval_seconds"],
        )
        offline = self._ask_float(
            "Offline loop interval (seconds)",
            defaults["offline_interval_seconds"],
        )
        memory = self._ask_int(
            "Memory capacity (max experiences)",
            defaults["memory_capacity"],
        )

        self._config["online_interval_seconds"] = online
        self._config["offline_interval_seconds"] = offline
        self._config["memory_capacity"] = memory
        print()

    def _step_advanced_prompt(self) -> bool:
        """询问是否配置高级选项。"""
        return self._confirm("Configure advanced options? (exploration, epsilon, etc.)")

    def _step_advanced_config(self) -> None:
        """步骤4：高级配置。"""
        print(_c("--- Step 4: Advanced Configuration ---", _COLOR_BLUE))

        defaults = self._get_env_defaults(self._env)

        self._config["exploration_rate"] = self._ask_float(
            "Exploration rate (0-1, higher=more exploration)",
            defaults.get("exploration_rate", 0.3),
        )
        self._config["epsilon"] = self._ask_float(
            "Epsilon (0-1, exploration noise)",
            defaults.get("epsilon", 0.2),
        )
        self._config["interrupt_threshold"] = self._ask_float(
            "Interrupt threshold (0-1, when to interrupt)",
            defaults.get("interrupt_threshold", 0.7),
        )
        self._config["log_level"] = self._ask_choice(
            "Log level",
            ["DEBUG", "INFO", "WARNING", "ERROR"],
            defaults.get("log_level", "INFO"),
        )
        print()

    def _step_confirm(self) -> bool:
        """步骤5：确认。"""
        print(_c("--- Confirmation ---", _COLOR_BLUE))
        print(f"  App name:    {self._app_name}")
        print(f"  Environment: {self._env}")
        for key, val in self._config.items():
            print(f"  {key}: {val}")
        print()
        return self._confirm("Generate configuration with these settings?")

    def _use_defaults(self) -> None:
        """非交互模式：使用全部默认值。"""
        print(_c("Non-interactive mode: using all defaults.", _COLOR_DIM))
        defaults = self._get_env_defaults(self._env)
        self._config.update(defaults)

    def _build_config(self) -> None:
        """构建完整配置字典。"""
        defaults = self._get_env_defaults(self._env)
        # 用户配置覆盖默认值
        for key, val in defaults.items():
            if key not in self._config:
                self._config[key] = val
        self._config["app_name"] = self._app_name
        self._config["app_version"] = "1.0.0"

    def _generate_config(self) -> bool:
        """生成配置文件。"""
        config_dir = os.path.join(self._project_dir, "config")
        os.makedirs(config_dir, exist_ok=True)

        config_path = os.path.join(config_dir, f"{self._env}.yaml")

        try:
            import yaml
        except ImportError:
            print(_c("[ERROR] PyYAML not installed. Install with: pip install pyyaml", _COLOR_RED))
            return False

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(f"# {self._env} environment configuration\n")
                f.write(f"# Generated by 'agent wizard' onboarding wizard\n")
                f.write(f"# App: {self._app_name}\n\n")
                yaml.dump(self._config, f, default_flow_style=False, sort_keys=True)
        except OSError as exc:
            print(_c(f"[ERROR] Failed to write config: {exc}", _COLOR_RED))
            return False

        print(_c(f"\n[OK] Configuration generated: {config_path}", _COLOR_GREEN))
        return True

    def _show_next_steps(self) -> None:
        """显示下一步指引。"""
        print()
        print(_c("--- Next Steps ---", _COLOR_CYAN))
        print(f"  1. Review config: {_c(f'config/{self._env}.yaml', _COLOR_DIM)}")
        print(f"  2. Validate:      {_c('agent config validate', _COLOR_DIM)}")
        print(f"  3. Dry-run:       {_c(f'agent start --env {self._env} --dry-run', _COLOR_DIM)}")
        print(f"  4. Start agent:   {_c(f'agent start --env {self._env}', _COLOR_DIM)}")
        print(f"  5. Interactive:   {_c('agent shell', _COLOR_DIM)}")
        print()
        print(_c("Onboarding complete! Welcome to Self-Evolving Agent.", _COLOR_GREEN))

    def _get_env_defaults(self, env: str) -> Dict[str, Any]:
        """获取环境默认配置。"""
        presets = {
            "dev": {
                "log_level": "DEBUG",
                "online_interval_seconds": 1.0,
                "offline_interval_seconds": 600.0,
                "memory_capacity": 10000,
                "exploration_rate": 0.3,
                "epsilon": 0.2,
                "interrupt_threshold": 0.7,
            },
            "prod": {
                "log_level": "INFO",
                "online_interval_seconds": 5.0,
                "offline_interval_seconds": 3600.0,
                "memory_capacity": 100000,
                "exploration_rate": 0.1,
                "epsilon": 0.05,
                "interrupt_threshold": 0.8,
            },
            "test": {
                "log_level": "DEBUG",
                "online_interval_seconds": 0.5,
                "offline_interval_seconds": 60.0,
                "memory_capacity": 1000,
                "exploration_rate": 0.5,
                "epsilon": 0.3,
                "interrupt_threshold": 0.5,
            },
        }
        return presets.get(env, presets["dev"])

    # --- 输入辅助方法 ---

    def _ask(self, prompt: str, default: str) -> str:
        """文本输入。"""
        try:
            answer = input(f"  {prompt} [{default}]: ").strip()
            return answer if answer else default
        except (EOFError, KeyboardInterrupt):
            return default

    def _ask_choice(
        self, prompt: str, choices: List[str], default: str
    ) -> str:
        """选择输入。"""
        choices_str = "/".join(choices)
        try:
            answer = input(
                f"  {prompt} ({choices_str}) [{default}]: "
            ).strip().lower()
            return answer if answer in choices else default
        except (EOFError, KeyboardInterrupt):
            return default

    def _ask_float(self, prompt: str, default: float) -> float:
        """浮点输入。"""
        try:
            answer = input(f"  {prompt} [{default}]: ").strip()
            if not answer:
                return default
            return float(answer)
        except (ValueError, EOFError, KeyboardInterrupt):
            return default

    def _ask_int(self, prompt: str, default: int) -> int:
        """整数输入。"""
        try:
            answer = input(f"  {prompt} [{default}]: ").strip()
            if not answer:
                return default
            return int(answer)
        except (ValueError, EOFError, KeyboardInterrupt):
            return default

    def _confirm(self, prompt: str) -> bool:
        """确认。"""
        try:
            answer = input(f"  {prompt} [y/N]: ").strip().lower()
            return answer in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False


def cmd_wizard(args: argparse.Namespace) -> int:
    """
    CLI入口：运行向导。

    Args:
        args: 命令行参数。

    Returns:
        退出码。
    """
    interactive = not getattr(args, "yes", False)
    project_dir = getattr(args, "directory", ".")

    wizard = OnboardingWizard(interactive=interactive)
    success, _ = wizard.run(project_dir=project_dir)
    return 0 if success else 1


def handle_wizard(args: argparse.Namespace) -> int:
    """处理wizard命令（同步入口）。"""
    return cmd_wizard(args)


def add_wizard_subparser(subparsers: argparse._SubParsersAction) -> None:
    """
    注册wizard子命令。

    Args:
        subparsers: argparse子命令解析器。
    """
    wizard_parser = subparsers.add_parser(
        "wizard",
        help="交互式配置向导（首次运行引导）",
        description="交互式向导引导生成配置文件，适合首次使用。",
    )
    wizard_parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="项目目录（默认: 当前目录）",
    )
    wizard_parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="非交互模式（使用全部默认值）",
    )
