"""
U-9: 配置diff + dry-run模式 测试。

覆盖：config diff/show/validate、dry-run、错误处理、Shell集成。
"""

import io
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from agent_core.cli import main, _build_parser, _do_dry_run, _get_default_config
from agent_core.config_cli import (
    handle_config,
    cmd_config_diff,
    cmd_config_show,
    cmd_config_validate,
    _load_yaml_file,
    _flatten_config,
    _compute_diff,
    add_config_subparser,
)


class TestConfigCLIParser(unittest.TestCase):
    """config子命令解析测试。"""

    def test_config_command_parsed(self):
        """config命令解析。"""
        parser = _build_parser()
        args = parser.parse_args(["config"])
        self.assertEqual(args.command, "config")

    def test_config_diff_parsed(self):
        """config diff解析。"""
        parser = _build_parser()
        args = parser.parse_args([
            "config", "diff", "--file-a", "a.yaml", "--file-b", "b.yaml"
        ])
        self.assertEqual(args.config_action, "diff")
        self.assertEqual(args.file_a, "a.yaml")
        self.assertEqual(args.file_b, "b.yaml")

    def test_config_diff_short_args(self):
        """config diff短参数。"""
        parser = _build_parser()
        args = parser.parse_args([
            "config", "diff", "-a", "a.yaml", "-b", "b.yaml"
        ])
        self.assertEqual(args.file_a, "a.yaml")
        self.assertEqual(args.file_b, "b.yaml")

    def test_config_show_parsed(self):
        """config show解析。"""
        parser = _build_parser()
        args = parser.parse_args(["config", "show"])
        self.assertEqual(args.config_action, "show")
        self.assertEqual(args.env, "dev")

    def test_config_show_with_env(self):
        """config show带环境。"""
        parser = _build_parser()
        args = parser.parse_args(["config", "show", "--env", "prod"])
        self.assertEqual(args.env, "prod")

    def test_config_validate_parsed(self):
        """config validate解析。"""
        parser = _build_parser()
        args = parser.parse_args(["config", "validate"])
        self.assertEqual(args.config_action, "validate")

    def test_config_diff_requires_file_a(self):
        """config diff必须有--file-a。"""
        parser = _build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["config", "diff", "-b", "b.yaml"])

    def test_config_diff_requires_file_b(self):
        """config diff必须有--file-b。"""
        parser = _build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["config", "diff", "-a", "a.yaml"])

    def test_start_dry_run_parsed(self):
        """start --dry-run解析。"""
        parser = _build_parser()
        args = parser.parse_args(["start", "--dry-run"])
        self.assertTrue(args.dry_run)


class TestFlattenConfig(unittest.TestCase):
    """_flatten_config测试。"""

    def test_flat_config(self):
        """扁平配置。"""
        config = {"a": 1, "b": "hello", "c": True}
        result = _flatten_config(config)
        self.assertEqual(result, {"a": 1, "b": "hello", "c": True})

    def test_nested_config(self):
        """嵌套配置。"""
        config = {
            "a": 1,
            "b": {
                "c": 2,
                "d": {
                    "e": 3,
                },
            },
        }
        result = _flatten_config(config)
        self.assertEqual(result, {"a": 1, "b.c": 2, "b.d.e": 3})

    def test_empty_config(self):
        """空配置。"""
        result = _flatten_config({})
        self.assertEqual(result, {})


class TestComputeDiff(unittest.TestCase):
    """_compute_diff测试。"""

    def test_identical_configs(self):
        """相同配置无差异。"""
        config = {"a": 1, "b": 2}
        added, removed, changed = _compute_diff(config, config)
        self.assertEqual(added, {})
        self.assertEqual(removed, {})
        self.assertEqual(changed, {})

    def test_added_keys(self):
        """新增键。"""
        a = {"a": 1}
        b = {"a": 1, "b": 2}
        added, removed, changed = _compute_diff(a, b)
        self.assertEqual(added, {"b": 2})
        self.assertEqual(removed, {})
        self.assertEqual(changed, {})

    def test_removed_keys(self):
        """删除键。"""
        a = {"a": 1, "b": 2}
        b = {"a": 1}
        added, removed, changed = _compute_diff(a, b)
        self.assertEqual(added, {})
        self.assertEqual(removed, {"b": 2})
        self.assertEqual(changed, {})

    def test_changed_keys(self):
        """修改键。"""
        a = {"a": 1, "b": 2}
        b = {"a": 1, "b": 3}
        added, removed, changed = _compute_diff(a, b)
        self.assertEqual(added, {})
        self.assertEqual(removed, {})
        self.assertEqual(changed, {"b": (2, 3)})

    def test_nested_diff(self):
        """嵌套配置差异。"""
        a = {"outer": {"inner": 1}}
        b = {"outer": {"inner": 2}}
        added, removed, changed = _compute_diff(a, b)
        self.assertEqual(changed, {"outer.inner": (1, 2)})


class TestLoadYamlFile(unittest.TestCase):
    """_load_yaml_file测试。"""

    def test_load_valid_yaml(self):
        """加载有效YAML。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("key: value\nnumber: 42\n")
            path = f.name
        try:
            result = _load_yaml_file(path)
            self.assertEqual(result, {"key": "value", "number": 42})
        finally:
            os.unlink(path)

    def test_load_nonexistent_file(self):
        """加载不存在的文件。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            result = _load_yaml_file("/nonexistent.yaml")
        self.assertEqual(result, {})

    def test_load_empty_file(self):
        """加载空文件。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("")
            path = f.name
        try:
            result = _load_yaml_file(path)
            self.assertEqual(result, {})
        finally:
            os.unlink(path)


class TestConfigDiff(unittest.TestCase):
    """config diff命令测试。"""

    def setUp(self):
        self.file_a = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        self.file_a.write("a: 1\nb: 2\nc: 3\n")
        self.file_a.close()

        self.file_b = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        self.file_b.write("a: 1\nb: 99\nd: 4\n")
        self.file_b.close()

    def tearDown(self):
        os.unlink(self.file_a.name)
        os.unlink(self.file_b.name)

    def test_diff_basic(self):
        """基本diff。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file_a=self.file_a.name,
                file_b=self.file_b.name,
            )
            result = cmd_config_diff(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Configuration Diff", output)
        self.assertIn("Added", output)
        self.assertIn("Removed", output)
        self.assertIn("Changed", output)

    def test_diff_shows_added(self):
        """diff显示新增项。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file_a=self.file_a.name,
                file_b=self.file_b.name,
            )
            cmd_config_diff(args)
        output = mock_stdout.getvalue()
        self.assertIn("d", output)  # 新增的键d

    def test_diff_shows_removed(self):
        """diff显示删除项。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file_a=self.file_a.name,
                file_b=self.file_b.name,
            )
            cmd_config_diff(args)
        output = mock_stdout.getvalue()
        self.assertIn("c", output)  # 删除的键c

    def test_diff_shows_changed(self):
        """diff显示修改项。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file_a=self.file_a.name,
                file_b=self.file_b.name,
            )
            cmd_config_diff(args)
        output = mock_stdout.getvalue()
        self.assertIn("b", output)  # 修改的键b
        self.assertIn("2", output)  # 旧值
        self.assertIn("99", output)  # 新值

    def test_diff_identical_files(self):
        """相同文件无差异。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file_a=self.file_a.name,
                file_b=self.file_a.name,
            )
            result = cmd_config_diff(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("No differences", output)

    def test_diff_missing_file_a(self):
        """缺少file_a参数。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(file_a=None, file_b="b.yaml")
            result = cmd_config_diff(args)
        self.assertEqual(result, 1)

    def test_diff_missing_file_b(self):
        """缺少file_b参数。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(file_a="a.yaml", file_b=None)
            result = cmd_config_diff(args)
        self.assertEqual(result, 1)


class TestConfigShow(unittest.TestCase):
    """config show命令测试。"""

    def test_show_basic(self):
        """基本show。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(env="dev", config=None)
            result = cmd_config_show(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Effective Configuration", output)
        self.assertIn("Environment: dev", output)

    def test_show_with_config_file(self):
        """带配置文件show。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("app_name: test_agent\nlog_level: DEBUG\n")
            path = f.name
        try:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                args = MagicMock(env="dev", config=path)
                result = cmd_config_show(args)
            self.assertEqual(result, 0)
            output = mock_stdout.getvalue()
            self.assertIn("test_agent", output)
        finally:
            os.unlink(path)


class TestConfigValidate(unittest.TestCase):
    """config validate命令测试。"""

    def test_validate_default_config(self):
        """验证默认配置。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(env="dev", config=None)
            result = cmd_config_validate(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Configuration is valid", output)

    def test_validate_with_config_file(self):
        """验证指定配置文件。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("app_name: test_agent\nlog_level: INFO\n")
            path = f.name
        try:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                args = MagicMock(env="dev", config=path)
                result = cmd_config_validate(args)
            self.assertEqual(result, 0)
        finally:
            os.unlink(path)


class TestDryRun(unittest.TestCase):
    """dry-run模式测试。"""

    def test_dry_run_valid_config(self):
        """有效配置dry-run。"""
        config = _get_default_config()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = _do_dry_run(config, "dev")
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Dry Run", output)
        self.assertIn("Configuration is valid", output)
        self.assertIn("Key Parameters", output)
        self.assertIn("What Would Happen", output)

    def test_dry_run_shows_key_params(self):
        """dry-run显示关键参数。"""
        config = _get_default_config()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            _do_dry_run(config, "dev")
        output = mock_stdout.getvalue()
        self.assertIn("App Name", output)
        self.assertIn("Log Level", output)
        self.assertIn("Online Interval", output)

    def test_dry_run_shows_startup_plan(self):
        """dry-run显示启动计划。"""
        config = _get_default_config()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            _do_dry_run(config, "dev")
        output = mock_stdout.getvalue()
        self.assertIn("Initialize Agent", output)
        self.assertIn("online loop", output)
        self.assertIn("offline loop", output)
        self.assertIn("Dashboard", output)

    def test_cli_start_dry_run_via_main(self):
        """通过main调用start --dry-run。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = main(["start", "--dry-run"])
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Dry Run", output)


class TestConfigHandleDispatch(unittest.TestCase):
    """handle_config分发测试。"""

    def test_handle_none_action(self):
        """无action时显示提示。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(config_action=None)
            result = handle_config(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("config", output)

    def test_handle_unknown_action(self):
        """未知action。"""
        args = MagicMock(config_action="unknown")
        with patch("sys.stderr", new_callable=io.StringIO):
            result = handle_config(args)
        self.assertEqual(result, 1)


class TestConfigCLIIntegration(unittest.TestCase):
    """CLI集成测试。"""

    def test_cli_config_diff_via_main(self):
        """通过main调用config diff。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f_a:
            f_a.write("a: 1\n")
            path_a = f_a.name
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f_b:
            f_b.write("a: 2\n")
            path_b = f_b.name
        try:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                result = main([
                    "config", "diff",
                    "--file-a", path_a,
                    "--file-b", path_b,
                ])
            self.assertEqual(result, 0)
            output = mock_stdout.getvalue()
            self.assertIn("Changed", output)
        finally:
            os.unlink(path_a)
            os.unlink(path_b)

    def test_cli_config_validate_via_main(self):
        """通过main调用config validate。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = main(["config", "validate"])
        self.assertEqual(result, 0)
        self.assertIn("valid", mock_stdout.getvalue())


class TestShellConfigDiffCommand(unittest.TestCase):
    """Shell config-diff命令测试。"""

    def test_shell_config_diff_help(self):
        """Shell config-diff命令有帮助。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell(port=19999)
        self.assertTrue(hasattr(shell, "do_config_diff"))
        doc = shell.do_config_diff.__doc__
        self.assertIsNotNone(doc)

    def test_shell_config_diff(self):
        """Shell config-diff执行。"""
        from agent_core.interactive_shell import AgentShell
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f_a:
            f_a.write("a: 1\n")
            path_a = f_a.name
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f_b:
            f_b.write("a: 2\n")
            path_b = f_b.name
        try:
            shell = AgentShell(port=19999)
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                shell.do_config_diff(f"diff -a {path_a} -b {path_b}")
            output = mock_stdout.getvalue()
            self.assertIn("Configuration Diff", output)
        finally:
            os.unlink(path_a)
            os.unlink(path_b)

    def test_shell_help_includes_config_diff(self):
        """Shell帮助包含config-diff。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell(port=19999)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            shell.do_help("")
        output = mock_stdout.getvalue()
        self.assertIn("config-diff", output)


if __name__ == "__main__":
    unittest.main()
