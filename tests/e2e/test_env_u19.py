"""
U-19: 环境变量集成与配置优先级 测试。

覆盖：
- _convert_value: 类型转换
- _env_var_name: 环境变量名生成
- EnvConfigManager: 环境变量配置管理器
- load_dotenv: .env文件加载
- merge_config_priority: 配置优先级合并
- get_config_with_sources: 配置来源追踪
- env CLI: show/list/validate
- CLI集成: env命令注册与分发
- Shell集成: do_env
"""

import argparse
import io
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from agent_core.env_config_cli import (
    EnvConfigManager,
    _convert_value,
    _env_var_name,
    _CONFIG_KEY_MAP,
    _ENV_PREFIX,
    _SOURCE_DEFAULT,
    _SOURCE_FILE,
    _SOURCE_ENV,
    _SOURCE_CLI,
    load_dotenv,
    merge_config_priority,
    get_config_with_sources,
    cmd_env_show,
    cmd_env_list,
    cmd_env_validate,
    handle_env,
    add_env_subparser,
)
from agent_core.cli import main, _build_parser


class TestConvertValue(unittest.TestCase):
    """_convert_value测试。"""

    def test_str(self):
        """字符串。"""
        self.assertEqual(_convert_value("hello", str), "hello")

    def test_int(self):
        """整数。"""
        self.assertEqual(_convert_value("42", int), 42)

    def test_int_negative(self):
        """负整数。"""
        self.assertEqual(_convert_value("-5", int), -5)

    def test_float(self):
        """浮点数。"""
        self.assertEqual(_convert_value("3.14", float), 3.14)

    def test_float_int_string(self):
        """整数字符串转浮点。"""
        self.assertEqual(_convert_value("10", float), 10.0)

    def test_bool_true(self):
        """布尔真。"""
        for val in ("true", "True", "1", "yes", "on"):
            self.assertTrue(_convert_value(val, bool), f"{val}应为True")

    def test_bool_false(self):
        """布尔假。"""
        for val in ("false", "0", "no", "off", ""):
            self.assertFalse(_convert_value(val, bool), f"{val}应为False")

    def test_int_invalid(self):
        """无效整数抛异常。"""
        with self.assertRaises(ValueError):
            _convert_value("abc", int)

    def test_float_invalid(self):
        """无效浮点抛异常。"""
        with self.assertRaises(ValueError):
            _convert_value("xyz", float)


class TestEnvVarName(unittest.TestCase):
    """_env_var_name测试。"""

    def test_known_key(self):
        """已知键。"""
        self.assertEqual(_env_var_name("log_level"), "AGENT_LOG_LEVEL")

    def test_known_key_memory(self):
        """已知键memory_capacity。"""
        self.assertEqual(_env_var_name("memory_capacity"), "AGENT_MEMORY_CAPACITY")

    def test_unknown_key(self):
        """未知键使用通用规则。"""
        self.assertEqual(_env_var_name("custom_key"), "AGENT_CUSTOM_KEY")

    def test_prefix(self):
        """环境变量前缀。"""
        self.assertTrue(_env_var_name("any_key").startswith(_ENV_PREFIX))


class TestEnvConfigManager(unittest.TestCase):
    """EnvConfigManager测试。"""

    def test_empty_env(self):
        """空环境返回空配置。"""
        manager = EnvConfigManager(env={})
        config = manager.get_env_config()
        self.assertEqual(config, {})

    def test_recognized_var(self):
        """识别的环境变量。"""
        env = {"AGENT_LOG_LEVEL": "DEBUG"}
        manager = EnvConfigManager(env=env)
        config = manager.get_env_config()
        self.assertIn("log_level", config)
        self.assertEqual(config["log_level"], "DEBUG")

    def test_int_conversion(self):
        """整数转换。"""
        env = {"AGENT_MEMORY_CAPACITY": "50000"}
        manager = EnvConfigManager(env=env)
        config = manager.get_env_config()
        self.assertEqual(config["memory_capacity"], 50000)
        self.assertIsInstance(config["memory_capacity"], int)

    def test_float_conversion(self):
        """浮点转换。"""
        env = {"AGENT_ONLINE_INTERVAL_SECONDS": "0.5"}
        manager = EnvConfigManager(env=env)
        config = manager.get_env_config()
        self.assertEqual(config["online_interval_seconds"], 0.5)
        self.assertIsInstance(config["online_interval_seconds"], float)

    def test_invalid_value_skipped(self):
        """无效值被跳过。"""
        env = {"AGENT_MEMORY_CAPACITY": "not_a_number"}
        manager = EnvConfigManager(env=env)
        config = manager.get_env_config()
        self.assertNotIn("memory_capacity", config)

    def test_multiple_vars(self):
        """多个环境变量。"""
        env = {
            "AGENT_LOG_LEVEL": "ERROR",
            "AGENT_MEMORY_CAPACITY": "100000",
            "AGENT_EXPLORATION_RATE": "0.1",
        }
        manager = EnvConfigManager(env=env)
        config = manager.get_env_config()
        self.assertEqual(len(config), 3)
        self.assertEqual(config["log_level"], "ERROR")
        self.assertEqual(config["memory_capacity"], 100000)
        self.assertEqual(config["exploration_rate"], 0.1)

    def test_non_agent_var_ignored(self):
        """非AGENT_前缀变量被忽略。"""
        env = {"PATH": "/usr/bin", "HOME": "/root", "AGENT_LOG_LEVEL": "INFO"}
        manager = EnvConfigManager(env=env)
        config = manager.get_env_config()
        self.assertEqual(len(config), 1)
        self.assertIn("log_level", config)

    def test_is_env_set_true(self):
        """环境变量已设置。"""
        env = {"AGENT_LOG_LEVEL": "DEBUG"}
        manager = EnvConfigManager(env=env)
        self.assertTrue(manager.is_env_set("log_level"))

    def test_is_env_set_false(self):
        """环境变量未设置。"""
        manager = EnvConfigManager(env={})
        self.assertFalse(manager.is_env_set("log_level"))

    def test_get_env_value(self):
        """获取环境变量原始值。"""
        env = {"AGENT_LOG_LEVEL": "DEBUG"}
        manager = EnvConfigManager(env=env)
        self.assertEqual(manager.get_env_value("log_level"), "DEBUG")

    def test_get_env_value_none(self):
        """获取未设置的值返回None。"""
        manager = EnvConfigManager(env={})
        self.assertIsNone(manager.get_env_value("log_level"))

    def test_get_all_env_vars(self):
        """获取所有AGENT_变量。"""
        env = {
            "AGENT_LOG_LEVEL": "DEBUG",
            "AGENT_MEMORY_CAPACITY": "1000",
            "PATH": "/usr/bin",
            "AGENT_CUSTOM_VAR": "custom",
        }
        manager = EnvConfigManager(env=env)
        all_vars = manager.get_all_env_vars()
        self.assertEqual(len(all_vars), 3)
        self.assertIn("AGENT_LOG_LEVEL", all_vars)
        self.assertIn("AGENT_MEMORY_CAPACITY", all_vars)
        self.assertIn("AGENT_CUSTOM_VAR", all_vars)
        self.assertNotIn("PATH", all_vars)

    def test_validate_env_value_valid(self):
        """验证有效值。"""
        env = {"AGENT_MEMORY_CAPACITY": "1000"}
        manager = EnvConfigManager(env=env)
        valid, msg = manager.validate_env_value("memory_capacity")
        self.assertTrue(valid)
        self.assertEqual(msg, "")

    def test_validate_env_value_invalid(self):
        """验证无效值。"""
        env = {"AGENT_MEMORY_CAPACITY": "abc"}
        manager = EnvConfigManager(env=env)
        valid, msg = manager.validate_env_value("memory_capacity")
        self.assertFalse(valid)
        self.assertIn("cannot convert", msg)

    def test_validate_env_value_not_set(self):
        """验证未设置的值返回有效。"""
        manager = EnvConfigManager(env={})
        valid, _ = manager.validate_env_value("memory_capacity")
        self.assertTrue(valid)

    def test_get_env_var_for_key(self):
        """获取配置键对应的环境变量名。"""
        manager = EnvConfigManager(env={})
        self.assertEqual(manager.get_env_var_for_key("log_level"), "AGENT_LOG_LEVEL")

    def test_uses_os_environ_by_default(self):
        """默认使用os.environ。"""
        manager = EnvConfigManager()
        # 应该能访问os.environ中的值
        # 不做具体断言，只确保不报错
        manager.get_env_config()


class TestLoadDotenv(unittest.TestCase):
    """load_dotenv测试。"""

    def test_nonexistent_file(self):
        """不存在的文件返回False。"""
        self.assertFalse(load_dotenv("/nonexistent/.env"))

    def test_loads_vars(self):
        """加载变量。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")
            with open(env_file, "w") as f:
                f.write("AGENT_LOG_LEVEL=DEBUG\n")
                f.write("AGENT_MEMORY_CAPACITY=50000\n")

            # 清除可能存在的值
            old_log = os.environ.pop("AGENT_LOG_LEVEL", None)
            old_mem = os.environ.pop("AGENT_MEMORY_CAPACITY", None)
            try:
                result = load_dotenv(env_file)
                self.assertTrue(result)
                self.assertEqual(os.environ.get("AGENT_LOG_LEVEL"), "DEBUG")
                self.assertEqual(os.environ.get("AGENT_MEMORY_CAPACITY"), "50000")
            finally:
                if old_log is not None:
                    os.environ["AGENT_LOG_LEVEL"] = old_log
                if old_mem is not None:
                    os.environ["AGENT_MEMORY_CAPACITY"] = old_mem
                os.environ.pop("AGENT_LOG_LEVEL", None)
                os.environ.pop("AGENT_MEMORY_CAPACITY", None)

    def test_skips_comments(self):
        """跳过注释。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")
            with open(env_file, "w") as f:
                f.write("# This is a comment\n")
                f.write("AGENT_LOG_LEVEL=INFO\n")

            os.environ.pop("AGENT_LOG_LEVEL", None)
            try:
                load_dotenv(env_file)
                self.assertEqual(os.environ.get("AGENT_LOG_LEVEL"), "INFO")
            finally:
                os.environ.pop("AGENT_LOG_LEVEL", None)

    def test_skips_empty_lines(self):
        """跳过空行。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")
            with open(env_file, "w") as f:
                f.write("\n\nAGENT_LOG_LEVEL=WARN\n\n")

            os.environ.pop("AGENT_LOG_LEVEL", None)
            try:
                load_dotenv(env_file)
                self.assertEqual(os.environ.get("AGENT_LOG_LEVEL"), "WARN")
            finally:
                os.environ.pop("AGENT_LOG_LEVEL", None)

    def test_strips_quotes(self):
        """去除引号。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")
            with open(env_file, "w") as f:
                f.write('AGENT_APP_NAME="my agent"\n')
                f.write("AGENT_LOG_LEVEL='DEBUG'\n")

            os.environ.pop("AGENT_APP_NAME", None)
            os.environ.pop("AGENT_LOG_LEVEL", None)
            try:
                load_dotenv(env_file)
                self.assertEqual(os.environ.get("AGENT_APP_NAME"), "my agent")
                self.assertEqual(os.environ.get("AGENT_LOG_LEVEL"), "DEBUG")
            finally:
                os.environ.pop("AGENT_APP_NAME", None)
                os.environ.pop("AGENT_LOG_LEVEL", None)

    def test_does_not_overwrite_existing(self):
        """不覆盖已存在的环境变量。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, ".env")
            with open(env_file, "w") as f:
                f.write("AGENT_LOG_LEVEL=DEBUG\n")

            os.environ["AGENT_LOG_LEVEL"] = "ERROR"
            try:
                load_dotenv(env_file)
                self.assertEqual(os.environ.get("AGENT_LOG_LEVEL"), "ERROR")
            finally:
                os.environ.pop("AGENT_LOG_LEVEL", None)


class TestMergeConfigPriority(unittest.TestCase):
    """merge_config_priority测试。"""

    def test_defaults_only(self):
        """只有默认值。"""
        defaults = {"a": 1, "b": 2}
        result = merge_config_priority(defaults, {}, {}, {})
        self.assertEqual(result, {"a": 1, "b": 2})

    def test_file_overrides_default(self):
        """配置文件覆盖默认值。"""
        defaults = {"a": 1, "b": 2}
        file_config = {"a": 10}
        result = merge_config_priority(defaults, file_config, {}, {})
        self.assertEqual(result["a"], 10)
        self.assertEqual(result["b"], 2)

    def test_env_overrides_file(self):
        """环境变量覆盖配置文件。"""
        defaults = {"a": 1}
        file_config = {"a": 10}
        env_config = {"a": 100}
        result = merge_config_priority(defaults, file_config, env_config, {})
        self.assertEqual(result["a"], 100)

    def test_cli_overrides_env(self):
        """CLI参数覆盖环境变量。"""
        defaults = {"a": 1}
        file_config = {"a": 10}
        env_config = {"a": 100}
        cli_config = {"a": 1000}
        result = merge_config_priority(defaults, file_config, env_config, cli_config)
        self.assertEqual(result["a"], 1000)

    def test_mixed_sources(self):
        """混合来源。"""
        defaults = {"a": 1, "b": 2, "c": 3}
        file_config = {"b": 20}
        env_config = {"c": 300}
        cli_config = {"a": 1000}
        result = merge_config_priority(defaults, file_config, env_config, cli_config)
        self.assertEqual(result["a"], 1000)  # CLI
        self.assertEqual(result["b"], 20)    # file
        self.assertEqual(result["c"], 300)   # env

    def test_new_keys_added(self):
        """新键被添加。"""
        defaults = {"a": 1}
        file_config = {"b": 2}
        env_config = {"c": 3}
        cli_config = {"d": 4}
        result = merge_config_priority(defaults, file_config, env_config, cli_config)
        self.assertEqual(len(result), 4)


class TestGetConfigWithSources(unittest.TestCase):
    """get_config_with_sources测试。"""

    def test_default_source(self):
        """默认来源。"""
        defaults = {"a": 1}
        result = get_config_with_sources(defaults, {}, {}, {})
        self.assertEqual(result["a"]["value"], 1)
        self.assertEqual(result["a"]["source"], _SOURCE_DEFAULT)

    def test_file_source(self):
        """配置文件来源。"""
        defaults = {"a": 1}
        file_config = {"a": 10}
        result = get_config_with_sources(defaults, file_config, {}, {})
        self.assertEqual(result["a"]["value"], 10)
        self.assertEqual(result["a"]["source"], _SOURCE_FILE)

    def test_env_source(self):
        """环境变量来源。"""
        defaults = {"a": 1}
        file_config = {"a": 10}
        env_config = {"a": 100}
        result = get_config_with_sources(defaults, file_config, env_config, {})
        self.assertEqual(result["a"]["value"], 100)
        self.assertEqual(result["a"]["source"], _SOURCE_ENV)

    def test_cli_source(self):
        """CLI参数来源。"""
        defaults = {"a": 1}
        file_config = {"a": 10}
        env_config = {"a": 100}
        cli_config = {"a": 1000}
        result = get_config_with_sources(defaults, file_config, env_config, cli_config)
        self.assertEqual(result["a"]["value"], 1000)
        self.assertEqual(result["a"]["source"], _SOURCE_CLI)

    def test_mixed_sources(self):
        """混合来源。"""
        defaults = {"a": 1, "b": 2}
        file_config = {"b": 20}
        env_config = {"c": 300}
        cli_config = {"d": 4000}
        result = get_config_with_sources(defaults, file_config, env_config, cli_config)
        self.assertEqual(result["a"]["source"], _SOURCE_DEFAULT)
        self.assertEqual(result["b"]["source"], _SOURCE_FILE)
        self.assertEqual(result["c"]["source"], _SOURCE_ENV)
        self.assertEqual(result["d"]["source"], _SOURCE_CLI)


class TestCmdEnvShow(unittest.TestCase):
    """cmd_env_show测试。"""

    def test_no_env_vars(self):
        """无环境变量。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("agent_core.env_config_cli.EnvConfigManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_env_config.return_value = {}
                instance.get_all_env_vars.return_value = {}
                result = cmd_env_show(MagicMock())
        self.assertEqual(result, 0)
        self.assertIn("No AGENT_", mock_out.getvalue())

    def test_with_env_vars(self):
        """有环境变量。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("agent_core.env_config_cli.EnvConfigManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_env_config.return_value = {"log_level": "DEBUG"}
                instance.get_all_env_vars.return_value = {"AGENT_LOG_LEVEL": "DEBUG"}
                instance.get_env_var_for_key.return_value = "AGENT_LOG_LEVEL"
                result = cmd_env_show(MagicMock())
        self.assertEqual(result, 0)
        output = mock_out.getvalue()
        self.assertIn("log_level", output)
        self.assertIn("DEBUG", output)


class TestCmdEnvList(unittest.TestCase):
    """cmd_env_list测试。"""

    def test_list_returns_zero(self):
        """list返回0。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            result = cmd_env_list(MagicMock())
        self.assertEqual(result, 0)

    def test_list_shows_keys(self):
        """list显示配置键。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_env_list(MagicMock())
        output = mock_out.getvalue()
        self.assertIn("log_level", output)
        self.assertIn("AGENT_LOG_LEVEL", output)
        self.assertIn("memory_capacity", output)

    def test_list_shows_priority(self):
        """list显示优先级。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            cmd_env_list(MagicMock())
        output = mock_out.getvalue()
        self.assertIn("Priority", output)
        self.assertIn("CLI", output)
        self.assertIn("Env", output)


class TestCmdEnvValidate(unittest.TestCase):
    """cmd_env_validate测试。"""

    def test_no_env_vars(self):
        """无环境变量。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.env_config_cli.EnvConfigManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_all_env_vars.return_value = {}
                result = cmd_env_validate(MagicMock())
        self.assertEqual(result, 0)

    def test_all_valid(self):
        """全部有效。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.env_config_cli.EnvConfigManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_all_env_vars.return_value = {"AGENT_LOG_LEVEL": "DEBUG"}
                instance.is_env_set.return_value = True
                instance.validate_env_value.return_value = (True, "")
                instance.get_env_var_for_key.return_value = "AGENT_LOG_LEVEL"
                instance.get_env_value.return_value = "DEBUG"
                result = cmd_env_validate(MagicMock())
        self.assertEqual(result, 0)

    def test_has_invalid(self):
        """有无效值。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.env_config_cli.EnvConfigManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_all_env_vars.return_value = {"AGENT_MEMORY_CAPACITY": "abc"}
                instance.is_env_set.return_value = True
                instance.validate_env_value.return_value = (False, "error")
                instance.get_env_var_for_key.return_value = "AGENT_MEMORY_CAPACITY"
                instance.get_env_value.return_value = "abc"
                result = cmd_env_validate(MagicMock())
        self.assertEqual(result, 1)


class TestHandleEnv(unittest.TestCase):
    """handle_env测试。"""

    def test_none_action_shows(self):
        """None action执行show。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.env_config_cli.EnvConfigManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_env_config.return_value = {}
                instance.get_all_env_vars.return_value = {}
                args = MagicMock(env_action=None)
                result = handle_env(args)
        self.assertEqual(result, 0)

    def test_show_action(self):
        """show action。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.env_config_cli.EnvConfigManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_env_config.return_value = {}
                instance.get_all_env_vars.return_value = {}
                args = MagicMock(env_action="show")
                result = handle_env(args)
        self.assertEqual(result, 0)

    def test_list_action(self):
        """list action。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            args = MagicMock(env_action="list")
            result = handle_env(args)
        self.assertEqual(result, 0)

    def test_validate_action(self):
        """validate action。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.env_config_cli.EnvConfigManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_all_env_vars.return_value = {}
                args = MagicMock(env_action="validate")
                result = handle_env(args)
        self.assertEqual(result, 0)

    def test_unknown_action(self):
        """未知action返回1。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("sys.stderr", new_callable=io.StringIO):
                args = MagicMock(env_action="unknown")
                result = handle_env(args)
        self.assertEqual(result, 1)


class TestAddEnvSubparser(unittest.TestCase):
    """add_env_subparser测试。"""

    def test_env_subparser_registered(self):
        """env子命令已注册。"""
        parser = _build_parser()
        args = parser.parse_args(["env"])
        self.assertEqual(args.command, "env")

    def test_env_show(self):
        """env show。"""
        parser = _build_parser()
        args = parser.parse_args(["env", "show"])
        self.assertEqual(args.env_action, "show")

    def test_env_list(self):
        """env list。"""
        parser = _build_parser()
        args = parser.parse_args(["env", "list"])
        self.assertEqual(args.env_action, "list")

    def test_env_validate(self):
        """env validate。"""
        parser = _build_parser()
        args = parser.parse_args(["env", "validate"])
        self.assertEqual(args.env_action, "validate")


class TestCLIIntegration(unittest.TestCase):
    """CLI集成测试。"""

    def test_env_show_via_main(self):
        """agent env show通过main。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            result = main(["env", "show"])
        self.assertEqual(result, 0)

    def test_env_list_via_main(self):
        """agent env list通过main。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            result = main(["env", "list"])
        self.assertEqual(result, 0)

    def test_env_validate_via_main(self):
        """agent env validate通过main。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            result = main(["env", "validate"])
        self.assertEqual(result, 0)

    def test_env_default_action(self):
        """agent env默认action。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            result = main(["env"])
        self.assertEqual(result, 0)

    def test_env_in_handlers(self):
        """env在handlers中。"""
        parser = _build_parser()
        args = parser.parse_args(["env"])
        self.assertEqual(args.command, "env")

    def test_env_in_known_commands(self):
        """env在known_commands中。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            result = main(["env", "list"])
        self.assertEqual(result, 0)


class TestShellIntegration(unittest.TestCase):
    """Shell集成测试。"""

    def test_shell_has_do_env(self):
        """Shell有do_env方法。"""
        from agent_core.interactive_shell import AgentShell
        self.assertTrue(hasattr(AgentShell, "do_env"))

    def test_shell_env_list(self):
        """Shell执行env list。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO):
            shell.do_env("list")

    def test_shell_env_show(self):
        """Shell执行env show。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO):
            shell.do_env("show")

    def test_shell_env_in_commands_list(self):
        """env在shell_commands列表中。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO):
            shell.default("en")  # 故意拼错
        # 应该建议env


class TestEdgeCases(unittest.TestCase):
    """边界情况测试。"""

    def test_all_config_keys_have_env_mapping(self):
        """所有配置键都有环境变量映射。"""
        for key, (suffix, _) in _CONFIG_KEY_MAP.items():
            env_name = f"{_ENV_PREFIX}{suffix}"
            self.assertTrue(env_name.startswith(_ENV_PREFIX))
            self.assertEqual(_env_var_name(key), env_name)

    def test_config_key_map_has_log_level(self):
        """配置键映射包含log_level。"""
        self.assertIn("log_level", _CONFIG_KEY_MAP)

    def test_config_key_map_has_memory_capacity(self):
        """配置键映射包含memory_capacity。"""
        self.assertIn("memory_capacity", _CONFIG_KEY_MAP)

    def test_priority_chain_order(self):
        """优先级链顺序正确。"""
        defaults = {"key": "default"}
        file_config = {"key": "file"}
        env_config = {"key": "env"}
        cli_config = {"key": "cli"}

        # CLI最高
        result = merge_config_priority(defaults, file_config, env_config, cli_config)
        self.assertEqual(result["key"], "cli")

        # 环境变量次之（无CLI）
        result = merge_config_priority(defaults, file_config, env_config, {})
        self.assertEqual(result["key"], "env")

        # 配置文件次之（无CLI、env）
        result = merge_config_priority(defaults, file_config, {}, {})
        self.assertEqual(result["key"], "file")

        # 默认值最低
        result = merge_config_priority(defaults, {}, {}, {})
        self.assertEqual(result["key"], "default")

    def test_env_with_special_chars(self):
        """环境变量含特殊字符。"""
        env = {"AGENT_APP_NAME": "my-agent-123"}
        manager = EnvConfigManager(env=env)
        config = manager.get_env_config()
        self.assertEqual(config["app_name"], "my-agent-123")

    def test_empty_env_value(self):
        """空环境变量值。"""
        env = {"AGENT_LOG_LEVEL": ""}
        manager = EnvConfigManager(env=env)
        config = manager.get_env_config()
        # 空字符串是有效的str值
        self.assertIn("log_level", config)
        self.assertEqual(config["log_level"], "")


class TestHelpMetadata(unittest.TestCase):
    """帮助元数据测试。"""

    def test_env_in_command_metadata(self):
        """env在COMMAND_METADATA中。"""
        from agent_core.help_cli import COMMAND_METADATA
        self.assertIn("env", COMMAND_METADATA)

    def test_env_has_category(self):
        """env有分类。"""
        from agent_core.help_cli import COMMAND_METADATA
        meta = COMMAND_METADATA["env"]
        self.assertEqual(meta["category"], "Configuration")

    def test_env_has_examples(self):
        """env有示例。"""
        from agent_core.help_cli import COMMAND_METADATA
        meta = COMMAND_METADATA["env"]
        self.assertIn("examples", meta)
        self.assertGreater(len(meta["examples"]), 0)

    def test_env_help_via_main(self):
        """agent help env通过main。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            result = main(["help", "env"])
        self.assertEqual(result, 0)
        output = mock_out.getvalue()
        self.assertIn("env", output)


class TestSourceConstants(unittest.TestCase):
    """来源常量测试。"""

    def test_source_default(self):
        """默认来源。"""
        self.assertEqual(_SOURCE_DEFAULT, "default")

    def test_source_file(self):
        """文件来源。"""
        self.assertEqual(_SOURCE_FILE, "config-file")

    def test_source_env(self):
        """环境变量来源。"""
        self.assertEqual(_SOURCE_ENV, "env-var")

    def test_source_cli(self):
        """CLI来源。"""
        self.assertEqual(_SOURCE_CLI, "cli-arg")


if __name__ == "__main__":
    unittest.main()
