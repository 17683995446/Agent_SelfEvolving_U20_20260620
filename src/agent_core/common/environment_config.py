"""
环境感知配置管理模块。

支持按环境加载配置，并支持配置热更新。

第一性原理：
- 配置与环境解耦，同一套代码运行在不同环境
- 配置变更必须可观测、可回滚
- 默认值保证系统在任何环境下可启动
"""

import os
from typing import Any, Dict, Optional

from agent_core.common.logger import get_logger


class EnvironmentConfig:
    """
    环境感知配置管理器。

    根据AGENT_ENV环境变量加载对应配置文件。
    """

    def __init__(self, config_dir: str = "config") -> None:
        self._config_dir = config_dir
        self._env = os.environ.get("AGENT_ENV", "dev")
        self._config: Dict[str, Any] = {}
        self._logger = get_logger()
        self._load()

    def _load(self) -> None:
        """加载配置文件。"""
        base_path = os.path.join(self._config_dir, "base.yaml")
        env_path = os.path.join(self._config_dir, f"{self._env}.yaml")
        self._config = self._load_file(base_path) or {}
        env_config = self._load_file(env_path)
        if env_config is not None:
            self._deep_merge(self._config, env_config)
        self._logger.info(f"[EnvConfig] Loaded {self._env} config")

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """深度合并两个字典。"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _load_file(self, path: str) -> Optional[Dict[str, Any]]:
        """加载单个配置文件。"""
        if not os.path.exists(path):
            return None
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except ImportError:
            self._logger.warning("[EnvConfig] yaml not available")
            return None
        except OSError as exc:
            self._logger.error(f"[EnvConfig] Failed to load {path}: {exc}")
            return None

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项。

        Args:
            key: 配置键，支持点号分隔嵌套。
            default: 默认值。

        Returns:
            配置值或默认值。
        """
        keys = key.split(".")
        value: Any = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def reload(self) -> bool:
        """
        热重载配置。

        Returns:
            成功返回True。
        """
        try:
            self._load()
            return True
        except Exception as exc:
            self._logger.error(f"[EnvConfig] Reload failed: {exc}")
            return False

    @property
    def environment(self) -> str:
        """当前环境名称。"""
        return self._env

    @property
    def all_config(self) -> Dict[str, Any]:
        """获取完整配置副本。"""
        return dict(self._config)
