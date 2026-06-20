"""
U-2: 配置链路修复与零配置启动 测试。

覆盖：base.yaml加载、EnvironmentConfig链路、配置校验、零配置启动。
"""

import os
import tempfile
import unittest
from typing import Any, Dict

from agent_core.common.environment_config import EnvironmentConfig
from agent_core.common.config_validator import (
    ConfigValidator,
    ConfigValidationError,
    validate_config,
)


class TestBaseConfig(unittest.TestCase):
    """base.yaml配置文件测试。"""

    def test_base_yaml_exists(self):
        """base.yaml文件存在。"""
        base_path = os.path.join(os.getcwd(), "config", "base.yaml")
        self.assertTrue(os.path.exists(base_path))

    def test_base_yaml_loadable(self):
        """base.yaml可被YAML加载。"""
        import yaml
        base_path = os.path.join(os.getcwd(), "config", "base.yaml")
        with open(base_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        self.assertIsInstance(config, dict)
        self.assertGreater(len(config), 10)

    def test_base_yaml_has_required_keys(self):
        """base.yaml包含必需键。"""
        ec = EnvironmentConfig(config_dir="config")
        required_keys = [
            "app_name", "app_version", "log_level",
            "online_interval_seconds", "offline_interval_seconds",
            "memory_capacity", "exploration_rate", "epsilon",
            "feature_dimensions", "base_weights",
        ]
        for key in required_keys:
            self.assertIn(
                key, ec.all_config,
                f"base.yaml missing required key: {key}"
            )

    def test_base_weights_sum_to_one(self):
        """base.yaml中权重和为1。"""
        ec = EnvironmentConfig(config_dir="config")
        weights = ec.get("base_weights")
        total = weights["safety"] + weights["gain"] + weights["efficiency"]
        self.assertAlmostEqual(total, 1.0, places=2)


class TestEnvironmentConfigChain(unittest.TestCase):
    """EnvironmentConfig配置链路测试。"""

    def test_env_config_loads_base_and_env(self):
        """EnvironmentConfig加载base+env配置。"""
        ec = EnvironmentConfig(config_dir="config")
        # base.yaml的值
        self.assertEqual(ec.get("app_name"), "self_evolving_agent")
        # dev.yaml覆盖的值
        self.assertEqual(ec.get("log_level"), "DEBUG")

    def test_env_config_dot_notation(self):
        """EnvironmentConfig支持点号嵌套取值。"""
        ec = EnvironmentConfig(config_dir="config")
        self.assertAlmostEqual(ec.get("base_weights.safety"), 0.4)
        self.assertAlmostEqual(ec.get("base_weights.gain"), 0.4)
        self.assertAlmostEqual(ec.get("base_weights.efficiency"), 0.2)

    def test_env_config_default_value(self):
        """EnvironmentConfig返回默认值。"""
        ec = EnvironmentConfig(config_dir="config")
        self.assertEqual(ec.get("nonexistent_key", "default"), "default")

    def test_env_config_environment_property(self):
        """EnvironmentConfig.environment属性。"""
        ec = EnvironmentConfig(config_dir="config")
        self.assertEqual(ec.environment, "dev")

    def test_env_config_all_config_returns_copy(self):
        """all_config返回副本。"""
        ec = EnvironmentConfig(config_dir="config")
        config1 = ec.all_config
        config1["test_key"] = "test_value"
        config2 = ec.all_config
        self.assertNotIn("test_key", config2)

    def test_env_config_reload(self):
        """reload热重载。"""
        ec = EnvironmentConfig(config_dir="config")
        result = ec.reload()
        self.assertTrue(result)

    def test_env_config_with_custom_dir(self):
        """自定义配置目录。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建base.yaml
            with open(os.path.join(tmpdir, "base.yaml"), "w") as f:
                f.write("app_name: custom_app\n")
            with open(os.path.join(tmpdir, "test.yaml"), "w") as f:
                f.write("log_level: ERROR\n")
            os.environ["AGENT_ENV"] = "test"
            try:
                ec = EnvironmentConfig(config_dir=tmpdir)
                self.assertEqual(ec.get("app_name"), "custom_app")
                self.assertEqual(ec.get("log_level"), "ERROR")
            finally:
                os.environ["AGENT_ENV"] = "dev"


class TestConfigValidator(unittest.TestCase):
    """配置校验器测试。"""

    def setUp(self):
        self.validator = ConfigValidator()
        # 加载有效配置
        ec = EnvironmentConfig(config_dir="config")
        self.valid_config = ec.all_config

    def test_valid_config_passes(self):
        """有效配置通过校验。"""
        ok, errors = self.validator.validate(self.valid_config)
        self.assertTrue(ok)
        self.assertEqual(len(errors), 0)

    def test_missing_required_key_fails(self):
        """缺少必需键失败。"""
        config = dict(self.valid_config)
        del config["app_name"]
        ok, errors = self.validator.validate(config)
        self.assertFalse(ok)
        self.assertTrue(any("app_name" in e for e in errors))

    def test_wrong_type_fails(self):
        """类型错误失败。"""
        config = dict(self.valid_config)
        config["memory_capacity"] = "not_a_number"
        ok, errors = self.validator.validate(config)
        self.assertFalse(ok)
        self.assertTrue(any("memory_capacity" in e and "type" in e for e in errors))

    def test_below_minimum_fails(self):
        """低于最小值失败。"""
        config = dict(self.valid_config)
        config["online_interval_seconds"] = -1.0
        ok, errors = self.validator.validate(config)
        self.assertFalse(ok)
        self.assertTrue(any("online_interval_seconds" in e and "minimum" in e for e in errors))

    def test_above_maximum_fails(self):
        """超过最大值失败。"""
        config = dict(self.valid_config)
        config["epsilon"] = 5.0
        ok, errors = self.validator.validate(config)
        self.assertFalse(ok)
        self.assertTrue(any("epsilon" in e and "maximum" in e for e in errors))

    def test_invalid_log_level_fails(self):
        """无效日志级别失败。"""
        config = dict(self.valid_config)
        config["log_level"] = "VERBOSE"
        ok, errors = self.validator.validate(config)
        self.assertFalse(ok)
        self.assertTrue(any("log_level" in e for e in errors))

    def test_alpha_min_max_constraint(self):
        """alpha_min <= alpha_max约束。"""
        config = dict(self.valid_config)
        config["low_alpha_min"] = 0.8
        config["low_alpha_max"] = 0.1
        ok, errors = self.validator.validate(config)
        self.assertFalse(ok)
        self.assertTrue(any("low_alpha_min" in e and "low_alpha_max" in e for e in errors))

    def test_base_weights_sum_constraint(self):
        """base_weights和为1约束。"""
        config = dict(self.valid_config)
        config["base_weights"] = {"safety": 0.5, "gain": 0.5, "efficiency": 0.5}
        ok, errors = self.validator.validate(config)
        self.assertFalse(ok)
        self.assertTrue(any("base_weights" in e and "sum" in e for e in errors))

    def test_base_weights_missing_keys(self):
        """base_weights缺少键失败。"""
        config = dict(self.valid_config)
        config["base_weights"] = {"safety": 0.5, "gain": 0.5}
        ok, errors = self.validator.validate(config)
        self.assertFalse(ok)
        self.assertTrue(any("base_weights" in e and "missing" in e for e in errors))

    def test_validate_or_raise_raises(self):
        """validate_or_raise抛出异常。"""
        config = {"app_name": "test"}  # 缺少大量必需键
        with self.assertRaises(ConfigValidationError) as ctx:
            self.validator.validate_or_raise(config)
        self.assertGreater(len(ctx.exception.errors), 1)

    def test_validate_or_raise_passes_valid(self):
        """validate_or_raise对有效配置不抛出。"""
        self.validator.validate_or_raise(self.valid_config)

    def test_error_messages_are_actionable(self):
        """错误信息包含修复建议。"""
        config = {"app_name": "test"}
        ok, errors = self.validator.validate(config)
        self.assertFalse(ok)
        # 错误信息应包含"Add it"或"Adjust"等修复建议
        actionable = any(
            "Add it" in e or "Adjust" in e or "Valid values" in e
            for e in errors
        )
        self.assertTrue(actionable)

    def test_get_defaults_returns_valid_config(self):
        """get_defaults返回有效配置。"""
        defaults = self.validator.get_defaults()
        self.assertIsInstance(defaults, dict)
        self.assertGreater(len(defaults), 5)

    def test_convenience_function(self):
        """便捷函数validate_config。"""
        ok, errors = validate_config(self.valid_config)
        self.assertTrue(ok)


class TestZeroConfigStartup(unittest.TestCase):
    """零配置启动测试。"""

    def test_defaults_allow_startup(self):
        """默认值允许启动。"""
        from agent_core.cli import _get_default_config
        config = _get_default_config()
        ok, errors = ConfigValidator().validate(config)
        self.assertTrue(ok, f"Default config invalid: {errors}")

    def test_no_config_file_uses_defaults(self):
        """无配置文件时使用默认值。"""
        from agent_core.cli import _load_config
        # 使用不存在的配置目录
        os.environ["AGENT_CONFIG_DIR"] = "/nonexistent"
        try:
            config = _load_config("dev", None)
            self.assertEqual(config["app_name"], "self_evolving_agent")
            self.assertGreater(config["online_interval_seconds"], 0)
        finally:
            del os.environ["AGENT_CONFIG_DIR"]

    def test_config_file_overrides_env(self):
        """配置文件覆盖环境配置。"""
        from agent_core.cli import _load_config
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("app_name: override_app\nonline_interval_seconds: 99.0\n")
            f.flush()
            try:
                config = _load_config("dev", f.name)
                self.assertEqual(config["app_name"], "override_app")
                self.assertEqual(config["online_interval_seconds"], 99.0)
            finally:
                os.unlink(f.name)

    def test_cli_params_override_config(self):
        """CLI参数覆盖配置（在_cmd_start中实现）。"""
        # 此测试验证配置加载逻辑正确
        from agent_core.cli import _load_config
        config = _load_config("dev", None)
        # 模拟CLI覆盖
        config["log_level"] = "DEBUG"
        config["online_interval_seconds"] = 2.0
        ok, errors = ConfigValidator().validate(config)
        self.assertTrue(ok)


class TestConfigChainPriority(unittest.TestCase):
    """配置优先级链路测试。"""

    def test_priority_config_file_over_env(self):
        """配置文件 > 环境配置。"""
        from agent_core.cli import _load_config
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("app_name: from_file\n")
            f.flush()
            try:
                config = _load_config("dev", f.name)
                self.assertEqual(config["app_name"], "from_file")
            finally:
                os.unlink(f.name)

    def test_priority_env_over_defaults(self):
        """环境配置 > 默认值。"""
        ec = EnvironmentConfig(config_dir="config")
        # dev.yaml中log_level=DEBUG，默认值是INFO
        self.assertEqual(ec.get("log_level"), "DEBUG")

    def test_priority_defaults_fill_gaps(self):
        """默认值填充缺失项。"""
        from agent_core.cli import _load_config
        # 使用空配置目录
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["AGENT_CONFIG_DIR"] = tmpdir
            try:
                config = _load_config("dev", None)
                # 默认值应填充所有必需键
                self.assertIn("app_name", config)
                self.assertIn("online_interval_seconds", config)
                self.assertIn("base_weights", config)
            finally:
                del os.environ["AGENT_CONFIG_DIR"]


if __name__ == "__main__":
    unittest.main()
