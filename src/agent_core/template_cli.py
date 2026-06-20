"""
配置模板与预设管理。

第一性原理：
- 不同场景需要不同配置模板，避免重复配置
- 内置模板覆盖常见场景，用户无需从零开始
- 用户自定义模板让配置可复用、可分享
- 模板是配置的最佳实践沉淀

设计要点：
- BUILTIN_TEMPLATES: 内置模板（minimal/standard/high-performance/debug）
- TemplateManager: 模板管理器
- template CLI: list/apply/save/show/delete
- 模板存储在 .agent_templates/ 目录
- apply时合并到目标配置文件
"""

import argparse
import json
import os
import shutil
import sys
from typing import Any, Dict, List, Optional

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


# 内置模板
BUILTIN_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "minimal": {
        "description": "最小化配置，适合快速测试",
        "config": {
            "app_name": "minimal_agent",
            "app_version": "1.0.0",
            "log_level": "WARNING",
            "online_interval_seconds": 5.0,
            "offline_interval_seconds": 3600.0,
            "memory_capacity": 1000,
            "exploration_rate": 0.1,
            "epsilon": 0.1,
            "interrupt_threshold": 0.8,
        },
    },
    "standard": {
        "description": "标准配置，适合大多数场景",
        "config": {
            "app_name": "standard_agent",
            "app_version": "1.0.0",
            "log_level": "INFO",
            "online_interval_seconds": 1.0,
            "offline_interval_seconds": 3600.0,
            "memory_capacity": 10000,
            "exploration_rate": 0.3,
            "epsilon": 0.2,
            "interrupt_threshold": 0.7,
            "feature_dimensions": 10,
            "mid_window_size": 20,
            "high_window_size": 100,
        },
    },
    "high-performance": {
        "description": "高性能配置，适合生产环境",
        "config": {
            "app_name": "hp_agent",
            "app_version": "1.0.0",
            "log_level": "ERROR",
            "online_interval_seconds": 0.5,
            "offline_interval_seconds": 1800.0,
            "memory_capacity": 100000,
            "exploration_rate": 0.05,
            "epsilon": 0.05,
            "interrupt_threshold": 0.9,
            "feature_dimensions": 20,
            "mid_window_size": 50,
            "high_window_size": 200,
            "ensemble_beta": 10.0,
        },
    },
    "debug": {
        "description": "调试配置，详细日志和快速循环",
        "config": {
            "app_name": "debug_agent",
            "app_version": "1.0.0",
            "log_level": "DEBUG",
            "online_interval_seconds": 2.0,
            "offline_interval_seconds": 300.0,
            "memory_capacity": 500,
            "exploration_rate": 0.5,
            "epsilon": 0.3,
            "interrupt_threshold": 0.5,
        },
    },
}

# 模板存储目录名
_TEMPLATE_DIR = ".agent_templates"


class TemplateManager:
    """
    配置模板管理器。

    管理内置模板和用户自定义模板。
    用户模板存储在 .agent_templates/ 目录。
    """

    def __init__(self, project_dir: Optional[str] = None) -> None:
        """
        初始化模板管理器。

        Args:
            project_dir: 项目目录（None时使用当前目录）。
        """
        self._project_dir = project_dir or os.getcwd()
        self._template_dir = os.path.join(self._project_dir, _TEMPLATE_DIR)

    @property
    def template_dir_path(self) -> str:
        """模板目录路径。"""
        return self._template_dir

    def get_builtin_templates(self) -> Dict[str, Dict[str, Any]]:
        """获取内置模板。"""
        return dict(BUILTIN_TEMPLATES)

    def get_user_templates(self) -> Dict[str, Dict[str, Any]]:
        """获取用户模板。"""
        templates: Dict[str, Dict[str, Any]] = {}
        if not os.path.isdir(self._template_dir):
            return templates

        for fname in os.listdir(self._template_dir):
            if not fname.endswith(".json"):
                continue
            name = fname[:-5]  # 去掉.json
            path = os.path.join(self._template_dir, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                templates[name] = data
            except (json.JSONDecodeError, OSError):
                pass

        return templates

    def get_all_templates(self) -> Dict[str, Dict[str, Any]]:
        """获取所有模板（内置+用户）。"""
        merged = dict(BUILTIN_TEMPLATES)
        merged.update(self.get_user_templates())
        return merged

    def get_template(self, name: str) -> Optional[Dict[str, Any]]:
        """
        获取指定模板。

        Args:
            name: 模板名。

        Returns:
            模板数据，不存在返回None。
        """
        all_templates = self.get_all_templates()
        return all_templates.get(name)

    def is_builtin(self, name: str) -> bool:
        """是否是内置模板。"""
        return name in BUILTIN_TEMPLATES

    def save_template(
        self,
        name: str,
        config: Dict[str, Any],
        description: str = "",
    ) -> bool:
        """
        保存用户模板。

        Args:
            name: 模板名。
            config: 配置字典。
            description: 描述。

        Returns:
            是否成功保存。
        """
        if not name or not config:
            return False

        if self.is_builtin(name):
            return False  # 不能覆盖内置模板

        os.makedirs(self._template_dir, exist_ok=True)

        template_data = {
            "description": description or f"User template: {name}",
            "config": config,
        }

        path = os.path.join(self._template_dir, f"{name}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(template_data, f, indent=2, ensure_ascii=False)
            return True
        except OSError:
            return False

    def delete_template(self, name: str) -> bool:
        """
        删除用户模板。

        Args:
            name: 模板名。

        Returns:
            是否成功删除。
        """
        if self.is_builtin(name):
            return False

        path = os.path.join(self._template_dir, f"{name}.json")
        if not os.path.exists(path):
            return False

        try:
            os.remove(path)
            return True
        except OSError:
            return False

    def apply_template(
        self,
        name: str,
        output_path: str,
        env: str = "dev",
    ) -> bool:
        """
        应用模板到配置文件。

        Args:
            name: 模板名。
            output_path: 输出配置文件路径。
            env: 环境名（写入注释）。

        Returns:
            是否成功应用。
        """
        template = self.get_template(name)
        if template is None:
            return False

        config = template.get("config", {})

        try:
            import yaml
        except ImportError:
            print(_c("[ERROR] PyYAML not installed.", _COLOR_RED))
            return False

        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"# {env} environment configuration\n")
                f.write(f"# Applied from template: {name}\n")
                f.write(f"# {template.get('description', '')}\n\n")
                yaml.dump(config, f, default_flow_style=False, sort_keys=True)
            return True
        except OSError as exc:
            print(_c(f"[ERROR] Failed to write config: {exc}", _COLOR_RED))
            return False


def cmd_template_list(args: argparse.Namespace) -> int:
    """列出所有模板。"""
    manager = TemplateManager()

    print(_c("=== Configuration Templates ===", _COLOR_BOLD))
    print()

    # 内置模板
    print(_c("Built-in:", _COLOR_CYAN))
    for name, tmpl in sorted(BUILTIN_TEMPLATES.items()):
        desc = tmpl.get("description", "")
        print(f"  {_c(name, _COLOR_GREEN):<20} {desc}")
    print()

    # 用户模板
    user_templates = manager.get_user_templates()
    if user_templates:
        print(_c("User-defined:", _COLOR_CYAN))
        for name, tmpl in sorted(user_templates.items()):
            desc = tmpl.get("description", "")
            print(f"  {_c(name, _COLOR_GREEN):<20} {desc}")
    else:
        print(_c("User-defined: (none)", _COLOR_DIM))
    print()

    print(_c("Tip: Use 'agent template apply <name>' to apply a template.", _COLOR_DIM))
    return 0


def cmd_template_apply(args: argparse.Namespace) -> int:
    """应用模板。"""
    manager = TemplateManager()
    name = args.name
    output = getattr(args, "output", None)
    env = getattr(args, "env", "dev")

    template = manager.get_template(name)
    if template is None:
        print(_c(f"[ERROR] Template not found: {name}", _COLOR_RED))
        return 1

    if output is None:
        output = os.path.join("config", f"{env}.yaml")

    if manager.apply_template(name, output, env):
        print(_c(f"[OK] Template '{name}' applied to {output}", _COLOR_GREEN))
        print(_c(f"     Description: {template.get('description', '')}", _COLOR_DIM))
        return 0
    else:
        print(_c(f"[ERROR] Failed to apply template: {name}", _COLOR_RED))
        return 1


def cmd_template_save(args: argparse.Namespace) -> int:
    """保存当前配置为模板。"""
    manager = TemplateManager()
    name = args.name
    config_path = args.config_file
    description = getattr(args, "description", "")

    if manager.is_builtin(name):
        print(_c(f"[ERROR] Cannot overwrite built-in template: {name}", _COLOR_RED))
        return 1

    # 加载配置文件
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    except ImportError:
        print(_c("[ERROR] PyYAML not installed.", _COLOR_RED))
        return 1
    except OSError as exc:
        print(_c(f"[ERROR] Failed to read config: {exc}", _COLOR_RED))
        return 1

    if manager.save_template(name, config, description):
        print(_c(f"[OK] Template saved: {name}", _COLOR_GREEN))
        return 0
    else:
        print(_c(f"[ERROR] Failed to save template", _COLOR_RED))
        return 1


def cmd_template_show(args: argparse.Namespace) -> int:
    """显示模板详情。"""
    manager = TemplateManager()
    name = args.name

    template = manager.get_template(name)
    if template is None:
        print(_c(f"[ERROR] Template not found: {name}", _COLOR_RED))
        return 1

    print(_c(f"=== Template: {name} ===", _COLOR_BOLD))
    print()
    is_builtin = manager.is_builtin(name)
    source = "Built-in" if is_builtin else "User-defined"
    print(f"  {_c('Source:', _COLOR_CYAN)}      {source}")
    print(f"  {_c('Description:', _COLOR_CYAN)} {template.get('description', '')}")
    print()
    print(_c("Configuration:", _COLOR_CYAN))
    config = template.get("config", {})
    for key in sorted(config.keys()):
        print(f"  {key}: {config[key]}")

    return 0


def cmd_template_delete(args: argparse.Namespace) -> int:
    """删除用户模板。"""
    manager = TemplateManager()
    name = args.name

    if manager.is_builtin(name):
        print(_c(f"[ERROR] Cannot delete built-in template: {name}", _COLOR_RED))
        return 1

    if manager.delete_template(name):
        print(_c(f"[OK] Template deleted: {name}", _COLOR_GREEN))
        return 0
    else:
        print(_c(f"[ERROR] Template not found or cannot delete: {name}", _COLOR_RED))
        return 1


def handle_template(args: argparse.Namespace) -> int:
    """
    处理template命令。

    Args:
        args: 命令行参数。

    Returns:
        退出码。
    """
    action = getattr(args, "template_action", None)

    if action is None or action == "list":
        return cmd_template_list(args)
    elif action == "apply":
        return cmd_template_apply(args)
    elif action == "save":
        return cmd_template_save(args)
    elif action == "show":
        return cmd_template_show(args)
    elif action == "delete":
        return cmd_template_delete(args)
    else:
        print(_c(f"[ERROR] Unknown template action: {action}", _COLOR_RED))
        return 1


def add_template_subparser(subparsers: argparse._SubParsersAction) -> None:
    """
    注册template子命令。

    Args:
        subparsers: argparse子命令解析器。
    """
    template_parser = subparsers.add_parser(
        "template",
        help="配置模板管理（list/apply/save/show/delete）",
        description="管理配置模板，支持内置和用户自定义模板。",
    )
    template_sub = template_parser.add_subparsers(dest="template_action")

    # template list（默认）
    template_sub.add_parser("list", help="列出所有模板")

    # template apply
    apply_parser = template_sub.add_parser("apply", help="应用模板到配置文件")
    apply_parser.add_argument("name", help="模板名")
    apply_parser.add_argument(
        "--output", "-o",
        default=None,
        help="输出配置文件路径（默认: config/<env>.yaml）",
    )
    apply_parser.add_argument(
        "--env",
        default="dev",
        help="环境名（默认: dev）",
    )

    # template save
    save_parser = template_sub.add_parser("save", help="保存配置为模板")
    save_parser.add_argument("name", help="模板名")
    save_parser.add_argument("config_file", help="配置文件路径")
    save_parser.add_argument(
        "--description", "-d",
        default="",
        help="模板描述",
    )

    # template show
    show_parser = template_sub.add_parser("show", help="显示模板详情")
    show_parser.add_argument("name", help="模板名")

    # template delete
    delete_parser = template_sub.add_parser("delete", help="删除用户模板")
    delete_parser.add_argument("name", help="模板名")
