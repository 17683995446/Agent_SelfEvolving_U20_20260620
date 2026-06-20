"""
U-14: 系统概览仪表盘 测试。

覆盖：
- collect_config_info: 配置信息收集
- collect_log_info: 日志信息收集
- collect_data_info: 数据信息收集
- collect_plugin_info: 插件信息收集
- collect_runtime_info: 运行时信息收集
- collect_overview: 全貌收集
- format_overview_text/json: 格式化输出
- overview CLI: --format, --env, --port
- CLI集成: overview子命令
- Shell集成: do_overview命令
"""

import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from agent_core.overview_cli import (
    collect_config_info,
    collect_log_info,
    collect_data_info,
    collect_plugin_info,
    collect_runtime_info,
    collect_overview,
    format_overview_text,
    format_overview_json,
    cmd_overview,
    handle_overview,
    add_overview_subparser,
    _format_size,
    _status_icon,
)
from agent_core.cli import main, _build_parser


class TestCollectConfigInfo(unittest.TestCase):
    """collect_config_info测试。"""

    def test_returns_dict(self):
        """返回字典。"""
        result = collect_config_info("dev")
        self.assertIsInstance(result, dict)

    def test_has_env(self):
        """包含env字段。"""
        result = collect_config_info("prod")
        self.assertEqual(result["env"], "prod")

    def test_has_required_keys(self):
        """包含必需键。"""
        result = collect_config_info("dev")
        required = ["env", "config_loaded", "item_count", "valid", "errors"]
        for key in required:
            self.assertIn(key, result)

    def test_errors_is_list(self):
        """errors是列表。"""
        result = collect_config_info("dev")
        self.assertIsInstance(result["errors"], list)


class TestCollectLogInfo(unittest.TestCase):
    """collect_log_info测试。"""

    def test_returns_dict(self):
        """返回字典。"""
        result = collect_log_info()
        self.assertIsInstance(result, dict)

    def test_has_required_keys(self):
        """包含必需键。"""
        result = collect_log_info()
        required = ["log_files", "total_size", "total_lines",
                    "error_count", "warning_count"]
        for key in required:
            self.assertIn(key, result)

    def test_log_files_is_list(self):
        """log_files是列表。"""
        result = collect_log_info()
        self.assertIsInstance(result["log_files"], list)

    def test_counts_are_int(self):
        """计数值是整数。"""
        result = collect_log_info()
        self.assertIsInstance(result["total_size"], int)
        self.assertIsInstance(result["total_lines"], int)
        self.assertIsInstance(result["error_count"], int)
        self.assertIsInstance(result["warning_count"], int)

    def test_finds_log_file(self):
        """能找到日志文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                os.makedirs("logs")
                with open("logs/test.log", "w") as f:
                    f.write("INFO test\nERROR test\nWARNING test\n")
                result = collect_log_info()
                self.assertGreater(len(result["log_files"]), 0)
                self.assertGreater(result["total_lines"], 0)
                self.assertGreater(result["error_count"], 0)
                self.assertGreater(result["warning_count"], 0)
            finally:
                os.chdir(old_cwd)


class TestCollectDataInfo(unittest.TestCase):
    """collect_data_info测试。"""

    def test_returns_dict(self):
        """返回字典。"""
        result = collect_data_info()
        self.assertIsInstance(result, dict)

    def test_has_required_keys(self):
        """包含必需键。"""
        result = collect_data_info()
        required = ["db_exists", "db_path", "experience_count",
                    "config_snapshots", "runtime_state_count"]
        for key in required:
            self.assertIn(key, result)

    def test_db_exists_is_bool(self):
        """db_exists是布尔。"""
        result = collect_data_info()
        self.assertIsInstance(result["db_exists"], bool)

    def test_finds_db(self):
        """能找到数据库。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                import sqlite3
                conn = sqlite3.connect("agent_memory.db")
                conn.execute("CREATE TABLE experiences (id INTEGER)")
                conn.execute("INSERT INTO experiences VALUES (1)")
                conn.execute("INSERT INTO experiences VALUES (2)")
                conn.commit()
                conn.close()

                result = collect_data_info()
                self.assertTrue(result["db_exists"])
                self.assertEqual(result["experience_count"], 2)
            finally:
                os.chdir(old_cwd)


class TestCollectPluginInfo(unittest.TestCase):
    """collect_plugin_info测试。"""

    def test_returns_dict(self):
        """返回字典。"""
        result = collect_plugin_info()
        self.assertIsInstance(result, dict)

    def test_has_required_keys(self):
        """包含必需键。"""
        result = collect_plugin_info()
        self.assertIn("plugin_count", result)
        self.assertIn("plugins", result)

    def test_plugin_count_is_int(self):
        """plugin_count是整数。"""
        result = collect_plugin_info()
        self.assertIsInstance(result["plugin_count"], int)

    def test_plugins_is_list(self):
        """plugins是列表。"""
        result = collect_plugin_info()
        self.assertIsInstance(result["plugins"], list)


class TestCollectRuntimeInfo(unittest.TestCase):
    """collect_runtime_info测试。"""

    def test_returns_dict(self):
        """返回字典。"""
        result = collect_runtime_info(8080)
        self.assertIsInstance(result, dict)

    def test_has_required_keys(self):
        """包含必需键。"""
        result = collect_runtime_info(8080)
        required = ["agent_running", "status", "port"]
        for key in required:
            self.assertIn(key, result)

    def test_port_set(self):
        """端口设置正确。"""
        result = collect_runtime_info(9090)
        self.assertEqual(result["port"], 9090)

    def test_agent_running_is_bool(self):
        """agent_running是布尔。"""
        result = collect_runtime_info(8080)
        self.assertIsInstance(result["agent_running"], bool)

    def test_not_running_by_default(self):
        """默认未运行。"""
        result = collect_runtime_info(9999)  # 不存在的端口
        self.assertFalse(result["agent_running"])
        self.assertEqual(result["status"], "stopped")


class TestCollectOverview(unittest.TestCase):
    """collect_overview测试。"""

    def test_returns_dict(self):
        """返回字典。"""
        result = collect_overview()
        self.assertIsInstance(result, dict)

    def test_has_all_sections(self):
        """包含所有部分。"""
        result = collect_overview()
        sections = ["config", "logs", "data", "plugins", "runtime"]
        for section in sections:
            self.assertIn(section, result)

    def test_config_section_has_env(self):
        """config部分有env。"""
        result = collect_overview(env="prod")
        self.assertEqual(result["config"]["env"], "prod")

    def test_runtime_section_has_port(self):
        """runtime部分有port。"""
        result = collect_overview(port=9090)
        self.assertEqual(result["runtime"]["port"], 9090)


class TestFormatOverviewText(unittest.TestCase):
    """format_overview_text测试。"""

    def setUp(self):
        self.overview = {
            "config": {
                "env": "dev",
                "config_loaded": True,
                "config_path": "/tmp/config",
                "item_count": 28,
                "valid": True,
                "errors": [],
            },
            "logs": {
                "log_files": [],
                "total_size": 1024,
                "total_lines": 100,
                "error_count": 2,
                "warning_count": 5,
            },
            "data": {
                "db_exists": True,
                "db_path": "/tmp/agent_memory.db",
                "experience_count": 100,
                "config_snapshots": 3,
                "runtime_state_count": 50,
            },
            "plugins": {
                "plugin_count": 2,
                "plugins": [{"name": "test_plugin"}],
            },
            "runtime": {
                "agent_running": False,
                "status": "stopped",
                "port": 8080,
            },
        }

    def test_returns_string(self):
        """返回字符串。"""
        result = format_overview_text(self.overview)
        self.assertIsInstance(result, str)

    def test_contains_title(self):
        """包含标题。"""
        result = format_overview_text(self.overview)
        self.assertIn("System Overview", result)

    def test_contains_config_section(self):
        """包含配置部分。"""
        result = format_overview_text(self.overview)
        self.assertIn("Configuration", result)
        self.assertIn("dev", result)

    def test_contains_logs_section(self):
        """包含日志部分。"""
        result = format_overview_text(self.overview)
        self.assertIn("Logs", result)

    def test_contains_data_section(self):
        """包含数据部分。"""
        result = format_overview_text(self.overview)
        self.assertIn("Data", result)

    def test_contains_plugins_section(self):
        """包含插件部分。"""
        result = format_overview_text(self.overview)
        self.assertIn("Plugins", result)

    def test_contains_runtime_section(self):
        """包含运行时部分。"""
        result = format_overview_text(self.overview)
        self.assertIn("Runtime", result)

    def test_shows_error_count(self):
        """显示错误计数。"""
        result = format_overview_text(self.overview)
        self.assertIn("2", result)

    def test_shows_plugin_name(self):
        """显示插件名。"""
        result = format_overview_text(self.overview)
        self.assertIn("test_plugin", result)

    def test_shows_db_path(self):
        """显示数据库路径。"""
        result = format_overview_text(self.overview)
        self.assertIn("agent_memory.db", result)

    def test_handles_empty_overview(self):
        """处理空概览。"""
        result = format_overview_text({})
        self.assertIsInstance(result, str)
        self.assertIn("System Overview", result)


class TestFormatOverviewJson(unittest.TestCase):
    """format_overview_json测试。"""

    def test_returns_valid_json(self):
        """返回有效JSON。"""
        overview = {"config": {"env": "dev"}, "logs": {"error_count": 0}}
        result = format_overview_json(overview)
        parsed = json.loads(result)
        self.assertEqual(parsed["config"]["env"], "dev")

    def test_handles_nested(self):
        """处理嵌套结构。"""
        overview = {
            "config": {"env": "dev", "valid": True},
            "data": {"db_exists": False},
        }
        result = format_overview_json(overview)
        parsed = json.loads(result)
        self.assertTrue(parsed["config"]["valid"])
        self.assertFalse(parsed["data"]["db_exists"])


class TestFormatSize(unittest.TestCase):
    """_format_size测试。"""

    def test_bytes(self):
        """字节。"""
        self.assertEqual(_format_size(500), "500 B")

    def test_kilobytes(self):
        """千字节。"""
        self.assertIn("KB", _format_size(2048))

    def test_megabytes(self):
        """兆字节。"""
        self.assertIn("MB", _format_size(1024 * 1024 * 5))

    def test_gigabytes(self):
        """吉字节。"""
        self.assertIn("GB", _format_size(1024 * 1024 * 1024 * 2))

    def test_zero(self):
        """零。"""
        self.assertEqual(_format_size(0), "0 B")


class TestStatusIcon(unittest.TestCase):
    """_status_icon测试。"""

    def test_ok_true(self):
        """OK状态。"""
        with patch("agent_core.overview_cli._COLOR_ENABLED", False):
            self.assertEqual(_status_icon(True), "[OK]")

    def test_fail_false(self):
        """FAIL状态。"""
        with patch("agent_core.overview_cli._COLOR_ENABLED", False):
            self.assertEqual(_status_icon(False), "[FAIL]")


class TestCmdOverview(unittest.TestCase):
    """cmd_overview测试。"""

    def test_text_format_returns_0(self):
        """文本格式返回0。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            args = argparse.Namespace(format="text", env="dev", port=8080)
            result = cmd_overview(args)
        self.assertEqual(result, 0)

    def test_json_format_returns_0(self):
        """JSON格式返回0。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            args = argparse.Namespace(format="json", env="dev", port=8080)
            result = cmd_overview(args)
        self.assertEqual(result, 0)

    def test_text_output_contains_overview(self):
        """文本输出包含概览。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            args = argparse.Namespace(format="text", env="dev", port=8080)
            cmd_overview(args)
        output = mock_out.getvalue()
        self.assertIn("System Overview", output)

    def test_json_output_is_valid_json(self):
        """JSON输出是有效JSON。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            args = argparse.Namespace(format="json", env="dev", port=8080)
            cmd_overview(args)
        output = mock_out.getvalue()
        parsed = json.loads(output)
        self.assertIn("config", parsed)


class TestHandleOverview(unittest.TestCase):
    """handle_overview测试。"""

    def test_returns_int(self):
        """返回整数。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            args = argparse.Namespace(format="text", env="dev", port=8080)
            result = handle_overview(args)
        self.assertIsInstance(result, int)


class TestAddOverviewSubparser(unittest.TestCase):
    """add_overview_subparser测试。"""

    def test_overview_subparser_registered(self):
        """overview子命令已注册。"""
        parser = _build_parser()
        args = parser.parse_args(["overview"])
        self.assertEqual(args.command, "overview")

    def test_default_format_text(self):
        """默认格式是text。"""
        parser = _build_parser()
        args = parser.parse_args(["overview"])
        self.assertEqual(args.format, "text")

    def test_format_json(self):
        """JSON格式。"""
        parser = _build_parser()
        args = parser.parse_args(["overview", "--format", "json"])
        self.assertEqual(args.format, "json")

    def test_env_option(self):
        """env选项。"""
        parser = _build_parser()
        args = parser.parse_args(["overview", "--env", "prod"])
        self.assertEqual(args.env, "prod")

    def test_port_option(self):
        """port选项。"""
        parser = _build_parser()
        args = parser.parse_args(["overview", "--port", "9090"])
        self.assertEqual(args.port, 9090)


class TestCLIIntegration(unittest.TestCase):
    """CLI集成测试。"""

    def test_overview_via_main_text(self):
        """agent overview通过main（text）。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            result = main(["overview"])
        self.assertEqual(result, 0)
        self.assertIn("System Overview", mock_out.getvalue())

    def test_overview_via_main_json(self):
        """agent overview --format json通过main。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            result = main(["overview", "--format", "json"])
        self.assertEqual(result, 0)
        output = mock_out.getvalue()
        parsed = json.loads(output)
        self.assertIn("config", parsed)

    def test_overview_in_handlers(self):
        """overview在handlers中。"""
        parser = _build_parser()
        args = parser.parse_args(["overview"])
        self.assertEqual(args.command, "overview")


class TestShellOverviewCommand(unittest.TestCase):
    """Shell overview命令测试。"""

    def test_shell_overview_text(self):
        """Shell overview文本格式。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO):
            shell.do_overview("")

    def test_shell_overview_json(self):
        """Shell overview JSON格式。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO):
            shell.do_overview("--format json")

    def test_shell_help_includes_overview(self):
        """Shell帮助包含overview。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            shell.do_help("")
        output = mock_out.getvalue()
        self.assertIn("overview", output)


class TestEdgeCases(unittest.TestCase):
    """边界情况测试。"""

    def test_overview_with_no_config(self):
        """无配置时的概览。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                overview = collect_overview()
                self.assertFalse(overview["config"]["config_loaded"])
                self.assertFalse(overview["data"]["db_exists"])
            finally:
                os.chdir(old_cwd)

    def test_overview_with_errors_in_config(self):
        """配置有错误时的概览。"""
        overview = {
            "config": {
                "env": "dev",
                "config_loaded": True,
                "config_path": "/tmp/config",
                "item_count": 28,
                "valid": False,
                "errors": ["error1", "error2"],
            },
            "logs": {"log_files": [], "total_size": 0, "total_lines": 0,
                     "error_count": 0, "warning_count": 0},
            "data": {"db_exists": False, "db_path": None,
                     "experience_count": 0, "config_snapshots": 0,
                     "runtime_state_count": 0},
            "plugins": {"plugin_count": 0, "plugins": []},
            "runtime": {"agent_running": False, "status": "stopped", "port": 8080},
        }
        result = format_overview_text(overview)
        self.assertIn("error1", result)

    def test_overview_running_agent(self):
        """运行中Agent的概览。"""
        overview = {
            "config": {"env": "dev", "config_loaded": True, "valid": True,
                       "errors": [], "item_count": 28, "config_path": None},
            "logs": {"log_files": [], "total_size": 0, "total_lines": 0,
                     "error_count": 0, "warning_count": 0},
            "data": {"db_exists": False, "db_path": None,
                     "experience_count": 0, "config_snapshots": 0,
                     "runtime_state_count": 0},
            "plugins": {"plugin_count": 0, "plugins": []},
            "runtime": {"agent_running": True, "status": "running",
                        "port": 8080, "cycle_count": 100, "interrupt_count": 5},
        }
        result = format_overview_text(overview)
        self.assertIn("running", result)
        self.assertIn("100", result)


if __name__ == "__main__":
    unittest.main()
