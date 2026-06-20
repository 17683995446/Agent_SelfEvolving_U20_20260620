"""
U-12: 交互式向导（Onboarding Wizard）测试。

覆盖：
- detect_first_run: 首次运行检测
- mark_initialized: 标记已初始化
- OnboardingWizard: 向导流程
- cmd_wizard/handle_wizard: CLI入口
- CLI集成: wizard子命令
- Shell集成: do_wizard命令
"""

import argparse
import io
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from agent_core.wizard_cli import (
    detect_first_run,
    mark_initialized,
    OnboardingWizard,
    cmd_wizard,
    handle_wizard,
    add_wizard_subparser,
    _FIRST_RUN_MARKERS,
)
from agent_core.cli import main, _build_parser


class TestDetectFirstRun(unittest.TestCase):
    """detect_first_run测试。"""

    def test_empty_dir_is_first_run(self):
        """空目录是首次运行。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertTrue(detect_first_run(tmpdir))

    def test_dir_with_config_not_first_run(self):
        """有config目录不是首次运行。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "config"))
            self.assertFalse(detect_first_run(tmpdir))

    def test_dir_with_base_yaml_not_first_run(self):
        """有config/base.yaml不是首次运行。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "config"))
            with open(os.path.join(tmpdir, "config", "base.yaml"), "w") as f:
                f.write("test")
            self.assertFalse(detect_first_run(tmpdir))

    def test_dir_with_db_not_first_run(self):
        """有agent_memory.db不是首次运行。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "agent_memory.db"), "w") as f:
                f.write("test")
            self.assertFalse(detect_first_run(tmpdir))

    def test_dir_with_marker_not_first_run(self):
        """有.agent_initialized不是首次运行。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, ".agent_initialized"), "w") as f:
                f.write("test")
            self.assertFalse(detect_first_run(tmpdir))

    def test_none_uses_cwd(self):
        """None参数使用当前目录。"""
        # 当前workspace目录有config/，所以不是首次运行
        result = detect_first_run(None)
        self.assertIsInstance(result, bool)


class TestMarkInitialized(unittest.TestCase):
    """mark_initialized测试。"""

    def test_creates_marker_file(self):
        """创建标志文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mark_initialized(tmpdir)
            marker = os.path.join(tmpdir, ".agent_initialized")
            self.assertTrue(os.path.exists(marker))

    def test_marker_makes_not_first_run(self):
        """标记后不再是首次运行。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertTrue(detect_first_run(tmpdir))
            mark_initialized(tmpdir)
            self.assertFalse(detect_first_run(tmpdir))

    def test_none_uses_cwd(self):
        """None参数使用当前目录。"""
        # 不实际写入当前目录，只验证不报错
        # mark_initialized(None)  # 会写入当前目录
        pass


class TestOnboardingWizardNonInteractive(unittest.TestCase):
    """非交互模式向导测试。"""

    def test_non_interactive_returns_true(self):
        """非交互模式返回成功。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                wizard = OnboardingWizard(interactive=False)
                success, config = wizard.run(project_dir=tmpdir)
            self.assertTrue(success)

    def test_non_interactive_generates_config_file(self):
        """非交互模式生成配置文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                wizard = OnboardingWizard(interactive=False)
                wizard.run(project_dir=tmpdir)
            config_path = os.path.join(tmpdir, "config", "dev.yaml")
            self.assertTrue(os.path.exists(config_path))

    def test_non_interactive_uses_defaults(self):
        """非交互模式使用默认值。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                wizard = OnboardingWizard(interactive=False)
                success, config = wizard.run(project_dir=tmpdir)
            self.assertEqual(config["app_name"], "my_agent")
            self.assertEqual(config["log_level"], "DEBUG")  # dev默认

    def test_non_interactive_prod_env(self):
        """非交互模式prod环境默认值。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                wizard = OnboardingWizard(interactive=False)
                wizard._env = "prod"
                wizard._use_defaults()
                wizard._build_config()
            self.assertEqual(wizard._config["log_level"], "INFO")

    def test_non_interactive_marks_initialized(self):
        """非交互模式标记已初始化。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertTrue(detect_first_run(tmpdir))
            with patch("sys.stdout", new_callable=io.StringIO):
                wizard = OnboardingWizard(interactive=False)
                wizard.run(project_dir=tmpdir)
            self.assertFalse(detect_first_run(tmpdir))

    def test_config_contains_required_keys(self):
        """配置包含必需键。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                wizard = OnboardingWizard(interactive=False)
                success, config = wizard.run(project_dir=tmpdir)
            required = ["app_name", "app_version", "log_level",
                        "online_interval_seconds", "offline_interval_seconds",
                        "memory_capacity"]
            for key in required:
                self.assertIn(key, config)

    def test_config_file_is_valid_yaml(self):
        """生成的配置文件是有效YAML。"""
        import yaml
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                wizard = OnboardingWizard(interactive=False)
                wizard.run(project_dir=tmpdir)
            config_path = os.path.join(tmpdir, "config", "dev.yaml")
            with open(config_path, "r") as f:
                loaded = yaml.safe_load(f)
            self.assertEqual(loaded["app_name"], "my_agent")


class TestOnboardingWizardInteractive(unittest.TestCase):
    """交互模式向导测试（模拟输入）。"""

    def _mock_inputs(self, inputs):
        """创建模拟输入的上下文。"""
        return patch("builtins.input", side_effect=inputs)

    def test_interactive_basic_flow(self):
        """交互模式基本流程。"""
        inputs = [
            "test_app",       # app name
            "dev",            # environment
            "",               # online interval (default)
            "",               # offline interval (default)
            "",               # memory capacity (default)
            "n",              # advanced config? no
            "y",              # confirm
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                with self._mock_inputs(inputs):
                    wizard = OnboardingWizard(interactive=True)
                    success, config = wizard.run(project_dir=tmpdir)
            self.assertTrue(success)
            self.assertEqual(config["app_name"], "test_app")

    def test_interactive_cancel(self):
        """交互模式取消。"""
        inputs = [
            "test_app",  # app name
            "dev",       # environment
            "",          # online interval
            "",          # offline interval
            "",          # memory capacity
            "n",         # advanced? no
            "n",         # confirm? no -> cancel
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                with self._mock_inputs(inputs):
                    wizard = OnboardingWizard(interactive=True)
                    success, config = wizard.run(project_dir=tmpdir)
            self.assertFalse(success)
            self.assertEqual(config, {})

    def test_interactive_with_advanced(self):
        """交互模式含高级配置。"""
        inputs = [
            "myapp",     # app name
            "prod",      # environment
            "",          # online interval
            "",          # offline interval
            "",          # memory capacity
            "y",         # advanced? yes
            "",          # exploration rate
            "",          # epsilon
            "",          # interrupt threshold
            "INFO",      # log level
            "y",         # confirm
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                with self._mock_inputs(inputs):
                    wizard = OnboardingWizard(interactive=True)
                    success, config = wizard.run(project_dir=tmpdir)
            self.assertTrue(success)
            self.assertEqual(config["app_name"], "myapp")
            self.assertEqual(config["log_level"], "INFO")

    def test_interactive_custom_values(self):
        """交互模式自定义值。"""
        inputs = [
            "custom_app",  # app name
            "test",        # environment
            "2.5",         # online interval
            "120",         # offline interval
            "5000",        # memory capacity
            "n",           # advanced? no
            "y",           # confirm
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                with self._mock_inputs(inputs):
                    wizard = OnboardingWizard(interactive=True)
                    success, config = wizard.run(project_dir=tmpdir)
            self.assertTrue(success)
            self.assertEqual(config["online_interval_seconds"], 2.5)
            self.assertEqual(config["offline_interval_seconds"], 120.0)
            self.assertEqual(config["memory_capacity"], 5000)

    def test_interactive_invalid_float_uses_default(self):
        """无效浮点输入使用默认值。"""
        inputs = [
            "app",       # app name
            "dev",       # environment
            "not_a_num", # invalid float -> default
            "",          # offline
            "",          # memory
            "n",         # advanced
            "y",         # confirm
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                with self._mock_inputs(inputs):
                    wizard = OnboardingWizard(interactive=True)
                    success, config = wizard.run(project_dir=tmpdir)
            self.assertTrue(success)
            self.assertEqual(config["online_interval_seconds"], 1.0)  # dev默认

    def test_interactive_invalid_int_uses_default(self):
        """无效整数输入使用默认值。"""
        inputs = [
            "app",       # app name
            "dev",       # environment
            "",          # online
            "",          # offline
            "abc",       # invalid int -> default
            "n",         # advanced
            "y",         # confirm
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                with self._mock_inputs(inputs):
                    wizard = OnboardingWizard(interactive=True)
                    success, config = wizard.run(project_dir=tmpdir)
            self.assertTrue(success)
            self.assertEqual(config["memory_capacity"], 10000)

    def test_interactive_eof_uses_defaults(self):
        """EOF异常使用默认值。"""
        inputs = [
            EOFError(),  # app name -> default
            EOFError(),  # environment -> default
            EOFError(),  # online -> default
            EOFError(),  # offline -> default
            EOFError(),  # memory -> default
            EOFError(),  # advanced -> default (no)
            EOFError(),  # confirm -> default (no) -> cancel
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                with self._mock_inputs(inputs):
                    wizard = OnboardingWizard(interactive=True)
                    success, config = wizard.run(project_dir=tmpdir)
            self.assertFalse(success)  # confirm默认no -> cancel


class TestOnboardingWizardEnvDefaults(unittest.TestCase):
    """环境默认值测试。"""

    def test_dev_defaults(self):
        """dev环境默认值。"""
        wizard = OnboardingWizard(interactive=False)
        defaults = wizard._get_env_defaults("dev")
        self.assertEqual(defaults["log_level"], "DEBUG")
        self.assertEqual(defaults["online_interval_seconds"], 1.0)

    def test_prod_defaults(self):
        """prod环境默认值。"""
        wizard = OnboardingWizard(interactive=False)
        defaults = wizard._get_env_defaults("prod")
        self.assertEqual(defaults["log_level"], "INFO")
        self.assertEqual(defaults["online_interval_seconds"], 5.0)

    def test_test_defaults(self):
        """test环境默认值。"""
        wizard = OnboardingWizard(interactive=False)
        defaults = wizard._get_env_defaults("test")
        self.assertEqual(defaults["log_level"], "DEBUG")
        self.assertEqual(defaults["online_interval_seconds"], 0.5)

    def test_unknown_env_falls_back_to_dev(self):
        """未知环境回退到dev默认值。"""
        wizard = OnboardingWizard(interactive=False)
        defaults = wizard._get_env_defaults("unknown")
        self.assertEqual(defaults["log_level"], "DEBUG")


class TestCmdWizard(unittest.TestCase):
    """cmd_wizard测试。"""

    def test_non_interactive_returns_0(self):
        """非交互模式返回0。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                args = argparse.Namespace(
                    directory=tmpdir,
                    yes=True,
                )
                result = cmd_wizard(args)
        self.assertEqual(result, 0)

    def test_interactive_cancel_returns_1(self):
        """交互模式取消返回1。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                with patch("builtins.input", side_effect=[
                    "app", "dev", "", "", "", "n", "n"
                ]):
                    args = argparse.Namespace(
                        directory=tmpdir,
                        yes=False,
                    )
                    result = cmd_wizard(args)
        self.assertEqual(result, 1)


class TestHandleWizard(unittest.TestCase):
    """handle_wizard测试。"""

    def test_returns_int(self):
        """返回整数。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                args = argparse.Namespace(directory=tmpdir, yes=True)
                result = handle_wizard(args)
        self.assertIsInstance(result, int)


class TestAddWizardSubparser(unittest.TestCase):
    """add_wizard_subparser测试。"""

    def test_wizard_subparser_registered(self):
        """wizard子命令已注册。"""
        parser = _build_parser()
        args = parser.parse_args(["wizard"])
        self.assertEqual(args.command, "wizard")

    def test_wizard_with_directory(self):
        """wizard带目录。"""
        parser = _build_parser()
        args = parser.parse_args(["wizard", "/tmp/test"])
        self.assertEqual(args.directory, "/tmp/test")

    def test_wizard_default_directory(self):
        """wizard默认目录。"""
        parser = _build_parser()
        args = parser.parse_args(["wizard"])
        self.assertEqual(args.directory, ".")

    def test_wizard_yes_flag(self):
        """wizard --yes标志。"""
        parser = _build_parser()
        args = parser.parse_args(["wizard", "--yes"])
        self.assertTrue(args.yes)

    def test_wizard_y_short_flag(self):
        """wizard -y短标志。"""
        parser = _build_parser()
        args = parser.parse_args(["wizard", "-y"])
        self.assertTrue(args.yes)


class TestCLIIntegration(unittest.TestCase):
    """CLI集成测试。"""

    def test_wizard_via_main_non_interactive(self):
        """agent wizard --yes通过main。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                result = main(["wizard", tmpdir, "--yes"])
        self.assertEqual(result, 0)

    def test_wizard_generates_config_file(self):
        """wizard生成配置文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                main(["wizard", tmpdir, "--yes"])
            config_path = os.path.join(tmpdir, "config", "dev.yaml")
            self.assertTrue(os.path.exists(config_path))

    def test_wizard_in_handlers(self):
        """wizard在handlers中。"""
        parser = _build_parser()
        args = parser.parse_args(["wizard", "--yes"])
        self.assertEqual(args.command, "wizard")

    def test_wizard_marks_initialized(self):
        """wizard标记已初始化。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertTrue(detect_first_run(tmpdir))
            with patch("sys.stdout", new_callable=io.StringIO):
                main(["wizard", tmpdir, "--yes"])
            self.assertFalse(detect_first_run(tmpdir))


class TestShellWizardCommand(unittest.TestCase):
    """Shell wizard命令测试。"""

    def test_shell_wizard_help(self):
        """Shell wizard非交互模式。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                shell.do_wizard(f"{tmpdir} --yes")

    def test_shell_help_includes_wizard(self):
        """Shell帮助包含wizard。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            shell.do_help("")
        output = mock_out.getvalue()
        self.assertIn("wizard", output)


class TestFirstRunMarkers(unittest.TestCase):
    """首次运行标志测试。"""

    def test_markers_list_not_empty(self):
        """标志列表非空。"""
        self.assertGreater(len(_FIRST_RUN_MARKERS), 0)

    def test_markers_contain_config(self):
        """标志包含config。"""
        self.assertIn("config", _FIRST_RUN_MARKERS)

    def test_markers_contain_db(self):
        """标志包含agent_memory.db。"""
        self.assertIn("agent_memory.db", _FIRST_RUN_MARKERS)

    def test_markers_contain_init_file(self):
        """标志包含.agent_initialized。"""
        self.assertIn(".agent_initialized", _FIRST_RUN_MARKERS)


class TestEdgeCases(unittest.TestCase):
    """边界情况测试。"""

    def test_wizard_creates_config_dir(self):
        """向导创建config目录。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = os.path.join(tmpdir, "config")
            self.assertFalse(os.path.exists(config_dir))
            with patch("sys.stdout", new_callable=io.StringIO):
                wizard = OnboardingWizard(interactive=False)
                wizard.run(project_dir=tmpdir)
            self.assertTrue(os.path.exists(config_dir))

    def test_wizard_config_has_header(self):
        """配置文件有头部注释。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                wizard = OnboardingWizard(interactive=False)
                wizard.run(project_dir=tmpdir)
            config_path = os.path.join(tmpdir, "config", "dev.yaml")
            with open(config_path, "r") as f:
                content = f.read()
            self.assertIn("environment configuration", content)
            self.assertIn("Generated by", content)

    def test_wizard_prod_env_generates_prod_yaml(self):
        """prod环境生成prod.yaml。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                wizard = OnboardingWizard(interactive=False)
                wizard._env = "prod"
                wizard.run(project_dir=tmpdir)
            config_path = os.path.join(tmpdir, "config", "prod.yaml")
            self.assertTrue(os.path.exists(config_path))

    def test_wizard_next_steps_output(self):
        """向导输出下一步指引。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
                wizard = OnboardingWizard(interactive=False)
                wizard.run(project_dir=tmpdir)
            output = mock_out.getvalue()
            self.assertIn("Next Steps", output)
            self.assertIn("agent config validate", output)
            self.assertIn("agent start", output)


if __name__ == "__main__":
    unittest.main()
