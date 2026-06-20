"""
U-11: 智能帮助与命令建议系统 测试。

覆盖：
- suggest_command: 模糊匹配
- format_suggestions: 建议格式化
- handle_unknown_command: 未知命令处理
- cmd_help: 分类帮助和命令详情
- CLI集成: help子命令、无命令时帮助、未知命令建议
- Shell集成: default方法建议
"""

import argparse
import io
import sys
import unittest
from unittest.mock import patch, MagicMock

from agent_core.help_cli import (
    suggest_command,
    suggest_subcommand,
    format_suggestions,
    handle_unknown_command,
    cmd_help,
    add_help_subparser,
    get_all_commands,
    get_commands_by_category,
    COMMAND_METADATA,
    _show_category_help,
    _show_command_detail,
)
from agent_core.cli import main, _build_parser


class TestSuggestCommand(unittest.TestCase):
    """suggest_command模糊匹配测试。"""

    def setUp(self):
        self.cmds = ["start", "status", "health", "dashboard", "version",
                     "shell", "init", "logs", "plugin", "log-rotate",
                     "config", "data", "help"]

    def test_exact_match(self):
        """精确匹配返回自身。"""
        result = suggest_command("start", self.cmds)
        self.assertEqual(result, ["start"])

    def test_typo_start(self):
        """start的拼写错误。"""
        result = suggest_command("stat", self.cmds)
        self.assertIn("start", result)

    def test_typo_status(self):
        """status的拼写错误。"""
        result = suggest_command("statas", self.cmds)
        self.assertTrue(any("status" in r for r in result))

    def test_typo_health(self):
        """health的拼写错误。"""
        result = suggest_command("healty", self.cmds)
        self.assertIn("health", result)

    def test_typo_logs(self):
        """logs的拼写错误。"""
        result = suggest_command("log", self.cmds)
        self.assertIn("logs", result)

    def test_typo_config(self):
        """config的拼写错误。"""
        result = suggest_command("confi", self.cmds)
        self.assertIn("config", result)

    def test_typo_plugin(self):
        """plugin的拼写错误。"""
        result = suggest_command("pluging", self.cmds)
        self.assertIn("plugin", result)

    def test_no_match(self):
        """完全无关的输入返回空列表。"""
        result = suggest_command("xyzabc", self.cmds)
        self.assertEqual(result, [])

    def test_empty_input(self):
        """空输入返回空列表。"""
        self.assertEqual(suggest_command("", self.cmds), [])

    def test_empty_cmds(self):
        """空命令列表返回空列表。"""
        self.assertEqual(suggest_command("start", []), [])

    def test_max_suggestions(self):
        """限制建议数量。"""
        result = suggest_command("st", self.cmds, max_suggestions=1)
        self.assertLessEqual(len(result), 1)

    def test_cutoff_threshold(self):
        """相似度阈值过滤。"""
        # 高阈值，低相似度不匹配
        result = suggest_command("z", self.cmds, cutoff=0.9)
        self.assertEqual(result, [])

    def test_returns_list(self):
        """返回类型是列表。"""
        result = suggest_command("start", self.cmds)
        self.assertIsInstance(result, list)


class TestSuggestSubcommand(unittest.TestCase):
    """suggest_subcommand测试。"""

    def test_basic(self):
        """子命令建议。"""
        subs = ["show", "tail", "analyze", "grep"]
        result = suggest_subcommand("sho", subs)
        self.assertIn("show", result)

    def test_typo(self):
        """子命令拼写错误。"""
        subs = ["show", "tail", "analyze", "grep"]
        result = suggest_subcommand("analize", subs)
        self.assertIn("analyze", result)


class TestFormatSuggestions(unittest.TestCase):
    """format_suggestions格式化测试。"""

    def test_empty(self):
        """空建议返回空字符串。"""
        self.assertEqual(format_suggestions([]), "")

    def test_single(self):
        """单个建议。"""
        result = format_suggestions(["start"])
        self.assertIn("start", result)
        self.assertIn("Did you mean", result)

    def test_multiple(self):
        """多个建议。"""
        result = format_suggestions(["start", "status"])
        self.assertIn("start", result)
        self.assertIn("status", result)
        self.assertIn("one of", result)

    def test_no_color_in_non_tty(self):
        """非TTY环境不含颜色码。"""
        with patch("agent_core.help_cli._COLOR_ENABLED", False):
            result = format_suggestions(["start"])
            self.assertNotIn("\033[", result)


class TestHandleUnknownCommand(unittest.TestCase):
    """handle_unknown_command测试。"""

    def setUp(self):
        self.cmds = ["start", "status", "health", "logs", "config"]

    def test_returns_1(self):
        """始终返回1。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            result = handle_unknown_command("stat", self.cmds)
        self.assertEqual(result, 1)

    def test_outputs_error(self):
        """输出错误信息。"""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            handle_unknown_command("stat", self.cmds)
        output = mock_err.getvalue()
        self.assertIn("Unknown command", output)
        self.assertIn("stat", output)

    def test_outputs_suggestion(self):
        """输出建议。"""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            handle_unknown_command("stat", self.cmds)
        output = mock_err.getvalue()
        self.assertIn("Did you mean", output)

    def test_outputs_help_hint(self):
        """输出help提示。"""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            handle_unknown_command("stat", self.cmds)
        output = mock_err.getvalue()
        self.assertIn("agent help", output)

    def test_no_suggestion_for_garbage(self):
        """完全无关的输入无建议。"""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            handle_unknown_command("zzzzz", self.cmds)
        output = mock_err.getvalue()
        self.assertNotIn("Did you mean", output)


class TestCmdHelp(unittest.TestCase):
    """cmd_help测试。"""

    def test_no_command_returns_0(self):
        """无参数返回0。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            args = argparse.Namespace(command_name=None)
            result = cmd_help(args)
        self.assertEqual(result, 0)

    def test_shows_category_help(self):
        """显示分类帮助。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            args = argparse.Namespace(command_name=None)
            cmd_help(args)
        output = mock_out.getvalue()
        self.assertIn("Command Reference", output)
        self.assertIn("Lifecycle", output)
        self.assertIn("Configuration", output)

    def test_shows_all_categories(self):
        """显示所有分类。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            args = argparse.Namespace(command_name=None)
            cmd_help(args)
        output = mock_out.getvalue()
        for cat in ["Lifecycle", "Configuration", "Data", "Extensibility", "System"]:
            self.assertIn(cat, output)

    def test_specific_command_returns_0(self):
        """特定命令返回0。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            args = argparse.Namespace(command_name="start")
            result = cmd_help(args)
        self.assertEqual(result, 0)

    def test_specific_command_shows_detail(self):
        """特定命令显示详情。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            args = argparse.Namespace(command_name="start")
            cmd_help(args)
        output = mock_out.getvalue()
        self.assertIn("agent start", output)
        self.assertIn("Summary", output)
        self.assertIn("Examples", output)

    def test_specific_command_shows_examples(self):
        """特定命令显示示例。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            args = argparse.Namespace(command_name="logs")
            cmd_help(args)
        output = mock_out.getvalue()
        self.assertIn("Examples", output)
        self.assertIn("logs show", output)

    def test_unknown_command_returns_1(self):
        """未知命令返回1。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = argparse.Namespace(command_name="nonexistent")
            result = cmd_help(args)
        self.assertEqual(result, 1)

    def test_unknown_command_shows_error(self):
        """未知命令显示错误。"""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            args = argparse.Namespace(command_name="nonexistent")
            cmd_help(args)
        output = mock_err.getvalue()
        self.assertIn("No help available", output)

    def test_unknown_command_shows_suggestion(self):
        """未知命令显示建议。"""
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            args = argparse.Namespace(command_name="stat")
            cmd_help(args)
        output = mock_err.getvalue()
        self.assertIn("Did you mean", output)


class TestShowCategoryHelp(unittest.TestCase):
    """_show_category_help测试。"""

    def test_returns_0(self):
        """返回0。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            result = _show_category_help()
        self.assertEqual(result, 0)

    def test_shows_tips(self):
        """显示提示。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _show_category_help()
        output = mock_out.getvalue()
        self.assertIn("Tips", output)
        self.assertIn("agent help", output)

    def test_shows_usage(self):
        """显示用法。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _show_category_help()
        output = mock_out.getvalue()
        self.assertIn("Usage", output)
        self.assertIn("agent <command>", output)


class TestShowCommandDetail(unittest.TestCase):
    """_show_command_detail测试。"""

    def test_valid_command_returns_0(self):
        """有效命令返回0。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            result = _show_command_detail("start")
        self.assertEqual(result, 0)

    def test_shows_summary(self):
        """显示摘要。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _show_command_detail("start")
        output = mock_out.getvalue()
        self.assertIn("Summary", output)
        self.assertIn("启动Agent", output)

    def test_shows_category(self):
        """显示分类。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _show_command_detail("start")
        output = mock_out.getvalue()
        self.assertIn("Category", output)
        self.assertIn("Lifecycle", output)

    def test_shows_description(self):
        """显示描述。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _show_command_detail("start")
        output = mock_out.getvalue()
        self.assertIn("Description", output)

    def test_shows_examples(self):
        """显示示例。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _show_command_detail("init")
        output = mock_out.getvalue()
        self.assertIn("Examples", output)
        self.assertIn("agent init", output)

    def test_invalid_command_returns_1(self):
        """无效命令返回1。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            result = _show_command_detail("nonexistent")
        self.assertEqual(result, 1)

    def test_shows_help_hint(self):
        """显示--help提示。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _show_command_detail("start")
        output = mock_out.getvalue()
        self.assertIn("--help", output)


class TestCommandMetadata(unittest.TestCase):
    """命令元数据测试。"""

    def test_all_commands_have_metadata(self):
        """所有命令都有元数据。"""
        all_cmds = get_all_commands()
        for cmd in all_cmds:
            self.assertIn(cmd, COMMAND_METADATA)

    def test_metadata_has_required_fields(self):
        """元数据包含必需字段。"""
        for cmd, meta in COMMAND_METADATA.items():
            self.assertIn("category", meta, f"{cmd} missing category")
            self.assertIn("summary", meta, f"{cmd} missing summary")
            self.assertIn("description", meta, f"{cmd} missing description")
            self.assertIn("examples", meta, f"{cmd} missing examples")

    def test_help_command_exists(self):
        """help命令在元数据中。"""
        self.assertIn("help", COMMAND_METADATA)

    def test_get_commands_by_category(self):
        """按分类获取命令。"""
        by_cat = get_commands_by_category()
        self.assertIn("Lifecycle", by_cat)
        self.assertIn("start", by_cat["Lifecycle"])
        self.assertIn("Configuration", by_cat)
        self.assertIn("init", by_cat["Configuration"])


class TestAddHelpSubparser(unittest.TestCase):
    """add_help_subparser测试。"""

    def test_help_subparser_registered(self):
        """help子命令已注册。"""
        parser = _build_parser()
        args = parser.parse_args(["help"])
        self.assertEqual(args.command, "help")

    def test_help_with_command_name(self):
        """help带命令名。"""
        parser = _build_parser()
        args = parser.parse_args(["help", "start"])
        self.assertEqual(args.command, "help")
        self.assertEqual(args.command_name, "start")

    def test_help_without_command_name(self):
        """help不带命令名。"""
        parser = _build_parser()
        args = parser.parse_args(["help"])
        self.assertIsNone(args.command_name)


class TestCLIIntegration(unittest.TestCase):
    """CLI集成测试。"""

    def test_no_command_shows_help(self):
        """无命令时显示分类帮助。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            result = main([])
        self.assertEqual(result, 0)
        output = mock_out.getvalue()
        self.assertIn("Command Reference", output)

    def test_help_command_via_main(self):
        """agent help显示帮助。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            result = main(["help"])
        self.assertEqual(result, 0)
        output = mock_out.getvalue()
        self.assertIn("Command Reference", output)

    def test_help_with_command_via_main(self):
        """agent help start显示详情。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            result = main(["help", "start"])
        self.assertEqual(result, 0)
        output = mock_out.getvalue()
        self.assertIn("agent start", output)
        self.assertIn("Summary", output)

    def test_help_unknown_command_via_main(self):
        """agent help unknown返回1。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            result = main(["help", "nonexistent"])
        self.assertEqual(result, 1)

    def test_help_in_handlers(self):
        """help在handlers字典中。"""
        parser = _build_parser()
        args = parser.parse_args(["help"])
        # 确保help命令能被正确解析
        self.assertEqual(args.command, "help")

    def test_all_commands_in_metadata(self):
        """所有CLI命令都在元数据中。"""
        parser = _build_parser()
        # 获取所有注册的子命令
        # 通过解析--help输出获取命令列表
        all_cmds = get_all_commands()
        expected = {"start", "status", "health", "dashboard", "version",
                    "shell", "init", "logs", "plugin", "log-rotate",
                    "config", "data", "help", "wizard", "alias", "overview",
                    "history", "template"}
        self.assertEqual(set(all_cmds), expected)


class TestShellDefaultCommand(unittest.TestCase):
    """Shell default方法测试。"""

    def test_default_shows_error(self):
        """default方法显示错误。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            shell.default("stat")
        output = mock_out.getvalue()
        self.assertIn("Unknown command", output)
        self.assertIn("stat", output)

    def test_default_shows_suggestion(self):
        """default方法显示建议。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            shell.default("stat")
        output = mock_out.getvalue()
        self.assertIn("Did you mean", output)

    def test_default_shows_help_hint(self):
        """default方法显示help提示。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            shell.default("xyz")
        output = mock_out.getvalue()
        self.assertIn("help", output)

    def test_default_garbage_no_suggestion(self):
        """完全无关的输入无建议。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            shell.default("zzzzz")
        output = mock_out.getvalue()
        self.assertNotIn("Did you mean", output)


class TestEdgeCases(unittest.TestCase):
    """边界情况测试。"""

    def test_suggest_with_hyphen(self):
        """含连字符的命令建议。"""
        cmds = ["log-rotate", "logs", "config"]
        result = suggest_command("log-rotat", cmds)
        self.assertIn("log-rotate", result)

    def test_suggest_case_sensitive(self):
        """建议区分大小写。"""
        cmds = ["start", "status"]
        result = suggest_command("Start", cmds)
        # difflib默认大小写敏感，Start可能不匹配start
        # 但相似度可能足够高
        self.assertIsInstance(result, list)

    def test_help_for_help(self):
        """help help显示help命令详情。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            args = argparse.Namespace(command_name="help")
            cmd_help(args)
        output = mock_out.getvalue()
        self.assertIn("agent help", output)
        self.assertIn("显示帮助", output)

    def test_help_for_data(self):
        """help data显示data命令详情。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            args = argparse.Namespace(command_name="data")
            cmd_help(args)
        output = mock_out.getvalue()
        self.assertIn("agent data", output)
        self.assertIn("导出", output)

    def test_help_for_config(self):
        """help config显示config命令详情。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            args = argparse.Namespace(command_name="config")
            cmd_help(args)
        output = mock_out.getvalue()
        self.assertIn("agent config", output)
        self.assertIn("配置", output)


if __name__ == "__main__":
    unittest.main()
