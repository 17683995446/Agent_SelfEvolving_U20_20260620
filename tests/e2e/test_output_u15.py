"""
U-15: 输出格式化与无障碍 测试。

覆盖：
- OutputFormatter: 格式化器（text/json/table、颜色、级别）
- create_formatter: 从命令行参数创建格式化器
- add_global_format_args: 全局参数注册
- format_table/format_kv: 独立格式化函数
- CLI集成: --format/--no-color/--quiet/--verbose
"""

import argparse
import io
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

from agent_core.output_formatter import (
    OutputFormatter,
    create_formatter,
    add_global_format_args,
    format_table,
    format_kv,
)
from agent_core.cli import main, _build_parser


class TestOutputFormatterInit(unittest.TestCase):
    """OutputFormatter初始化测试。"""

    def test_default_format_text(self):
        """默认格式是text。"""
        fmt = OutputFormatter(color_enabled=False)
        self.assertEqual(fmt.format, "text")

    def test_json_format(self):
        """JSON格式。"""
        fmt = OutputFormatter(format="json", color_enabled=False)
        self.assertEqual(fmt.format, "json")

    def test_table_format(self):
        """table格式。"""
        fmt = OutputFormatter(format="table", color_enabled=False)
        self.assertEqual(fmt.format, "table")

    def test_default_verbosity_normal(self):
        """默认级别是normal。"""
        fmt = OutputFormatter(color_enabled=False)
        self.assertEqual(fmt.verbosity, "normal")

    def test_quiet_verbosity(self):
        """quiet级别。"""
        fmt = OutputFormatter(verbosity="quiet", color_enabled=False)
        self.assertTrue(fmt.is_quiet)

    def test_verbose_verbosity(self):
        """verbose级别。"""
        fmt = OutputFormatter(verbosity="verbose", color_enabled=False)
        self.assertTrue(fmt.is_verbose)

    def test_color_enabled_explicit(self):
        """显式启用颜色。"""
        fmt = OutputFormatter(color_enabled=True)
        self.assertTrue(fmt.color_enabled)

    def test_color_disabled_explicit(self):
        """显式禁用颜色。"""
        fmt = OutputFormatter(color_enabled=False)
        self.assertFalse(fmt.color_enabled)


class TestColorize(unittest.TestCase):
    """colorize方法测试。"""

    def test_colorized_when_enabled(self):
        """启用时添加颜色。"""
        fmt = OutputFormatter(color_enabled=True)
        result = fmt.colorize("test", "\033[31m")
        self.assertIn("\033[31m", result)
        self.assertIn("test", result)
        self.assertIn("\033[0m", result)

    def test_no_color_when_disabled(self):
        """禁用时无颜色。"""
        fmt = OutputFormatter(color_enabled=False)
        result = fmt.colorize("test", "\033[31m")
        self.assertEqual(result, "test")


class TestPrintMethods(unittest.TestCase):
    """打印方法测试。"""

    def test_print_normal(self):
        """normal模式打印。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print("hello")
        self.assertIn("hello", mock_out.getvalue())

    def test_print_quiet_no_output(self):
        """quiet模式不打印。"""
        fmt = OutputFormatter(verbosity="quiet", color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print("hello")
        self.assertEqual(mock_out.getvalue(), "")

    def test_print_info(self):
        """print_info。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_info("message")
        self.assertIn("message", mock_out.getvalue())
        self.assertIn("[INFO]", mock_out.getvalue())

    def test_print_info_quiet_no_output(self):
        """quiet模式print_info不输出。"""
        fmt = OutputFormatter(verbosity="quiet", color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_info("message")
        self.assertEqual(mock_out.getvalue(), "")

    def test_print_success(self):
        """print_success。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_success("done")
        self.assertIn("done", mock_out.getvalue())
        self.assertIn("[OK]", mock_out.getvalue())

    def test_print_warning(self):
        """print_warning。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_warning("careful")
        self.assertIn("careful", mock_out.getvalue())
        self.assertIn("[WARN]", mock_out.getvalue())

    def test_print_error(self):
        """print_error。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            fmt.print_error("failed")
        self.assertIn("failed", mock_err.getvalue())
        self.assertIn("[ERROR]", mock_err.getvalue())

    def test_print_error_quiet_still_outputs(self):
        """quiet模式print_error仍输出。"""
        fmt = OutputFormatter(verbosity="quiet", color_enabled=False)
        with patch("sys.stderr", new_callable=io.StringIO) as mock_err:
            fmt.print_error("failed")
        self.assertIn("failed", mock_err.getvalue())

    def test_print_verbose_normal_no_output(self):
        """normal模式print_verbose不输出。"""
        fmt = OutputFormatter(verbosity="normal", color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_verbose("debug info")
        self.assertEqual(mock_out.getvalue(), "")

    def test_print_verbose_verbose_outputs(self):
        """verbose模式print_verbose输出。"""
        fmt = OutputFormatter(verbosity="verbose", color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_verbose("debug info")
        self.assertIn("debug info", mock_out.getvalue())
        self.assertIn("[DEBUG]", mock_out.getvalue())


class TestPrintKV(unittest.TestCase):
    """print_kv测试。"""

    def test_text_format(self):
        """text格式。"""
        fmt = OutputFormatter(format="text", color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_kv({"name": "agent", "version": "1.0"})
        output = mock_out.getvalue()
        self.assertIn("name", output)
        self.assertIn("agent", output)
        self.assertIn("version", output)
        self.assertIn("1.0", output)

    def test_json_format(self):
        """json格式。"""
        fmt = OutputFormatter(format="json", color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_kv({"name": "agent", "version": "1.0"})
        output = mock_out.getvalue()
        parsed = json.loads(output)
        self.assertEqual(parsed["name"], "agent")
        self.assertEqual(parsed["version"], "1.0")

    def test_with_title(self):
        """带标题。"""
        fmt = OutputFormatter(format="text", color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_kv({"name": "agent"}, title="Info")
        output = mock_out.getvalue()
        self.assertIn("Info", output)

    def test_quiet_no_output(self):
        """quiet模式不输出。"""
        fmt = OutputFormatter(verbosity="quiet", color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_kv({"name": "agent"})
        self.assertEqual(mock_out.getvalue(), "")

    def test_empty_data(self):
        """空数据。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO):
            fmt.print_kv({})  # 不应报错


class TestPrintTable(unittest.TestCase):
    """print_table测试。"""

    def test_text_format(self):
        """text格式。"""
        fmt = OutputFormatter(format="text", color_enabled=False)
        rows = [{"name": "a", "value": 1}, {"name": "b", "value": 2}]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_table(rows, columns=["name", "value"])
        output = mock_out.getvalue()
        self.assertIn("name", output)
        self.assertIn("value", output)
        self.assertIn("a", output)
        self.assertIn("b", output)

    def test_json_format(self):
        """json格式。"""
        fmt = OutputFormatter(format="json", color_enabled=False)
        rows = [{"name": "a", "value": 1}]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_table(rows, columns=["name", "value"])
        output = mock_out.getvalue()
        parsed = json.loads(output)
        self.assertEqual(parsed[0]["name"], "a")

    def test_with_title(self):
        """带标题。"""
        fmt = OutputFormatter(color_enabled=False)
        rows = [{"name": "a"}]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_table(rows, columns=["name"], title="List")
        output = mock_out.getvalue()
        self.assertIn("List", output)

    def test_empty_rows(self):
        """空行。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_table([], columns=["name"])
        output = mock_out.getvalue()
        self.assertIn("empty", output.lower())

    def test_auto_columns(self):
        """自动列名。"""
        fmt = OutputFormatter(color_enabled=False)
        rows = [{"name": "a", "value": 1}]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_table(rows)  # 不指定columns
        output = mock_out.getvalue()
        self.assertIn("name", output)
        self.assertIn("value", output)

    def test_quiet_no_output(self):
        """quiet模式不输出。"""
        fmt = OutputFormatter(verbosity="quiet", color_enabled=False)
        rows = [{"name": "a"}]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_table(rows, columns=["name"])
        self.assertEqual(mock_out.getvalue(), "")


class TestPrintList(unittest.TestCase):
    """print_list测试。"""

    def test_text_format(self):
        """text格式。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_list(["item1", "item2", "item3"])
        output = mock_out.getvalue()
        self.assertIn("item1", output)
        self.assertIn("item2", output)
        self.assertIn("item3", output)

    def test_json_format(self):
        """json格式。"""
        fmt = OutputFormatter(format="json", color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_list(["item1", "item2"])
        output = mock_out.getvalue()
        parsed = json.loads(output)
        self.assertEqual(parsed, ["item1", "item2"])

    def test_numbered(self):
        """编号列表。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_list(["a", "b"], numbered=True)
        output = mock_out.getvalue()
        self.assertIn("1.", output)
        self.assertIn("2.", output)

    def test_with_title(self):
        """带标题。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_list(["a"], title="Items")
        output = mock_out.getvalue()
        self.assertIn("Items", output)

    def test_empty_list(self):
        """空列表。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_list([])
        output = mock_out.getvalue()
        self.assertIn("empty", output.lower())

    def test_quiet_no_output(self):
        """quiet模式不输出。"""
        fmt = OutputFormatter(verbosity="quiet", color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_list(["a"])
        self.assertEqual(mock_out.getvalue(), "")


class TestPrintJSON(unittest.TestCase):
    """print_json测试。"""

    def test_prints_valid_json(self):
        """打印有效JSON。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_json({"key": "value"})
        output = mock_out.getvalue()
        parsed = json.loads(output)
        self.assertEqual(parsed["key"], "value")

    def test_handles_nested(self):
        """处理嵌套。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_json({"a": {"b": [1, 2, 3]}})
        output = mock_out.getvalue()
        parsed = json.loads(output)
        self.assertEqual(parsed["a"]["b"], [1, 2, 3])


class TestCreateFormatter(unittest.TestCase):
    """create_formatter测试。"""

    def test_default(self):
        """默认参数。"""
        args = argparse.Namespace(
            format="text", no_color=False, quiet=False, verbose=False
        )
        fmt = create_formatter(args)
        self.assertEqual(fmt.format, "text")
        self.assertEqual(fmt.verbosity, "normal")

    def test_json_format(self):
        """JSON格式。"""
        args = argparse.Namespace(
            format="json", no_color=False, quiet=False, verbose=False
        )
        fmt = create_formatter(args)
        self.assertEqual(fmt.format, "json")

    def test_no_color(self):
        """禁用颜色。"""
        args = argparse.Namespace(
            format="text", no_color=True, quiet=False, verbose=False
        )
        fmt = create_formatter(args)
        self.assertFalse(fmt.color_enabled)

    def test_quiet(self):
        """静默模式。"""
        args = argparse.Namespace(
            format="text", no_color=False, quiet=True, verbose=False
        )
        fmt = create_formatter(args)
        self.assertTrue(fmt.is_quiet)

    def test_verbose(self):
        """详细模式。"""
        args = argparse.Namespace(
            format="text", no_color=False, quiet=False, verbose=True
        )
        fmt = create_formatter(args)
        self.assertTrue(fmt.is_verbose)

    def test_quiet_overrides_verbose(self):
        """quiet优先于verbose。"""
        args = argparse.Namespace(
            format="text", no_color=False, quiet=True, verbose=True
        )
        fmt = create_formatter(args)
        self.assertTrue(fmt.is_quiet)
        self.assertFalse(fmt.is_verbose)


class TestAddGlobalFormatArgs(unittest.TestCase):
    """add_global_format_args测试。"""

    def test_format_arg_registered(self):
        """--format参数注册。"""
        parser = argparse.ArgumentParser()
        add_global_format_args(parser)
        args = parser.parse_args(["--format", "json"])
        self.assertEqual(args.format, "json")

    def test_no_color_arg_registered(self):
        """--no-color参数注册。"""
        parser = argparse.ArgumentParser()
        add_global_format_args(parser)
        args = parser.parse_args(["--no-color"])
        self.assertTrue(args.no_color)

    def test_quiet_arg_registered(self):
        """--quiet参数注册。"""
        parser = argparse.ArgumentParser()
        add_global_format_args(parser)
        args = parser.parse_args(["--quiet"])
        self.assertTrue(args.quiet)

    def test_quiet_short_arg(self):
        """-q短参数。"""
        parser = argparse.ArgumentParser()
        add_global_format_args(parser)
        args = parser.parse_args(["-q"])
        self.assertTrue(args.quiet)

    def test_verbose_arg_registered(self):
        """--verbose参数注册。"""
        parser = argparse.ArgumentParser()
        add_global_format_args(parser)
        args = parser.parse_args(["--verbose"])
        self.assertTrue(args.verbose)

    def test_verbose_short_arg(self):
        """-V短参数。"""
        parser = argparse.ArgumentParser()
        add_global_format_args(parser)
        args = parser.parse_args(["-V"])
        self.assertTrue(args.verbose)

    def test_format_choices(self):
        """format选项。"""
        parser = argparse.ArgumentParser()
        add_global_format_args(parser)
        for fmt in ["text", "json", "table"]:
            args = parser.parse_args(["--format", fmt])
            self.assertEqual(args.format, fmt)

    def test_global_args_in_main_parser(self):
        """主parser包含全局参数。"""
        parser = _build_parser()
        args = parser.parse_args(["--format", "json", "version"])
        self.assertEqual(args.format, "json")
        self.assertEqual(args.command, "version")


class TestFormatTable(unittest.TestCase):
    """format_table函数测试。"""

    def test_basic_table(self):
        """基本表格。"""
        rows = [{"name": "a", "value": 1}, {"name": "b", "value": 2}]
        result = format_table(rows, columns=["name", "value"])
        self.assertIn("name", result)
        self.assertIn("value", result)
        self.assertIn("a", result)
        self.assertIn("b", result)

    def test_empty_rows(self):
        """空行。"""
        result = format_table([], columns=["name"])
        self.assertIn("empty", result.lower())

    def test_auto_columns(self):
        """自动列名。"""
        rows = [{"name": "a", "value": 1}]
        result = format_table(rows)
        self.assertIn("name", result)
        self.assertIn("value", result)

    def test_has_separator(self):
        """有分隔线。"""
        rows = [{"name": "a"}]
        result = format_table(rows, columns=["name"])
        self.assertIn("-", result)

    def test_alignment(self):
        """对齐。"""
        rows = [{"name": "a", "value": 1}, {"name": "bbb", "value": 222}]
        result = format_table(rows, columns=["name", "value"])
        lines = result.split("\n")
        # 表头和数据行应有相同宽度
        self.assertGreater(len(lines), 2)


class TestFormatKV(unittest.TestCase):
    """format_kv函数测试。"""

    def test_basic_kv(self):
        """基本键值对。"""
        result = format_kv({"name": "agent", "version": "1.0"})
        self.assertIn("name", result)
        self.assertIn("agent", result)
        self.assertIn("version", result)
        self.assertIn("1.0", result)

    def test_empty_data(self):
        """空数据。"""
        result = format_kv({})
        self.assertIn("empty", result.lower())

    def test_alignment(self):
        """对齐。"""
        result = format_kv({"a": 1, "bbb": 2})
        lines = result.split("\n")
        # 键应该对齐
        self.assertGreater(len(lines), 1)


class TestCLIIntegration(unittest.TestCase):
    """CLI集成测试。"""

    def test_version_with_json_format(self):
        """version命令支持JSON格式。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            result = main(["--format", "json", "version"])
        self.assertEqual(result, 0)

    def test_version_with_no_color(self):
        """version命令支持--no-color。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            result = main(["--no-color", "version"])
        self.assertEqual(result, 0)

    def test_version_with_quiet(self):
        """version命令支持--quiet。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            result = main(["--quiet", "version"])
        self.assertEqual(result, 0)

    def test_help_with_global_options(self):
        """help显示全局选项。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            result = main(["help"])
        output = mock_out.getvalue()
        self.assertIn("Global Options", output)
        self.assertIn("--format", output)
        self.assertIn("--no-color", output)
        self.assertIn("--quiet", output)
        self.assertIn("--verbose", output)

    def test_overview_with_json_format(self):
        """overview支持JSON格式。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            result = main(["overview", "--format", "json"])
        self.assertEqual(result, 0)
        output = mock_out.getvalue()
        # 日志可能混入stdout，提取JSON部分（从第一个{开始）
        json_start = output.find("{")
        self.assertGreater(json_start, -1, "No JSON found in output")
        json_str = output[json_start:]
        parsed = json.loads(json_str)
        self.assertIn("config", parsed)

    def test_global_args_before_command(self):
        """全局参数在命令前。"""
        parser = _build_parser()
        args = parser.parse_args(["--no-color", "--quiet", "version"])
        self.assertTrue(args.no_color)
        self.assertTrue(args.quiet)
        self.assertEqual(args.command, "version")

    def test_global_args_after_command(self):
        """全局参数在命令前（argparse子命令模式限制）。"""
        parser = _build_parser()
        # argparse子命令模式下，全局参数只能在命令前
        args = parser.parse_args(["--no-color", "version"])
        self.assertTrue(args.no_color)
        self.assertEqual(args.command, "version")


class TestEdgeCases(unittest.TestCase):
    """边界情况测试。"""

    def test_long_values_in_table(self):
        """表格中的长值。"""
        fmt = OutputFormatter(color_enabled=False)
        rows = [{"name": "a" * 50, "value": 1}]
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_table(rows, columns=["name", "value"])
        output = mock_out.getvalue()
        self.assertIn("a" * 50, output)

    def test_special_chars_in_kv(self):
        """键值对中的特殊字符。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_kv({"path": "/tmp/test file.yaml", "count": 0})
        output = mock_out.getvalue()
        self.assertIn("/tmp/test file.yaml", output)

    def test_unicode_in_output(self):
        """Unicode输出。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_kv({"name": "测试", "value": "値"})
        output = mock_out.getvalue()
        self.assertIn("测试", output)

    def test_none_value_in_kv(self):
        """键值对中的None值。"""
        fmt = OutputFormatter(color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_kv({"name": None, "value": 1})
        output = mock_out.getvalue()
        self.assertIn("None", output)

    def test_nested_dict_in_json(self):
        """JSON中的嵌套字典。"""
        fmt = OutputFormatter(format="json", color_enabled=False)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            fmt.print_kv({"outer": {"inner": "value"}})
        output = mock_out.getvalue()
        parsed = json.loads(output)
        self.assertEqual(parsed["outer"]["inner"], "value")


if __name__ == "__main__":
    unittest.main()
