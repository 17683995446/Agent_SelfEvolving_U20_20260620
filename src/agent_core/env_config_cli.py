"""
环境变量集成与配置优先级。

第一性原理：
- 12-Factor App原则：配置应通过环境变量传递
- 环境变量让同一代码在不同环境（dev/prod/test）运行无需修改
- 明确的优先级链避免配置混乱：CLI > 环境变量 > 配置文件 > 默认值
- 配置来源可追溯，便于调试

设计要点：
- EnvConfigManager: 环境变量配置管理器
- 命名规范: AGENT_<KEY>（如AGENT_LOG_LEVEL）
- 类型转换: 自动将字符串转为int/float/bool
- .env文件支持: 简单KEY=VALUE格式
- 优先级链: CLI参数 > 环境变量 > 配置文件 > 默认值
- env CLI: show/list/validate
- 配置来源追踪: 每个值标注来源
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
_COLOR_CYAN = "\033[36m"
_COLOR_BOLD = "\033[1m"
_COLOR_DIM = "\033[2m"
_COLOR_MAGENTA = "\033[35m"

_COLOR_ENABLED = sys.stdout.isatty() if hasattr(sys.stdout, "isatty") else False


def _c(text: str, color: str) -> str:
    """添加颜色。"""
    if not _COLOR_ENABLED:
        return text
    return f"{color}{text}{_COLOR_RESET}"


# 环境变量前缀
_ENV_PREFIX = "AGENT_"

# 配置来源标签
_SOURCE_DEFAULT = "default"
_SOURCE_FILE = "config-file"
_SOURCE_ENV = "env-var"
_SOURCE_CLI = "cli-arg"

# 已知的配置键及其类型
# 格式: config_key -> (env_suffix, type_converter)
_CONFIG_KEY_MAP: Dict[str, Tuple[str, type]] = {
    "app_name": ("APP_NAME", str),
    "app_version": ("APP_VERSION", str),
    "log_level": ("LOG_LEVEL", str),
    "online_interval_seconds": ("ONLINE_INTERVAL_SECONDS", float),
    "offline_interval_seconds": ("OFFLINE_INTERVAL_SECONDS", float),
    "memory_capacity": ("MEMORY_CAPACITY", int),
    "exploration_rate": ("EXPLORATION_RATE", float),
    "epsilon": ("EPSILON", float),
    "interrupt_threshold": ("INTERRUPT_THRESHOLD", float),
    "feature_dimensions": ("FEATURE_DIMENSIONS", int),
    "mid_window_size": ("MID_WINDOW_SIZE", int),
    "high_window_size": ("HIGH_WINDOW_SIZE", int),
    "ensemble_beta": ("ENSEMBLE_BETA", float),
    "cpu_interval_seconds": ("CPU_INTERVAL_SECONDS", float),
    "max_log_lines": ("MAX_LOG_LINES", int),
    "query_page_size": ("QUERY_PAGE_SIZE", int),
    "batch_query_limit": ("BATCH_QUERY_LIMIT", int),
}


def _convert_value(value: str, target_type: type) -> Any:
    """
    将字符串值转换为目标类型。

    Args:
        value: 字符串值。
        target_type: 目标类型（str/int/float/bool）。

    Returns:
        转换后的值。

    Raises:
        ValueError: 转换失败。
    """
    if target_type is str:
        return value
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    if target_type is bool:
        return value.lower() in ("true", "1", "yes", "on")
    return value


def _env_var_name(config_key: str) -> str:
    """
    获取配置键对应的环境变量名。

    Args:
        config_key: 配置键名。

    Returns:
        环境变量名（如AGENT_LOG_LEVEL）。
    """
    if config_key in _CONFIG_KEY_MAP:
        suffix, _ = _CONFIG_KEY_MAP[config_key]
        return f"{_ENV_PREFIX}{suffix}"
    # 通用规则：大写+下划线
    return f"{_ENV_PREFIX}{config_key.upper()}"


class EnvConfigManager:
    """
    环境变量配置管理器。

    管理从环境变量加载配置，并合并到配置优先级链中。
    """

    def __init__(self, env: Optional[Dict[str, str]] = None) -> None:
        """
        初始化。

        Args:
            env: 环境变量字典（None时使用os.environ）。
        """
        self._env = env if env is not None else dict(os.environ)

    def get_env_config(self) -> Dict[str, Any]:
        """
        从环境变量加载配置。

        只加载AGENT_前缀的变量。

        Returns:
            配置字典。
        """
        config: Dict[str, Any] = {}

        for config_key, (suffix, target_type) in _CONFIG_KEY_MAP.items():
            env_name = f"{_ENV_PREFIX}{suffix}"
            if env_name in self._env:
                raw_value = self._env[env_name]
                try:
                    config[config_key] = _convert_value(raw_value, target_type)
                except (ValueError, TypeError):
                    pass  # 转换失败跳过

        return config

    def get_env_var_for_key(self, config_key: str) -> str:
        """获取配置键对应的环境变量名。"""
        return _env_var_name(config_key)

    def is_env_set(self, config_key: str) -> bool:
        """检查配置键对应的环境变量是否已设置。"""
        return _env_var_name(config_key) in self._env

    def get_env_value(self, config_key: str) -> Optional[str]:
        """获取配置键对应的环境变量原始值。"""
        return self._env.get(_env_var_name(config_key))

    def get_all_env_vars(self) -> Dict[str, str]:
        """
        获取所有AGENT_前缀的环境变量。

        Returns:
            环境变量字典（变量名→值）。
        """
        return {
            k: v for k, v in self._env.items()
            if k.startswith(_ENV_PREFIX)
        }

    def validate_env_value(self, config_key: str) -> Tuple[bool, str]:
        """
        验证环境变量值是否有效。

        Args:
            config_key: 配置键名。

        Returns:
            (是否有效, 错误消息)。
        """
        if not self.is_env_set(config_key):
            return True, ""

        if config_key not in _CONFIG_KEY_MAP:
            return True, ""  # 未知键不验证

        _, target_type = _CONFIG_KEY_MAP[config_key]
        env_name = _env_var_name(config_key)
        raw_value = self._env[env_name]

        try:
            _convert_value(raw_value, target_type)
            return True, ""
        except (ValueError, TypeError) as exc:
            return False, f"{env_name}={raw_value} cannot convert to {target_type.__name__}: {exc}"


def load_dotenv(file_path: str = ".env") -> bool:
    """
    加载.env文件到环境变量。

    简单KEY=VALUE格式，支持注释（#）和空行。

    Args:
        file_path: .env文件路径。

    Returns:
        是否成功加载。
    """
    if not os.path.exists(file_path):
        return False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # 去除引号
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                # 只设置未存在的（不覆盖）
                if key not in os.environ:
                    os.environ[key] = value
        return True
    except OSError:
        return False


def merge_config_priority(
    defaults: Dict[str, Any],
    file_config: Dict[str, Any],
    env_config: Dict[str, Any],
    cli_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    按优先级合并配置。

    优先级: CLI参数 > 环境变量 > 配置文件 > 默认值

    Args:
        defaults: 默认配置。
        file_config: 配置文件加载的配置。
        env_config: 环境变量配置。
        cli_config: CLI参数配置。

    Returns:
        合并后的配置。
    """
    merged = dict(defaults)
    merged.update(file_config)
    merged.update(env_config)
    merged.update(cli_config)
    return merged


def get_config_with_sources(
    defaults: Dict[str, Any],
    file_config: Dict[str, Any],
    env_config: Dict[str, Any],
    cli_config: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    """
    获取配置及其来源。

    Args:
        defaults: 默认配置。
        file_config: 配置文件配置。
        env_config: 环境变量配置。
        cli_config: CLI参数配置。

    Returns:
        {key: {"value": value, "source": source}} 字典。
    """
    result: Dict[str, Dict[str, Any]] = {}

    # 收集所有键
    all_keys = set(defaults.keys()) | set(file_config.keys()) | \
               set(env_config.keys()) | set(cli_config.keys())

    for key in all_keys:
        if key in cli_config:
            result[key] = {"value": cli_config[key], "source": _SOURCE_CLI}
        elif key in env_config:
            result[key] = {"value": env_config[key], "source": _SOURCE_ENV}
        elif key in file_config:
            result[key] = {"value": file_config[key], "source": _SOURCE_FILE}
        elif key in defaults:
            result[key] = {"value": defaults[key], "source": _SOURCE_DEFAULT}
        else:
            result[key] = {"value": None, "source": "unknown"}

    return result


def cmd_env_show(args: argparse.Namespace) -> int:
    """显示环境变量配置。"""
    manager = EnvConfigManager()

    env_config = manager.get_env_config()
    all_env_vars = manager.get_all_env_vars()

    print(_c("=== Environment Variable Configuration ===", _COLOR_BOLD))
    print()

    if not all_env_vars:
        print(_c("No AGENT_* environment variables set.", _COLOR_DIM))
        print()
        print(_c("Tip: Set variables like:", _COLOR_CYAN))
        print(f"  export AGENT_LOG_LEVEL=DEBUG")
        print(f"  export AGENT_MEMORY_CAPACITY=50000")
        return 0

    # 显示已知配置键
    print(_c("Recognized config:", _COLOR_CYAN))
    for key in sorted(env_config.keys()):
        env_name = manager.get_env_var_for_key(key)
        value = env_config[key]
        print(f"  {_c(env_name, _COLOR_GREEN):<40} → {key} = {value}")
    print()

    # 显示其他AGENT_变量
    known_env_names = {manager.get_env_var_for_key(k) for k in _CONFIG_KEY_MAP}
    other_vars = {
        k: v for k, v in all_env_vars.items()
        if k not in known_env_names
    }
    if other_vars:
        print(_c("Other AGENT_* variables:", _COLOR_CYAN))
        for name in sorted(other_vars.keys()):
            print(f"  {_c(name, _COLOR_YELLOW):<40} = {other_vars[name]}")
    print()

    print(_c("Priority: CLI args > Env vars > Config file > Defaults", _COLOR_DIM))
    return 0


def cmd_env_list(args: argparse.Namespace) -> int:
    """列出所有支持的配置键和环境变量名。"""
    print(_c("=== Supported Environment Variables ===", _COLOR_BOLD))
    print()
    print(f"  {_c('Config Key', _COLOR_CYAN):<30} {_c('Env Var', _COLOR_CYAN):<40} {_c('Type', _COLOR_CYAN)}")
    print(f"  {'-'*30} {'-'*40} {'-'*10}")

    for key in sorted(_CONFIG_KEY_MAP.keys()):
        suffix, target_type = _CONFIG_KEY_MAP[key]
        env_name = f"{_ENV_PREFIX}{suffix}"
        print(f"  {key:<30} {_c(env_name, _COLOR_GREEN):<40} {target_type.__name__}")

    print()
    print(_c(f"Prefix: {_ENV_PREFIX}", _COLOR_DIM))
    print(_c("Priority: CLI args > Env vars > Config file > Defaults", _COLOR_DIM))
    return 0


def cmd_env_validate(args: argparse.Namespace) -> int:
    """验证环境变量配置。"""
    manager = EnvConfigManager()
    all_env_vars = manager.get_all_env_vars()

    if not all_env_vars:
        print(_c("No AGENT_* environment variables set to validate.", _COLOR_YELLOW))
        return 0

    print(_c("=== Environment Variable Validation ===", _COLOR_BOLD))
    print()

    all_valid = True
    for key in sorted(_CONFIG_KEY_MAP.keys()):
        if not manager.is_env_set(key):
            continue

        valid, msg = manager.validate_env_value(key)
        env_name = manager.get_env_var_for_key(key)
        raw_value = manager.get_env_value(key)

        if valid:
            print(f"  {_c('[OK]', _COLOR_GREEN)} {env_name} = {raw_value}")
        else:
            print(f"  {_c('[FAIL]', _COLOR_RED)} {env_name} = {raw_value}")
            print(f"       {msg}")
            all_valid = False

    print()
    if all_valid:
        print(_c("All environment variables are valid.", _COLOR_GREEN))
        return 0
    else:
        print(_c("Some environment variables are invalid.", _COLOR_RED))
        return 1


def handle_env(args: argparse.Namespace) -> int:
    """
    处理env命令。

    Args:
        args: 命令行参数。

    Returns:
        退出码。
    """
    action = getattr(args, "env_action", None)

    if action is None or action == "show":
        return cmd_env_show(args)
    elif action == "list":
        return cmd_env_list(args)
    elif action == "validate":
        return cmd_env_validate(args)
    else:
        print(_c(f"[ERROR] Unknown env action: {action}", _COLOR_RED))
        return 1


def add_env_subparser(subparsers: argparse._SubParsersAction) -> None:
    """
    注册env子命令。

    Args:
        subparsers: argparse子命令解析器。
    """
    env_parser = subparsers.add_parser(
        "env",
        help="环境变量配置管理（show/list/validate）",
        description="管理AGENT_*环境变量配置，支持优先级链和验证。",
    )
    env_sub = env_parser.add_subparsers(dest="env_action")

    # env show（默认）
    env_sub.add_parser("show", help="显示当前环境变量配置")

    # env list
    env_sub.add_parser("list", help="列出所有支持的环境变量")

    # env validate
    env_sub.add_parser("validate", help="验证环境变量配置")
