"""
项目脚手架生成器。

为新项目生成模板配置与启动脚本，降低入门门槛。

第一性原理：
- 模仿学习：生物通过模仿同类行为学习，从模板开始降低入门门槛
- 约定优于配置：合理的默认结构让用户无需从零开始
- 渐进式定制：先生成可运行模板，再按需修改

设计要点：
- agent init 命令生成交互式向导
- 生成配置文件模板(dev/prod/test)
- 生成启动脚本
- 生成示例代码
- 支持非交互模式(--yes跳过确认)
"""

import os
import sys
from typing import Any, Dict, Optional

from agent_core.common.logger import get_logger

# 颜色
_COLOR_RESET = "\033[0m"
_COLOR_GREEN = "\033[32m"
_COLOR_YELLOW = "\033[33m"
_COLOR_CYAN = "\033[36m"
_COLOR_BOLD = "\033[1m"


def _c(text: str, color: str) -> str:
    """添加颜色。"""
    if not sys.stdout.isatty():
        return text
    return f"{color}{text}{_COLOR_RESET}"


# 配置文件模板
_CONFIG_TEMPLATE = """\
# {env}环境配置
# 由 'agent init' 生成，可根据需要修改

app_name: "{app_name}"
app_version: "1.0.0"
log_level: "{log_level}"

# 运行循环间隔（秒）
online_interval_seconds: {online_interval}
offline_interval_seconds: {offline_interval}

# 记忆系统
memory_capacity: {memory_capacity}

# 探索-利用平衡
exploration_rate: {exploration_rate}
epsilon: {epsilon}
interrupt_threshold: {interrupt_threshold}

# 预测器
feature_dimensions: {feature_dimensions}
low_alpha_init: 0.3
low_alpha_min: 0.05
low_alpha_max: 0.8
low_adaptation_rate: 0.1
mid_window_size: 20
mid_forecast_horizon: 5
high_window_size: 100
high_reversion_strength: 0.3
ensemble_beta: 5.0

# 监控
cpu_interval_seconds: 1.0
disk_paths:
  - "/"
log_paths: []
max_log_lines: 100

# 驱力基础权重（和为1.0）
base_weights:
  safety: 0.4
  gain: 0.4
  efficiency: 0.2

# 分页
query_page_size: 20
batch_query_limit: 1000
"""

# 环境特定配置
_ENV_PRESETS: Dict[str, Dict[str, Any]] = {
    "dev": {
        "log_level": "DEBUG",
        "online_interval": "1.0",
        "offline_interval": "3600.0",
        "memory_capacity": "10000",
        "exploration_rate": "0.3",
        "epsilon": "0.2",
        "interrupt_threshold": "0.7",
        "feature_dimensions": "10",
    },
    "prod": {
        "log_level": "INFO",
        "online_interval": "1.0",
        "offline_interval": "7200.0",
        "memory_capacity": "100000",
        "exploration_rate": "0.1",
        "epsilon": "0.1",
        "interrupt_threshold": "0.8",
        "feature_dimensions": "10",
    },
    "test": {
        "log_level": "DEBUG",
        "online_interval": "0.5",
        "offline_interval": "60.0",
        "memory_capacity": "1000",
        "exploration_rate": "0.5",
        "epsilon": "0.3",
        "interrupt_threshold": "0.6",
        "feature_dimensions": "5",
    },
}

# 启动脚本模板
_START_SCRIPT_TEMPLATE = """\
#!/bin/bash
# {app_name} 启动脚本
# 由 'agent init' 生成

set -e

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
PROJECT_ROOT="$(dirname "${{SCRIPT_DIR}}")"

export PYTHONPATH="${{PROJECT_ROOT}}/src:${{PYTHONPATH}}"
export AGENT_ENV={env}

cd "${{PROJECT_ROOT}}"

python3 -m agent_core start --env {env} "$@"
"""

# 示例代码模板
_EXAMPLE_TEMPLATE = '''\
"""
{app_name} 示例代码。

由 'agent init' 生成。
演示如何以编程方式使用Self-Evolving Agent。
"""

import asyncio
from agent_core.memory.agent_main import SelfEvolvingAgent


async def main():
    """主函数。"""
    # 创建Agent实例
    agent = SelfEvolvingAgent()

    # 使用默认配置初始化
    config = {
        "app_name": "{app_name}",
        "log_level": "INFO",
        "online_interval_seconds": 1.0,
        "offline_interval_seconds": 3600.0,
    }

    print("Initializing agent...")
    ok = await agent.initialize(config)
    if not ok:
        print("Initialization failed!")
        return

    print("Agent initialized successfully!")

    # 健康检查
    health = await agent.health_check()
    print(f"Health status: {health.get('status', 'unknown')}")

    # 启动运行（短时间演示）
    print("Starting agent for 5 seconds...")
    await agent.start(1.0, 3600.0)

    await asyncio.sleep(5)

    # 停止
    print("Stopping agent...")
    await agent.stop()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
'''

# README模板
_README_TEMPLATE = """\
# {app_name}

由 Self-Evolving Agent 脚手架生成。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动Agent
bash scripts/start.sh

# 3. 查看状态
python -m agent_core status

# 4. 交互式Shell
python -m agent_core shell
```

## 配置

配置文件位于 `config/` 目录：
- `base.yaml` - 基础配置（所有环境共享）
- `dev.yaml` - 开发环境
- `prod.yaml` - 生产环境
- `test.yaml` - 测试环境

切换环境：
```bash
AGENT_ENV=prod bash scripts/start.sh
```

## 示例

运行示例代码：
```bash
python examples/main.py
```

## 更多信息

- 交互式Shell: `python -m agent_core shell`
- 健康检查: `python -m agent_core health`
- Dashboard: `python -m agent_core dashboard`
"""


class ProjectScaffolder:
    """
    项目脚手架生成器。

    生成配置文件、启动脚本、示例代码。
    """

    def __init__(self) -> None:
        self._logger = get_logger()

    def generate(
        self,
        project_dir: str,
        app_name: str = "my_agent",
        env: str = "dev",
        interactive: bool = True,
    ) -> bool:
        """
        生成项目脚手架。

        Args:
            project_dir: 项目目录。
            app_name: 应用名称。
            env: 默认环境。
            interactive: 是否交互式确认。

        Returns:
            是否成功生成。
        """
        project_dir = os.path.abspath(project_dir)

        # 检查目录
        if os.path.exists(project_dir) and os.listdir(project_dir):
            if interactive:
                print(_c(
                    f"Warning: Directory '{project_dir}' is not empty. "
                    f"Files may be overwritten.",
                    _COLOR_YELLOW,
                ))
                if not self._confirm("Continue?"):
                    print("Aborted.")
                    return False

        # 交互式配置
        if interactive:
            app_name = self._ask("App name", app_name)
            env = self._ask_choice(
                "Environment", ["dev", "prod", "test"], env
            )

        # 创建目录结构
        self._create_dirs(project_dir)

        # 生成文件
        self._generate_configs(project_dir, app_name)
        self._generate_scripts(project_dir, app_name, env)
        self._generate_example(project_dir, app_name)
        self._generate_readme(project_dir, app_name)
        self._generate_requirements(project_dir)

        print(_c(
            f"\n=== Project scaffolded successfully! ===",
            _COLOR_GREEN,
        ))
        print(f"  Location: {project_dir}")
        print(f"  App name: {app_name}")
        print(f"  Environment: {env}")
        print()
        print(_c("Next steps:", _COLOR_BOLD))
        print(f"  1. cd {project_dir}")
        print(f"  2. pip install -r requirements.txt")
        print(f"  3. bash scripts/start.sh")
        print(f"  4. python -m agent_core shell")

        return True

    def _create_dirs(self, project_dir: str) -> None:
        """创建目录结构。"""
        dirs = [
            project_dir,
            os.path.join(project_dir, "config"),
            os.path.join(project_dir, "scripts"),
            os.path.join(project_dir, "examples"),
            os.path.join(project_dir, "logs"),
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

    def _generate_configs(
        self, project_dir: str, app_name: str
    ) -> None:
        """生成配置文件。"""
        config_dir = os.path.join(project_dir, "config")

        # 生成base.yaml
        base_path = os.path.join(config_dir, "base.yaml")
        with open(base_path, "w", encoding="utf-8") as f:
            f.write(_CONFIG_TEMPLATE.format(
                env="base", app_name=app_name, **_ENV_PRESETS["dev"]
            ))

        # 生成各环境配置
        for env, preset in _ENV_PRESETS.items():
            path = os.path.join(config_dir, f"{env}.yaml")
            with open(path, "w", encoding="utf-8") as f:
                f.write(_CONFIG_TEMPLATE.format(
                    env=env, app_name=app_name, **preset
                ))

        print(f"  Generated config files in {config_dir}")

    def _generate_scripts(
        self, project_dir: str, app_name: str, env: str
    ) -> None:
        """生成启动脚本。"""
        scripts_dir = os.path.join(project_dir, "scripts")
        start_path = os.path.join(scripts_dir, "start.sh")
        with open(start_path, "w", encoding="utf-8") as f:
            f.write(_START_SCRIPT_TEMPLATE.format(
                app_name=app_name, env=env
            ))
        os.chmod(start_path, 0o755)

        print(f"  Generated start script: {start_path}")

    def _generate_example(
        self, project_dir: str, app_name: str
    ) -> None:
        """生成示例代码。"""
        examples_dir = os.path.join(project_dir, "examples")
        example_path = os.path.join(examples_dir, "main.py")
        # 使用replace避免format与dict花括号冲突
        content = _EXAMPLE_TEMPLATE.replace("{app_name}", app_name)
        with open(example_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"  Generated example: {example_path}")

    def _generate_readme(
        self, project_dir: str, app_name: str
    ) -> None:
        """生成README。"""
        readme_path = os.path.join(project_dir, "README.md")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(_README_TEMPLATE.format(app_name=app_name))

        print(f"  Generated README: {readme_path}")

    def _generate_requirements(self, project_dir: str) -> None:
        """生成requirements.txt。"""
        req_path = os.path.join(project_dir, "requirements.txt")
        with open(req_path, "w", encoding="utf-8") as f:
            f.write("numpy>=1.24.0\n")
            f.write("psutil>=5.9.0\n")
            f.write("pyyaml>=6.0\n")

        print(f"  Generated requirements.txt: {req_path}")

    def _ask(self, prompt: str, default: str) -> str:
        """交互式提问。"""
        try:
            answer = input(f"{prompt} [{default}]: ").strip()
            return answer if answer else default
        except (EOFError, KeyboardInterrupt):
            return default

    def _ask_choice(
        self, prompt: str, choices: list, default: str
    ) -> str:
        """交互式选择。"""
        choices_str = "/".join(choices)
        try:
            answer = input(
                f"{prompt} ({choices_str}) [{default}]: "
            ).strip().lower()
            return answer if answer in choices else default
        except (EOFError, KeyboardInterrupt):
            return default

    def _confirm(self, prompt: str) -> bool:
        """确认提示。"""
        try:
            answer = input(f"{prompt} [y/N]: ").strip().lower()
            return answer in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False


def scaffold_project(
    project_dir: str,
    app_name: str = "my_agent",
    env: str = "dev",
    interactive: bool = True,
) -> bool:
    """
    便捷函数：生成项目脚手架。

    Args:
        project_dir: 项目目录。
        app_name: 应用名称。
        env: 默认环境。
        interactive: 是否交互式确认。

    Returns:
        是否成功生成。
    """
    scaffolder = ProjectScaffolder()
    return scaffolder.generate(
        project_dir=project_dir,
        app_name=app_name,
        env=env,
        interactive=interactive,
    )
