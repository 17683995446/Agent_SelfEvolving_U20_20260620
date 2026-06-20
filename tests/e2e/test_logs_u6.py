"""
U-6: 日志查看/过滤/分析CLI 测试。

覆盖：CLI解析、logs show/tail/analyze/grep、默认路径解析、Shell集成。
"""

import io
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from agent_core.cli import main, _build_parser
from agent_core.logs_cli import (
    handle_logs,
    cmd_logs_show,
    cmd_logs_analyze,
    cmd_logs_grep,
    cmd_logs_tail,
    _resolve_log_path,
    _colorize_log_line,
    add_logs_subparser,
)


class TestLogsCLIParser(unittest.TestCase):
    """logs子命令解析测试。"""

    def test_logs_command_parsed(self):
        """logs命令解析。"""
        parser = _build_parser()
        args = parser.parse_args(["logs"])
        self.assertEqual(args.command, "logs")

    def test_logs_show_parsed(self):
        """logs show解析。"""
        parser = _build_parser()
        args = parser.parse_args(["logs", "show"])
        self.assertEqual(args.command, "logs")
        self.assertEqual(args.logs_action, "show")

    def test_logs_show_with_file(self):
        """logs show带文件参数。"""
        parser = _build_parser()
        args = parser.parse_args(["logs", "show", "--file", "/tmp/test.log"])
        self.assertEqual(args.file, "/tmp/test.log")

    def test_logs_show_with_lines(self):
        """logs show带行数参数。"""
        parser = _build_parser()
        args = parser.parse_args(["logs", "show", "-n", "100"])
        self.assertEqual(args.lines, 100)

    def test_logs_show_with_level(self):
        """logs show带级别过滤。"""
        parser = _build_parser()
        args = parser.parse_args(["logs", "show", "--level", "ERROR"])
        self.assertEqual(args.level, "ERROR")

    def test_logs_tail_parsed(self):
        """logs tail解析。"""
        parser = _build_parser()
        args = parser.parse_args(["logs", "tail"])
        self.assertEqual(args.logs_action, "tail")

    def test_logs_analyze_parsed(self):
        """logs analyze解析。"""
        parser = _build_parser()
        args = parser.parse_args(["logs", "analyze"])
        self.assertEqual(args.logs_action, "analyze")

    def test_logs_grep_parsed(self):
        """logs grep解析。"""
        parser = _build_parser()
        args = parser.parse_args(["logs", "grep", "error"])
        self.assertEqual(args.logs_action, "grep")
        self.assertEqual(args.pattern, "error")

    def test_logs_grep_with_context(self):
        """logs grep带上下文。"""
        parser = _build_parser()
        args = parser.parse_args(["logs", "grep", "error", "-C", "3"])
        self.assertEqual(args.context, 3)

    def test_logs_grep_ignore_case(self):
        """logs grep忽略大小写。"""
        parser = _build_parser()
        args = parser.parse_args(["logs", "grep", "error", "-i"])
        self.assertTrue(args.ignore_case)

    def test_logs_default_lines(self):
        """logs show默认行数50。"""
        parser = _build_parser()
        args = parser.parse_args(["logs", "show"])
        self.assertEqual(args.lines, 50)


class TestResolveLogPath(unittest.TestCase):
    """日志路径解析测试。"""

    def test_explicit_file_exists(self):
        """显式指定存在的文件。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write("test log")
            path = f.name
        try:
            result = _resolve_log_path(path)
            self.assertEqual(result, path)
        finally:
            os.unlink(path)

    def test_explicit_file_not_exists(self):
        """显式指定不存在的文件。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            result = _resolve_log_path("/nonexistent/path.log")
        self.assertIsNone(result)

    def test_none_arg_no_default_files(self):
        """无参数且无默认文件时返回None。"""
        with patch("agent_core.logs_cli._DEFAULT_LOG_PATHS", []):
            with patch("sys.stderr", new_callable=io.StringIO):
                result = _resolve_log_path(None)
        self.assertIsNone(result)

    def test_finds_default_log_file(self):
        """找到默认日志文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "agent.log")
            with open(log_file, "w") as f:
                f.write("test")
            with patch("agent_core.logs_cli._DEFAULT_LOG_PATHS", [log_file]):
                result = _resolve_log_path(None)
            self.assertEqual(result, log_file)


class TestLogsShow(unittest.TestCase):
    """logs show命令测试。"""

    def setUp(self):
        self.log_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        )
        for i in range(20):
            self.log_file.write(
                f"[2024-01-01 10:00:{i:02d}] [INFO] [test] message {i}\n"
            )
        for i in range(5):
            self.log_file.write(
                f"[2024-01-01 10:01:{i:02d}] [ERROR] [test] error {i}\n"
            )
        self.log_file.close()

    def tearDown(self):
        os.unlink(self.log_file.name)

    def test_show_basic(self):
        """基本显示。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name, lines=10, level=None
            )
            result = cmd_logs_show(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("message", output)

    def test_show_level_filter(self):
        """级别过滤。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name, lines=50, level="ERROR"
            )
            result = cmd_logs_show(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("[ERROR]", output)
        self.assertNotIn("[INFO]", output)

    def test_show_lines_limit(self):
        """行数限制。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name, lines=3, level=None
            )
            result = cmd_logs_show(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue().strip().split("\n")
        # 第一行是标题，后面3行是日志
        self.assertLessEqual(len(output), 5)

    def test_show_file_not_found(self):
        """文件不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                file="/nonexistent.log", lines=10, level=None
            )
            result = cmd_logs_show(args)
        self.assertEqual(result, 1)

    def test_show_no_file_arg(self):
        """无file参数且无默认文件。"""
        with patch("agent_core.logs_cli._DEFAULT_LOG_PATHS", []):
            with patch("sys.stderr", new_callable=io.StringIO):
                args = MagicMock(file=None, lines=10, level=None)
                result = cmd_logs_show(args)
        self.assertEqual(result, 1)


class TestLogsGrep(unittest.TestCase):
    """logs grep命令测试。"""

    def setUp(self):
        self.log_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        )
        self.log_file.write("[INFO] starting agent\n")
        self.log_file.write("[ERROR] connection failed\n")
        self.log_file.write("[INFO] retrying\n")
        self.log_file.write("[ERROR] timeout error\n")
        self.log_file.write("[INFO] agent started\n")
        self.log_file.close()

    def tearDown(self):
        os.unlink(self.log_file.name)

    def test_grep_basic(self):
        """基本搜索。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name,
                pattern="error",
                context=0,
                ignore_case=False,
            )
            result = cmd_logs_grep(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        # "error"小写只匹配"timeout error"行（大小写敏感）
        self.assertIn("1 match", output)

    def test_grep_ignore_case(self):
        """忽略大小写搜索。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name,
                pattern="ERROR",
                context=0,
                ignore_case=True,
            )
            result = cmd_logs_grep(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        # ignore_case=True 应匹配 "error" 和 "ERROR"
        self.assertIn("matches", output)

    def test_grep_with_context(self):
        """带上下文搜索。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name,
                pattern="failed",
                context=1,
                ignore_case=False,
            )
            result = cmd_logs_grep(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn(">>", output)  # 匹配行标记

    def test_grep_no_matches(self):
        """无匹配。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name,
                pattern="nonexistent_pattern",
                context=0,
                ignore_case=False,
            )
            result = cmd_logs_grep(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("No matches", output)

    def test_grep_invalid_regex(self):
        """无效正则。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                file=self.log_file.name,
                pattern="[invalid",
                context=0,
                ignore_case=False,
            )
            result = cmd_logs_grep(args)
        self.assertEqual(result, 1)

    def test_grep_file_not_found(self):
        """文件不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                file="/nonexistent.log",
                pattern="test",
                context=0,
                ignore_case=False,
            )
            result = cmd_logs_grep(args)
        self.assertEqual(result, 1)


class TestLogsAnalyze(unittest.TestCase):
    """logs analyze命令测试。"""

    def setUp(self):
        self.log_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        )
        # 写入足够多的日志条目用于分析
        for i in range(30):
            self.log_file.write(
                f"[2024-01-01 10:00:{i:02d}] [INFO] [test] [key=value] message {i}\n"
            )
        for i in range(15):
            self.log_file.write(
                f"[2024-01-01 10:01:{i:02d}] [ERROR] [test] [key=value] error {i}\n"
            )
        self.log_file.close()

    def tearDown(self):
        os.unlink(self.log_file.name)

    def test_analyze_basic(self):
        """基本分析。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(file=self.log_file.name)
            result = cmd_logs_analyze(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Log Analysis Report", output)
        self.assertIn("Error Frequency", output)
        self.assertIn("Anomaly Patterns", output)

    def test_analyze_file_not_found(self):
        """文件不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(file="/nonexistent.log")
            result = cmd_logs_analyze(args)
        self.assertEqual(result, 1)

    def test_analyze_empty_file(self):
        """空文件分析。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write("")
            empty_path = f.name
        try:
            with patch("sys.stderr", new_callable=io.StringIO):
                args = MagicMock(file=empty_path)
                result = cmd_logs_analyze(args)
            self.assertEqual(result, 1)
        finally:
            os.unlink(empty_path)


class TestLogsHandleDispatch(unittest.TestCase):
    """handle_logs分发测试。"""

    def test_handle_show_action(self):
        """分发到show。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write("[INFO] test\n")
            path = f.name
        try:
            args = MagicMock(
                logs_action="show", file=path, lines=10, level=None
            )
            with patch("sys.stdout", new_callable=io.StringIO):
                result = handle_logs(args)
            self.assertEqual(result, 0)
        finally:
            os.unlink(path)

    def test_handle_none_action_defaults_show(self):
        """无action时默认show。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write("[INFO] test\n")
            path = f.name
        try:
            args = MagicMock(
                logs_action=None, file=path, lines=10, level=None
            )
            with patch("sys.stdout", new_callable=io.StringIO):
                result = handle_logs(args)
            self.assertEqual(result, 0)
        finally:
            os.unlink(path)

    def test_handle_unknown_action(self):
        """未知action。"""
        args = MagicMock(logs_action="unknown")
        with patch("sys.stderr", new_callable=io.StringIO):
            result = handle_logs(args)
        self.assertEqual(result, 1)


class TestLogsCLIIntegration(unittest.TestCase):
    """CLI集成测试。"""

    def test_cli_logs_show_via_main(self):
        """通过main调用logs show。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write("[INFO] test message\n")
            path = f.name
        try:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                result = main(["logs", "show", "--file", path])
            self.assertEqual(result, 0)
            self.assertIn("test message", mock_stdout.getvalue())
        finally:
            os.unlink(path)

    def test_cli_logs_grep_via_main(self):
        """通过main调用logs grep。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write("[INFO] starting\n")
            f.write("[ERROR] failed\n")
            path = f.name
        try:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                result = main(["logs", "grep", "failed", "--file", path])
            self.assertEqual(result, 0)
            self.assertIn("1 match", mock_stdout.getvalue())
        finally:
            os.unlink(path)

    def test_cli_logs_no_file_error(self):
        """无文件时报错。"""
        with patch("agent_core.logs_cli._DEFAULT_LOG_PATHS", []):
            with patch("sys.stderr", new_callable=io.StringIO):
                result = main(["logs", "show"])
        self.assertEqual(result, 1)


class TestColorizeLogLine(unittest.TestCase):
    """日志行着色测试。"""

    def test_colorize_disabled(self):
        """非TTY不着色。"""
        with patch("agent_core.logs_cli._COLOR_ENABLED", False):
            line = "[INFO] test message"
            result = _colorize_log_line(line)
        self.assertEqual(result, line)

    def test_colorize_info_line(self):
        """INFO级别着色。"""
        with patch("agent_core.logs_cli._COLOR_ENABLED", True):
            line = "[INFO] test message"
            result = _colorize_log_line(line)
        self.assertIn("test message", result)

    def test_colorize_no_level(self):
        """无级别不着色。"""
        with patch("agent_core.logs_cli._COLOR_ENABLED", True):
            line = "plain text without level"
            result = _colorize_log_line(line)
        self.assertEqual(result, line)


class TestShellLogsCommand(unittest.TestCase):
    """Shell logs命令测试。"""

    def test_shell_logs_help(self):
        """Shell logs命令有帮助。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell(port=19999)
        self.assertTrue(hasattr(shell, "do_logs"))
        doc = shell.do_logs.__doc__
        self.assertIsNotNone(doc)
        self.assertIn("logs", doc.lower())

    def test_shell_logs_show(self):
        """Shell logs show执行。"""
        from agent_core.interactive_shell import AgentShell
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write("[INFO] shell test\n")
            path = f.name
        try:
            shell = AgentShell(port=19999)
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                shell.do_logs(f"show --file {path}")
            output = mock_stdout.getvalue()
            self.assertIn("shell test", output)
        finally:
            os.unlink(path)

    def test_shell_logs_grep(self):
        """Shell logs grep执行。"""
        from agent_core.interactive_shell import AgentShell
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        ) as f:
            f.write("[INFO] found me\n")
            f.write("[INFO] other line\n")
            path = f.name
        try:
            shell = AgentShell(port=19999)
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                shell.do_logs(f"grep found --file {path}")
            output = mock_stdout.getvalue()
            self.assertIn("1 match", output)
        finally:
            os.unlink(path)

    def test_shell_help_includes_logs(self):
        """Shell帮助包含logs。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell(port=19999)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            shell.do_help("")
        output = mock_stdout.getvalue()
        self.assertIn("Logs", output)
        self.assertIn("logs", output)


class TestLogsTailBasic(unittest.TestCase):
    """logs tail基础测试（不测试无限循环）。"""

    def test_tail_file_not_found(self):
        """tail文件不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(file="/nonexistent.log")
            result = cmd_logs_tail(args)
        self.assertEqual(result, 1)

    def test_tail_no_file_arg(self):
        """tail无文件参数。"""
        with patch("agent_core.logs_cli._DEFAULT_LOG_PATHS", []):
            with patch("sys.stderr", new_callable=io.StringIO):
                args = MagicMock(file=None)
                result = cmd_logs_tail(args)
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
