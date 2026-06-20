"""
U-4: 交互式Shell与REPL 测试。

覆盖：Shell命令、API交互、脚本模式、命令补全、历史记录。
"""

import io
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from agent_core.interactive_shell import AgentShell, run_shell, _c


class TestShellCommands(unittest.TestCase):
    """Shell命令测试。"""

    def setUp(self):
        self.shell = AgentShell(port=19999)  # 无Agent运行的端口

    def test_shell_initialization(self):
        """Shell初始化。"""
        self.assertEqual(self.shell._port, 19999)
        self.assertEqual(len(self.shell._history), 0)

    def test_exit_returns_true(self):
        """exit命令返回True（退出信号）。"""
        result = self.shell.do_exit("")
        self.assertTrue(result)

    def test_quit_returns_true(self):
        """quit命令返回True。"""
        result = self.shell.do_quit("")
        self.assertTrue(result)

    def test_eof_returns_true(self):
        """EOF(Ctrl+D)返回True。"""
        result = self.shell.do_EOF("")
        self.assertTrue(result)

    def test_emptyline_no_repeat(self):
        """空行不重复上一条命令。"""
        # 默认cmd.Cmd会重复上一条，我们覆盖为不重复
        with patch("sys.stdout", new_callable=io.StringIO):
            self.shell.emptyline()  # 不应抛出异常

    def test_port_command_set(self):
        """port命令设置端口。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            self.shell.do_port("8081")
        self.assertEqual(self.shell._port, 8081)

    def test_port_command_show_current(self):
        """port命令无参数显示当前端口。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_port("")
        output = mock_stdout.getvalue()
        self.assertIn("19999", output)

    def test_port_command_invalid(self):
        """port命令无效输入。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            self.shell.do_port("not_a_number")
        # 端口不应改变
        self.assertEqual(self.shell._port, 19999)

    def test_history_command_empty(self):
        """history命令无历史。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_history("")
        output = mock_stdout.getvalue()
        self.assertIn("No commands", output)

    def test_history_command_with_entries(self):
        """history命令显示历史。"""
        self.shell._history = ["status", "health", "config"]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_history("")
        output = mock_stdout.getvalue()
        self.assertIn("status", output)
        self.assertIn("health", output)
        self.assertIn("config", output)

    def test_precmd_records_history(self):
        """precmd记录历史。"""
        self.shell.precmd("status")
        self.shell.precmd("health")
        self.assertEqual(len(self.shell._history), 2)
        self.assertEqual(self.shell._history[0], "status")

    def test_precmd_skips_history_command(self):
        """precmd不记录history命令本身。"""
        self.shell.precmd("status")
        self.shell.precmd("history")
        self.assertEqual(len(self.shell._history), 1)

    def test_help_command_shows_commands(self):
        """help命令显示可用命令。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_help("")
        output = mock_stdout.getvalue()
        self.assertIn("status", output)
        self.assertIn("config", output)
        self.assertIn("exit", output)

    def test_help_with_arg(self):
        """help带参数显示具体命令帮助。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            # 不应抛出异常
            self.shell.do_help("status")


class TestShellAPIInteraction(unittest.TestCase):
    """Shell API交互测试。"""

    def setUp(self):
        self.shell = AgentShell(port=19999)

    def test_status_no_agent_running(self):
        """status命令无Agent运行时友好报错。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_status("")
        output = mock_stdout.getvalue()
        self.assertIn("Cannot connect", output)

    def test_health_no_agent_running(self):
        """health命令无Agent运行时友好报错。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_health("")
        output = mock_stdout.getvalue()
        self.assertIn("Cannot connect", output)

    def test_metrics_no_agent_running(self):
        """metrics命令无Agent运行时友好报错。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_metrics("")
        output = mock_stdout.getvalue()
        self.assertIn("Cannot connect", output)

    def test_errors_no_agent_running(self):
        """errors命令无Agent运行时友好报错。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_errors("")
        output = mock_stdout.getvalue()
        self.assertIn("Cannot connect", output)

    def test_profile_no_agent_running(self):
        """profile命令无Agent运行时友好报错。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_profile("")
        output = mock_stdout.getvalue()
        self.assertIn("Cannot connect", output)

    def test_config_no_agent_running(self):
        """config命令无Agent运行时友好报错。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_config("")
        output = mock_stdout.getvalue()
        self.assertIn("Cannot connect", output)

    def test_api_get_returns_none_on_connection_error(self):
        """_api_get连接失败返回None。"""
        result = self.shell._api_get("/api/status")
        self.assertIsNone(result)

    @patch("agent_core.interactive_shell.urllib.request.urlopen")
    def test_api_get_success(self, mock_urlopen):
        """_api_get成功返回数据。"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "running", "cycle_count": 42}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = self.shell._api_get("/api/status")
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["cycle_count"], 42)

    @patch("agent_core.interactive_shell.urllib.request.urlopen")
    def test_status_with_mock_data(self, mock_urlopen):
        """status命令使用mock数据。"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "status": "running",
            "cycle_count": 100,
            "interrupt_count": 2,
            "recent_errors": ["error1", "error2"],
            "recent_rewards": [0.8, 0.9, 0.7],
            "current_task": "task_001",
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_status("")

        output = mock_stdout.getvalue()
        self.assertIn("running", output)
        self.assertIn("100", output)
        self.assertIn("error1", output)
        self.assertIn("task_001", output)

    @patch("agent_core.interactive_shell.urllib.request.urlopen")
    def test_health_healthy(self, mock_urlopen):
        """health命令健康状态。"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"status": "running"}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_health("")
        output = mock_stdout.getvalue()
        self.assertIn("HEALTHY", output)

    @patch("agent_core.interactive_shell.urllib.request.urlopen")
    def test_errors_no_errors(self, mock_urlopen):
        """errors命令无错误。"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"recent_errors": []}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_errors("")
        output = mock_stdout.getvalue()
        self.assertIn("No recent errors", output)

    @patch("agent_core.interactive_shell.urllib.request.urlopen")
    def test_config_show_all(self, mock_urlopen):
        """config命令显示全部配置。"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "config": {"app_name": "test", "log_level": "DEBUG"}
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_config("")
        output = mock_stdout.getvalue()
        self.assertIn("app_name", output)
        self.assertIn("test", output)

    @patch("agent_core.interactive_shell.urllib.request.urlopen")
    def test_config_show_single_key(self, mock_urlopen):
        """config命令显示单个键。"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "config": {"app_name": "test_agent", "log_level": "DEBUG"}
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_config("app_name")
        output = mock_stdout.getvalue()
        self.assertIn("test_agent", output)

    @patch("agent_core.interactive_shell.urllib.request.urlopen")
    def test_config_key_not_found(self, mock_urlopen):
        """config命令键不存在。"""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "config": {"app_name": "test"}
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_config("nonexistent")
        output = mock_stdout.getvalue()
        self.assertIn("not found", output)

    def test_config_modify_not_supported(self):
        """config修改提示只读。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            self.shell.do_config("app_name new_value")
        output = mock_stdout.getvalue()
        self.assertIn("not supported", output.lower())


class TestShellScriptMode(unittest.TestCase):
    """Shell脚本模式测试。"""

    def test_script_file_not_found(self):
        """脚本文件不存在返回错误。"""
        result = run_shell(script="/nonexistent/script.txt")
        self.assertEqual(result, 1)

    def test_script_mode_executes_commands(self):
        """脚本模式执行命令。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write("# This is a comment\n")
            f.write("port 8082\n")
            f.write("history\n")
            f.flush()
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = run_shell(port=19999, script=f.name)
                self.assertEqual(result, 0)
            finally:
                os.unlink(f.name)

    def test_script_mode_skips_comments(self):
        """脚本模式跳过注释行。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write("# comment line\n")
            f.write("exit\n")
            f.flush()
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = run_shell(script=f.name)
                self.assertEqual(result, 0)
            finally:
                os.unlink(f.name)


class TestShellCompletion(unittest.TestCase):
    """Shell命令补全测试。"""

    def setUp(self):
        self.shell = AgentShell()

    def test_complete_config_no_text(self):
        """config补全无前缀返回全部。"""
        result = self.shell.complete_config("", "config ", 7, 7)
        self.assertGreater(len(result), 0)
        self.assertIn("app_name", result)

    def test_complete_config_with_prefix(self):
        """config补全带前缀过滤。"""
        result = self.shell.complete_config("app", "config app", 7, 10)
        self.assertIn("app_name", result)
        self.assertNotIn("log_level", result)

    def test_complete_config_no_match(self):
        """config补全无匹配返回空。"""
        result = self.shell.complete_config("xyz", "config xyz", 7, 10)
        self.assertEqual(len(result), 0)


class TestShellColorOutput(unittest.TestCase):
    """Shell彩色输出测试。"""

    def test_color_function_tty(self):
        """_c函数TTY环境加颜色。"""
        with patch("agent_core.interactive_shell.sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            result = _c("test", "\033[31m")
            self.assertIn("\033[31m", result)
            self.assertIn("test", result)

    def test_color_function_non_tty(self):
        """_c函数非TTY环境不加颜色。"""
        with patch("agent_core.interactive_shell.sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = False
            result = _c("test", "\033[31m")
            self.assertEqual(result, "test")


class TestShellIntegration(unittest.TestCase):
    """Shell集成测试。"""

    def test_run_shell_interactive_mode(self):
        """run_shell交互模式。"""
        # 模拟立即退出
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("builtins.input", side_effect=EOFError):
                result = run_shell(port=19999)
        self.assertEqual(result, 0)

    def test_run_shell_keyboard_interrupt(self):
        """run_shell处理Ctrl+C。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("builtins.input", side_effect=KeyboardInterrupt):
                result = run_shell(port=19999)
        self.assertEqual(result, 0)


# 导入json用于mock数据
import json


if __name__ == "__main__":
    unittest.main()
