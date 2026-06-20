"""
U-8: 日志轮转CLI 测试。

覆盖：CLI解析、log-rotate status/rotate/archives、错误处理、Shell集成。
"""

import gzip
import io
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from agent_core.cli import main, _build_parser
from agent_core.log_rotate_cli import (
    handle_log_rotate,
    cmd_log_rotate_status,
    cmd_log_rotate_rotate,
    cmd_log_rotate_archives,
    _resolve_log_path,
    _format_size,
    add_log_rotate_subparser,
)


class TestLogRotateCLIParser(unittest.TestCase):
    """log-rotate子命令解析测试。"""

    def test_log_rotate_command_parsed(self):
        """log-rotate命令解析。"""
        parser = _build_parser()
        args = parser.parse_args(["log-rotate"])
        self.assertEqual(args.command, "log-rotate")

    def test_log_rotate_status_parsed(self):
        """log-rotate status解析。"""
        parser = _build_parser()
        args = parser.parse_args(["log-rotate", "status"])
        self.assertEqual(args.rotate_action, "status")

    def test_log_rotate_status_with_file(self):
        """log-rotate status带文件参数。"""
        parser = _build_parser()
        args = parser.parse_args(["log-rotate", "status", "--file", "/tmp/test.log"])
        self.assertEqual(args.file, "/tmp/test.log")

    def test_log_rotate_status_with_max_bytes(self):
        """log-rotate status带max-bytes。"""
        parser = _build_parser()
        args = parser.parse_args(["log-rotate", "status", "--max-bytes", "1024"])
        self.assertEqual(args.max_bytes, 1024)

    def test_log_rotate_status_with_backup_count(self):
        """log-rotate status带backup-count。"""
        parser = _build_parser()
        args = parser.parse_args(["log-rotate", "status", "--backup-count", "3"])
        self.assertEqual(args.backup_count, 3)

    def test_log_rotate_rotate_parsed(self):
        """log-rotate rotate解析。"""
        parser = _build_parser()
        args = parser.parse_args(["log-rotate", "rotate"])
        self.assertEqual(args.rotate_action, "rotate")

    def test_log_rotate_rotate_force(self):
        """log-rotate rotate --force。"""
        parser = _build_parser()
        args = parser.parse_args(["log-rotate", "rotate", "--force"])
        self.assertTrue(args.force)

    def test_log_rotate_archives_parsed(self):
        """log-rotate archives解析。"""
        parser = _build_parser()
        args = parser.parse_args(["log-rotate", "archives"])
        self.assertEqual(args.rotate_action, "archives")

    def test_log_rotate_default_max_bytes(self):
        """log-rotate默认max-bytes。"""
        parser = _build_parser()
        args = parser.parse_args(["log-rotate", "status"])
        self.assertEqual(args.max_bytes, 10 * 1024 * 1024)

    def test_log_rotate_default_backup_count(self):
        """log-rotate默认backup-count。"""
        parser = _build_parser()
        args = parser.parse_args(["log-rotate", "status"])
        self.assertEqual(args.backup_count, 5)


class TestFormatSize(unittest.TestCase):
    """_format_size测试。"""

    def test_bytes(self):
        """字节。"""
        self.assertEqual(_format_size(500), "500 B")

    def test_kilobytes(self):
        """千字节。"""
        self.assertEqual(_format_size(1024), "1.0 KB")
        self.assertEqual(_format_size(2048), "2.0 KB")

    def test_megabytes(self):
        """兆字节。"""
        self.assertEqual(_format_size(1024 * 1024), "1.0 MB")

    def test_gigabytes(self):
        """吉字节。"""
        self.assertEqual(_format_size(1024 * 1024 * 1024), "1.0 GB")

    def test_zero(self):
        """零字节。"""
        self.assertEqual(_format_size(0), "0 B")


class TestResolveLogPath(unittest.TestCase):
    """日志路径解析测试。"""

    def test_explicit_file_exists(self):
        """显式指定存在的文件。"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
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
        with patch("agent_core.log_rotate_cli._DEFAULT_LOG_PATHS", []):
            with patch("sys.stderr", new_callable=io.StringIO):
                result = _resolve_log_path(None)
        self.assertIsNone(result)


class TestLogRotateStatus(unittest.TestCase):
    """log-rotate status命令测试。"""

    def setUp(self):
        self.log_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        )
        self.log_file.write("x" * 500)
        self.log_file.close()

    def tearDown(self):
        os.unlink(self.log_file.name)
        # 清理归档文件
        for i in range(1, 6):
            archive = f"{self.log_file.name}.{i}.gz"
            if os.path.exists(archive):
                os.unlink(archive)

    def test_status_basic(self):
        """基本状态查询。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name,
                max_bytes=1024,
                backup_count=5,
            )
            result = cmd_log_rotate_status(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Log Rotation Status", output)
        self.assertIn("Current Size", output)
        self.assertIn("Needs Rotate", output)

    def test_status_needs_rotate(self):
        """需要轮转状态。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name,
                max_bytes=100,  # 小于500字节
                backup_count=5,
            )
            result = cmd_log_rotate_status(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("YES", output)

    def test_status_no_rotate_needed(self):
        """不需要轮转状态。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name,
                max_bytes=10000,  # 大于500字节
                backup_count=5,
            )
            result = cmd_log_rotate_status(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("NO", output)

    def test_status_file_not_found(self):
        """文件不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                file="/nonexistent.log",
                max_bytes=1024,
                backup_count=5,
            )
            result = cmd_log_rotate_status(args)
        self.assertEqual(result, 1)

    def test_status_no_file_arg(self):
        """无file参数且无默认文件。"""
        with patch("agent_core.log_rotate_cli._DEFAULT_LOG_PATHS", []):
            with patch("sys.stderr", new_callable=io.StringIO):
                args = MagicMock(file=None, max_bytes=1024, backup_count=5)
                result = cmd_log_rotate_status(args)
        self.assertEqual(result, 1)

    def test_status_shows_archives(self):
        """状态显示归档列表。"""
        # 创建一个归档文件
        archive = f"{self.log_file.name}.1.gz"
        with gzip.open(archive, "wb") as f:
            f.write(b"archived log")

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name,
                max_bytes=1024,
                backup_count=5,
            )
            result = cmd_log_rotate_status(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Archives", output)
        self.assertIn("1.gz", output)


class TestLogRotateRotate(unittest.TestCase):
    """log-rotate rotate命令测试。"""

    def setUp(self):
        self.log_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        )
        self.log_file.write("x" * 500)
        self.log_file.close()

    def tearDown(self):
        if os.path.exists(self.log_file.name):
            os.unlink(self.log_file.name)
        for i in range(1, 6):
            archive = f"{self.log_file.name}.{i}.gz"
            if os.path.exists(archive):
                os.unlink(archive)

    def test_rotate_when_needed(self):
        """需要轮转时执行轮转。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name,
                max_bytes=100,  # 小于500字节，需要轮转
                backup_count=5,
                force=False,
            )
            result = cmd_log_rotate_rotate(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("rotated successfully", output)
        # 验证归档文件已创建
        self.assertTrue(os.path.exists(f"{self.log_file.name}.1.gz"))
        # 验证原文件已清空
        self.assertEqual(os.path.getsize(self.log_file.name), 0)

    def test_rotate_not_needed_no_force(self):
        """不需要轮转且无--force。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name,
                max_bytes=10000,  # 大于500字节，不需要轮转
                backup_count=5,
                force=False,
            )
            result = cmd_log_rotate_rotate(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("No rotation needed", output)

    def test_rotate_force(self):
        """强制轮转。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name,
                max_bytes=10000,  # 不需要轮转
                backup_count=5,
                force=True,
            )
            result = cmd_log_rotate_rotate(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("rotated successfully", output)
        # 验证归档文件已创建
        self.assertTrue(os.path.exists(f"{self.log_file.name}.1.gz"))

    def test_rotate_file_not_found(self):
        """文件不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                file="/nonexistent.log",
                max_bytes=100,
                backup_count=5,
                force=False,
            )
            result = cmd_log_rotate_rotate(args)
        self.assertEqual(result, 1)


class TestLogRotateArchives(unittest.TestCase):
    """log-rotate archives命令测试。"""

    def setUp(self):
        self.log_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False
        )
        self.log_file.write("current log")
        self.log_file.close()

    def tearDown(self):
        if os.path.exists(self.log_file.name):
            os.unlink(self.log_file.name)
        for i in range(1, 6):
            archive = f"{self.log_file.name}.{i}.gz"
            if os.path.exists(archive):
                os.unlink(archive)

    def test_archives_empty(self):
        """无归档文件。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name,
                backup_count=5,
            )
            result = cmd_log_rotate_archives(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("No archive", output)

    def test_archives_with_files(self):
        """有归档文件。"""
        # 创建归档文件
        for i in range(1, 4):
            archive = f"{self.log_file.name}.{i}.gz"
            with gzip.open(archive, "wb") as f:
                f.write(f"archive {i}".encode())

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.log_file.name,
                backup_count=5,
            )
            result = cmd_log_rotate_archives(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("1.gz", output)
        self.assertIn("2.gz", output)
        self.assertIn("3.gz", output)
        self.assertIn("Total", output)
        self.assertIn("Archives: 3", output)

    def test_archives_file_not_found(self):
        """文件不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                file="/nonexistent.log",
                backup_count=5,
            )
            result = cmd_log_rotate_archives(args)
        self.assertEqual(result, 1)


class TestLogRotateHandleDispatch(unittest.TestCase):
    """handle_log_rotate分发测试。"""

    def test_handle_status_action(self):
        """分发到status。"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            with patch("sys.stdout", new_callable=io.StringIO):
                args = MagicMock(
                    rotate_action="status",
                    file=path,
                    max_bytes=1024,
                    backup_count=5,
                )
                result = handle_log_rotate(args)
            self.assertEqual(result, 0)
        finally:
            os.unlink(path)

    def test_handle_none_action_defaults_status(self):
        """无action时默认status。"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            path = f.name
        try:
            with patch("sys.stdout", new_callable=io.StringIO):
                args = MagicMock(
                    rotate_action=None,
                    file=path,
                    max_bytes=1024,
                    backup_count=5,
                )
                result = handle_log_rotate(args)
            self.assertEqual(result, 0)
        finally:
            os.unlink(path)

    def test_handle_unknown_action(self):
        """未知action。"""
        args = MagicMock(rotate_action="unknown")
        with patch("sys.stderr", new_callable=io.StringIO):
            result = handle_log_rotate(args)
        self.assertEqual(result, 1)


class TestLogRotateCLIIntegration(unittest.TestCase):
    """CLI集成测试。"""

    def test_cli_status_via_main(self):
        """通过main调用log-rotate status。"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test log content")
            path = f.name
        try:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                result = main(["log-rotate", "status", "--file", path])
            self.assertEqual(result, 0)
            self.assertIn("Log Rotation Status", mock_stdout.getvalue())
        finally:
            os.unlink(path)

    def test_cli_archives_via_main(self):
        """通过main调用log-rotate archives。"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test log")
            path = f.name
        try:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                result = main(["log-rotate", "archives", "--file", path])
            self.assertEqual(result, 0)
            self.assertIn("Log Archives", mock_stdout.getvalue())
        finally:
            os.unlink(path)

    def test_cli_rotate_force_via_main(self):
        """通过main调用log-rotate rotate --force。"""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test log content")
            path = f.name
        try:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                result = main([
                    "log-rotate", "rotate", "--file", path, "--force"
                ])
            self.assertEqual(result, 0)
            self.assertIn("rotated successfully", mock_stdout.getvalue())
            # 验证归档已创建
            self.assertTrue(os.path.exists(f"{path}.1.gz"))
        finally:
            if os.path.exists(path):
                os.unlink(path)
            for i in range(1, 6):
                archive = f"{path}.{i}.gz"
                if os.path.exists(archive):
                    os.unlink(archive)


class TestShellLogRotateCommand(unittest.TestCase):
    """Shell log-rotate命令测试。"""

    def test_shell_log_rotate_help(self):
        """Shell log-rotate命令有帮助。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell(port=19999)
        self.assertTrue(hasattr(shell, "do_log_rotate"))
        doc = shell.do_log_rotate.__doc__
        self.assertIsNotNone(doc)
        self.assertIn("log-rotate", doc.lower())

    def test_shell_log_rotate_status(self):
        """Shell log-rotate status执行。"""
        from agent_core.interactive_shell import AgentShell
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test log")
            path = f.name
        try:
            shell = AgentShell(port=19999)
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                shell.do_log_rotate(f"status --file {path}")
            output = mock_stdout.getvalue()
            self.assertIn("Log Rotation Status", output)
        finally:
            os.unlink(path)

    def test_shell_help_includes_log_rotate(self):
        """Shell帮助包含log-rotate。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell(port=19999)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            shell.do_help("")
        output = mock_stdout.getvalue()
        self.assertIn("Log Rotation", output)
        self.assertIn("log-rotate", output)


if __name__ == "__main__":
    unittest.main()
