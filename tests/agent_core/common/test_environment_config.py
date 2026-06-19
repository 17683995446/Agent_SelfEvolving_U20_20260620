"""
环境感知配置管理模块测试。

覆盖：默认环境、嵌套获取、默认值、热重载、环境变量切换。
"""

import os
import tempfile

import pytest

from agent_core.common.environment_config import EnvironmentConfig


class TestEnvironmentConfig:
    """EnvironmentConfig测试类。"""

    @pytest.fixture
    def config_dir(self):
        """创建临时配置目录。"""
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, "base.yaml")
            with open(base, "w") as f:
                f.write("app:\n  name: base\n  port: 8080\n")
            prod = os.path.join(d, "prod.yaml")
            with open(prod, "w") as f:
                f.write("app:\n  port: 443\n")
            yield d

    def test_default_environment(self, monkeypatch):
        """测试默认环境为dev。"""
        monkeypatch.delenv("AGENT_ENV", raising=False)
        cfg = EnvironmentConfig("/nonexistent")
        assert cfg.environment == "dev"

    def test_get_nested(self, config_dir):
        """测试嵌套配置获取。"""
        cfg = EnvironmentConfig(config_dir)
        assert cfg.get("app.name") == "base"
        assert cfg.get("app.port") == 8080

    def test_get_default(self, config_dir):
        """测试默认值。"""
        cfg = EnvironmentConfig(config_dir)
        assert cfg.get("missing.key", "fallback") == "fallback"

    def test_env_override(self, config_dir, monkeypatch):
        """测试环境配置覆盖基础配置。"""
        monkeypatch.setenv("AGENT_ENV", "prod")
        cfg = EnvironmentConfig(config_dir)
        assert cfg.get("app.port") == 443
        assert cfg.get("app.name") == "base"

    def test_reload(self, config_dir):
        """测试热重载。"""
        cfg = EnvironmentConfig(config_dir)
        assert cfg.get("app.port") == 8080
        prod = os.path.join(config_dir, "dev.yaml")
        with open(prod, "w") as f:
            f.write("app:\n  port: 9090\n")
        result = cfg.reload()
        assert result is True
        assert cfg.get("app.port") == 9090

    def test_all_config(self, config_dir):
        """测试获取完整配置。"""
        cfg = EnvironmentConfig(config_dir)
        all_cfg = cfg.all_config
        assert all_cfg["app"]["name"] == "base"
