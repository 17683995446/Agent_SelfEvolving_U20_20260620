"""
U-18: 批量操作与管道支持 测试。

覆盖：
- parse_batch_content: 批量内容解析
- parse_command_chain: 命令链解析（&&/||/;/|）
- BatchResult: 执行结果
- BatchExecutor: 批量执行器
- batch CLI: run/preview
- CLI集成: batch命令注册与分发
- Shell集成: do_batch
"""

import argparse
import io
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from agent_core.batch_cli import (
    BatchResult,
    BatchExecutor,
    parse_batch_content,
    parse_command_chain,
    cmd_batch_run,
    cmd_batch_preview,
    handle_batch,
    add_batch_subparser,
    _OP_AND,
    _OP_OR,
    _OP_SEMI,
    _OP_PIPE,
)
from agent_core.cli import main, _build_parser


class TestParseBatchContent(unittest.TestCase):
    """parse_batch_content测试。"""

    def test_empty_content(self):
        """空内容返回空列表。"""
        self.assertEqual(parse_batch_content(""), [])
        self.assertEqual(parse_batch_content(None), [])

    def test_single_command(self):
        """单条命令。"""
        result = parse_batch_content("version")
        self.assertEqual(result, ["version"])

    def test_multiple_commands(self):
        """多条命令。"""
        content = "version\nstatus\nhealth"
        result = parse_batch_content(content)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], "version")
        self.assertEqual(result[1], "status")
        self.assertEqual(result[2], "health")

    def test_skip_comments(self):
        """跳过注释。"""
        content = "# 这是注释\nversion\n# 另一个注释"
        result = parse_batch_content(content)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], "version")

    def test_skip_empty_lines(self):
        """跳过空行。"""
        content = "version\n\n\nstatus\n"
        result = parse_batch_content(content)
        self.assertEqual(len(result), 2)

    def test_strip_whitespace(self):
        """去除首尾空白。"""
        content = "  version  \n  status  "
        result = parse_batch_content(content)
        self.assertEqual(result[0], "version")
        self.assertEqual(result[1], "status")

    def test_line_continuation(self):
        """续行符支持。"""
        content = "version \\\n--no-color"
        result = parse_batch_content(content)
        self.assertEqual(len(result), 1)
        self.assertIn("version", result[0])
        self.assertIn("--no-color", result[0])

    def test_inline_operators_preserved(self):
        """行内操作符保留。"""
        content = "version && status"
        result = parse_batch_content(content)
        self.assertEqual(len(result), 1)
        self.assertIn("&&", result[0])


class TestParseCommandChain(unittest.TestCase):
    """parse_command_chain测试。"""

    def test_empty(self):
        """空字符串。"""
        self.assertEqual(parse_command_chain(""), [])

    def test_single_command(self):
        """单条命令。"""
        result = parse_command_chain("version")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], ("version", ""))

    def test_and_operator(self):
        """&&操作符。"""
        result = parse_command_chain("version && status")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("version", ""))
        self.assertEqual(result[1], ("status", "&&"))

    def test_or_operator(self):
        """||操作符。"""
        result = parse_command_chain("version || status")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("version", ""))
        self.assertEqual(result[1], ("status", "||"))

    def test_semicolon_operator(self):
        """分号操作符。"""
        result = parse_command_chain("version ; status")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("version", ""))
        self.assertEqual(result[1], ("status", ";"))

    def test_pipe_operator(self):
        """管道操作符。"""
        result = parse_command_chain("version | status")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("version", ""))
        self.assertEqual(result[1], ("status", "|"))

    def test_multiple_operators(self):
        """多操作符链。"""
        result = parse_command_chain("cmd1 && cmd2 || cmd3 ; cmd4")
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0], ("cmd1", ""))
        self.assertEqual(result[1], ("cmd2", "&&"))
        self.assertEqual(result[2], ("cmd3", "||"))
        self.assertEqual(result[3], ("cmd4", ";"))

    def test_first_command_op_empty(self):
        """第一条命令操作符为空。"""
        result = parse_command_chain("cmd1 && cmd2")
        self.assertEqual(result[0][1], "")

    def test_strips_whitespace(self):
        """去除空白。"""
        result = parse_command_chain("  version  &&  status  ")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], ("version", ""))
        self.assertEqual(result[1], ("status", "&&"))


class TestBatchResult(unittest.TestCase):
    """BatchResult测试。"""

    def test_default(self):
        """默认值。"""
        result = BatchResult(command="test")
        self.assertEqual(result.command, "test")
        self.assertIsNone(result.exit_code)
        self.assertEqual(result.output, "")
        self.assertFalse(result.skipped)
        self.assertEqual(result.duration, 0.0)

    def test_success_property(self):
        """success属性。"""
        success = BatchResult(command="test", exit_code=0)
        failure = BatchResult(command="test", exit_code=1)
        self.assertTrue(success.success)
        self.assertFalse(failure.success)

    def test_executed_property(self):
        """executed属性。"""
        executed = BatchResult(command="test", exit_code=0)
        skipped = BatchResult(command="test", skipped=True)
        self.assertTrue(executed.executed)
        self.assertFalse(skipped.executed)

    def test_to_dict(self):
        """转字典。"""
        result = BatchResult(
            command="test", exit_code=0, output="hello",
            skipped=False, duration=1.5,
        )
        d = result.to_dict()
        self.assertEqual(d["command"], "test")
        self.assertEqual(d["exit_code"], 0)
        self.assertEqual(d["output"], "hello")
        self.assertFalse(d["skipped"])
        self.assertEqual(d["duration"], 1.5)
        self.assertTrue(d["success"])


class TestBatchExecutor(unittest.TestCase):
    """BatchExecutor测试。"""

    def test_dry_run_returns_zero(self):
        """dry-run模式返回0。"""
        executor = BatchExecutor(dry_run=True)
        results = executor.execute(["version"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].exit_code, 0)

    def test_empty_commands(self):
        """空命令列表。"""
        executor = BatchExecutor()
        results = executor.execute([])
        self.assertEqual(results, [])

    def test_execute_single_command(self):
        """执行单条命令。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                executor = BatchExecutor()
                results = executor.execute(["version"])
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0].exit_code, 0)
            finally:
                os.chdir(old_cwd)

    def test_stop_on_error_default(self):
        """默认出错停止。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                executor = BatchExecutor()
                # 第一条命令会失败（不存在的命令），第二条应被跳过
                results = executor.execute([
                    "nonexistent_cmd_xyz",
                    "version",
                ])
                self.assertEqual(len(results), 2)
                # 第二条被跳过
                self.assertTrue(results[1].skipped)
            finally:
                os.chdir(old_cwd)

    def test_continue_on_error(self):
        """continue_on_error继续执行。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                executor = BatchExecutor(continue_on_error=True)
                results = executor.execute([
                    "nonexistent_cmd_xyz",
                    "version",
                ])
                self.assertEqual(len(results), 2)
                # 第二条执行了
                self.assertFalse(results[1].skipped)
            finally:
                os.chdir(old_cwd)

    def test_summary(self):
        """执行摘要。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                executor = BatchExecutor()
                executor.execute(["version", "status"])
                summary = executor.summary()
                self.assertEqual(summary["total"], 2)
                self.assertEqual(summary["executed"], 2)
                self.assertEqual(summary["skipped"], 0)
            finally:
                os.chdir(old_cwd)

    def test_summary_all_success(self):
        """全部成功摘要。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                executor = BatchExecutor()
                executor.execute(["version"])
                summary = executor.summary()
                self.assertTrue(summary["all_success"])
            finally:
                os.chdir(old_cwd)

    def test_results_property(self):
        """results属性返回副本。"""
        executor = BatchExecutor(dry_run=True)
        executor.execute(["version"])
        results1 = executor.results
        results2 = executor.results
        self.assertIsNot(results1, results2)
        self.assertEqual(len(results1), len(results2))

    def test_and_operator_success(self):
        """&&操作符：前成功执行后。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                executor = BatchExecutor()
                results = executor.execute(["version && template list"])
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0].exit_code, 0)
            finally:
                os.chdir(old_cwd)

    def test_and_operator_skip_on_fail(self):
        """&&操作符：前失败跳过后。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                executor = BatchExecutor(continue_on_error=True)
                results = executor.execute([
                    "nonexistent_xyz && version"
                ])
                self.assertEqual(len(results), 1)
                # 整体失败（因为第一条失败，第二条跳过）
                self.assertNotEqual(results[0].exit_code, 0)
            finally:
                os.chdir(old_cwd)

    def test_semicolon_operator(self):
        """分号操作符无条件执行。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                executor = BatchExecutor()
                results = executor.execute(["version ; template list"])
                self.assertEqual(len(results), 1)
            finally:
                os.chdir(old_cwd)

    def test_agent_prefix_stripped(self):
        """agent前缀被去除。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                executor = BatchExecutor()
                results = executor.execute(["agent version"])
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0].exit_code, 0)
            finally:
                os.chdir(old_cwd)


class TestCmdBatchRun(unittest.TestCase):
    """cmd_batch_run测试。"""

    def test_no_commands_warns(self):
        """无命令警告。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            args = MagicMock(file=None, commands=None, dry_run=False,
                             continue_on_error=False, verbose=False)
            # stdin为空
            with patch("sys.stdin", new_callable=io.StringIO):
                result = cmd_batch_run(args)
        self.assertEqual(result, 0)
        self.assertIn("No commands", mock_out.getvalue())

    def test_inline_commands(self):
        """内联命令。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    args = MagicMock(
                        file=None,
                        commands="version\ntemplate list",
                        dry_run=False,
                        continue_on_error=False,
                        verbose=False,
                    )
                    result = cmd_batch_run(args)
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_file_not_found(self):
        """文件不存在返回1。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("sys.stderr", new_callable=io.StringIO):
                args = MagicMock(
                    file="/nonexistent/file.txt",
                    commands=None,
                    dry_run=False,
                    continue_on_error=False,
                    verbose=False,
                )
                result = cmd_batch_run(args)
        self.assertEqual(result, 1)

    def test_file_commands(self):
        """从文件读取命令。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                # 创建批量文件
                batch_file = os.path.join(tmpdir, "cmds.txt")
                with open(batch_file, "w") as f:
                    f.write("# 注释\nversion\ntemplate list\n")

                with patch("sys.stdout", new_callable=io.StringIO):
                    args = MagicMock(
                        file=batch_file,
                        commands=None,
                        dry_run=False,
                        continue_on_error=False,
                        verbose=False,
                    )
                    result = cmd_batch_run(args)
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_dry_run(self):
        """dry-run模式。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    args = MagicMock(
                        file=None,
                        commands="version",
                        dry_run=True,
                        continue_on_error=False,
                        verbose=False,
                    )
                    result = cmd_batch_run(args)
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)


class TestCmdBatchPreview(unittest.TestCase):
    """cmd_batch_preview测试。"""

    def test_preview_returns_zero(self):
        """预览返回0。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    args = MagicMock(
                        file=None,
                        commands="version",
                        dry_run=False,
                        continue_on_error=False,
                        verbose=False,
                    )
                    result = cmd_batch_preview(args)
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)


class TestHandleBatch(unittest.TestCase):
    """handle_batch测试。"""

    def test_none_action_runs(self):
        """None action执行run。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    args = MagicMock(
                        batch_action=None,
                        file=None,
                        commands="version",
                        dry_run=False,
                        continue_on_error=False,
                        verbose=False,
                    )
                    result = handle_batch(args)
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_run_action(self):
        """run action。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    args = MagicMock(
                        batch_action="run",
                        file=None,
                        commands="version",
                        dry_run=False,
                        continue_on_error=False,
                        verbose=False,
                    )
                    result = handle_batch(args)
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_preview_action(self):
        """preview action。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    args = MagicMock(
                        batch_action="preview",
                        file=None,
                        commands="version",
                        dry_run=False,
                        continue_on_error=False,
                        verbose=False,
                    )
                    result = handle_batch(args)
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_unknown_action(self):
        """未知action返回1。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("sys.stderr", new_callable=io.StringIO):
                args = MagicMock(batch_action="unknown")
                result = handle_batch(args)
        self.assertEqual(result, 1)


class TestAddBatchSubparser(unittest.TestCase):
    """add_batch_subparser测试。"""

    def test_batch_subparser_registered(self):
        """batch子命令已注册。"""
        parser = _build_parser()
        args = parser.parse_args(["batch"])
        self.assertEqual(args.command, "batch")

    def test_batch_run(self):
        """batch run。"""
        parser = _build_parser()
        args = parser.parse_args(["batch", "run", "-c", "version"])
        self.assertEqual(args.batch_action, "run")
        self.assertEqual(args.commands, "version")

    def test_batch_preview(self):
        """batch preview。"""
        parser = _build_parser()
        args = parser.parse_args(["batch", "preview", "-c", "version"])
        self.assertEqual(args.batch_action, "preview")

    def test_batch_file_option(self):
        """batch -f选项。"""
        parser = _build_parser()
        args = parser.parse_args(["batch", "-f", "cmds.txt"])
        self.assertEqual(args.file, "cmds.txt")

    def test_batch_continue_on_error(self):
        """batch --continue-on-error。"""
        parser = _build_parser()
        args = parser.parse_args(["batch", "-c", "version", "--continue-on-error"])
        self.assertTrue(args.continue_on_error)

    def test_batch_dry_run(self):
        """batch --dry-run。"""
        parser = _build_parser()
        args = parser.parse_args(["batch", "-c", "version", "--dry-run"])
        self.assertTrue(args.dry_run)

    def test_batch_verbose(self):
        """batch --verbose。"""
        parser = _build_parser()
        args = parser.parse_args(["batch", "-c", "version", "--verbose"])
        self.assertTrue(args.verbose)


class TestCLIIntegration(unittest.TestCase):
    """CLI集成测试。"""

    def test_batch_inline_via_main(self):
        """agent batch -c通过main。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = main(["batch", "-c", "version"])
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_batch_file_via_main(self):
        """agent batch -f通过main。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                batch_file = os.path.join(tmpdir, "cmds.txt")
                with open(batch_file, "w") as f:
                    f.write("# 注释\nversion\n")

                with patch("sys.stdout", new_callable=io.StringIO):
                    result = main(["batch", "-f", batch_file])
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_batch_dry_run_via_main(self):
        """agent batch --dry-run通过main。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = main(["batch", "-c", "version", "--dry-run"])
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_batch_preview_via_main(self):
        """agent batch preview通过main。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = main(["batch", "preview", "-c", "version"])
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_batch_in_handlers(self):
        """batch在handlers中。"""
        parser = _build_parser()
        args = parser.parse_args(["batch"])
        self.assertEqual(args.command, "batch")

    def test_batch_in_known_commands(self):
        """batch在known_commands中。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = main(["batch", "-c", "version"])
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)


class TestShellIntegration(unittest.TestCase):
    """Shell集成测试。"""

    def test_shell_has_do_batch(self):
        """Shell有do_batch方法。"""
        from agent_core.interactive_shell import AgentShell
        self.assertTrue(hasattr(AgentShell, "do_batch"))

    def test_shell_batch_inline(self):
        """Shell执行batch -c。"""
        from agent_core.interactive_shell import AgentShell
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                shell = AgentShell()
                with patch("sys.stdout", new_callable=io.StringIO):
                    shell.do_batch("-c version")
            finally:
                os.chdir(old_cwd)

    def test_shell_batch_in_commands_list(self):
        """batch在shell_commands列表中。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO):
            shell.default("batc")  # 故意拼错
        # 应该建议batch


class TestEdgeCases(unittest.TestCase):
    """边界情况测试。"""

    def test_multiple_commands_with_mixed_operators(self):
        """混合操作符。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                executor = BatchExecutor()
                results = executor.execute([
                    "version ; template list ; version",
                ])
                self.assertEqual(len(results), 1)
            finally:
                os.chdir(old_cwd)

    def test_command_with_args(self):
        """带参数的命令。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                executor = BatchExecutor()
                results = executor.execute(["template list"])
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0].exit_code, 0)
            finally:
                os.chdir(old_cwd)

    def test_batch_file_with_comments_and_blanks(self):
        """批量文件含注释和空行。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                batch_file = os.path.join(tmpdir, "cmds.txt")
                with open(batch_file, "w") as f:
                    f.write("# 注释1\n\nversion\n\n# 注释2\ntemplate list\n")

                with patch("sys.stdout", new_callable=io.StringIO):
                    args = MagicMock(
                        file=batch_file,
                        commands=None,
                        dry_run=False,
                        continue_on_error=False,
                        verbose=False,
                    )
                    result = cmd_batch_run(args)
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_empty_command_in_chain(self):
        """命令链中的空命令。"""
        result = parse_command_chain("")
        self.assertEqual(result, [])

    def test_summary_with_failures(self):
        """含失败的摘要。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                executor = BatchExecutor(continue_on_error=True)
                executor.execute([
                    "nonexistent_xyz",
                    "version",
                ])
                summary = executor.summary()
                self.assertEqual(summary["total"], 2)
                self.assertGreaterEqual(summary["failed"], 1)
                self.assertFalse(summary["all_success"])
            finally:
                os.chdir(old_cwd)


class TestHelpMetadata(unittest.TestCase):
    """帮助元数据测试。"""

    def test_batch_in_command_metadata(self):
        """batch在COMMAND_METADATA中。"""
        from agent_core.help_cli import COMMAND_METADATA
        self.assertIn("batch", COMMAND_METADATA)

    def test_batch_has_category(self):
        """batch有分类。"""
        from agent_core.help_cli import COMMAND_METADATA
        meta = COMMAND_METADATA["batch"]
        self.assertEqual(meta["category"], "System")

    def test_batch_has_examples(self):
        """batch有示例。"""
        from agent_core.help_cli import COMMAND_METADATA
        meta = COMMAND_METADATA["batch"]
        self.assertIn("examples", meta)
        self.assertGreater(len(meta["examples"]), 0)

    def test_batch_help_via_main(self):
        """agent help batch通过main。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            result = main(["help", "batch"])
        self.assertEqual(result, 0)
        output = mock_out.getvalue()
        self.assertIn("batch", output)


class TestOperators(unittest.TestCase):
    """操作符常量测试。"""

    def test_and_operator_value(self):
        """&&操作符值。"""
        self.assertEqual(_OP_AND, "&&")

    def test_or_operator_value(self):
        """||操作符值。"""
        self.assertEqual(_OP_OR, "||")

    def test_semi_operator_value(self):
        """分号操作符值。"""
        self.assertEqual(_OP_SEMI, ";")

    def test_pipe_operator_value(self):
        """管道操作符值。"""
        self.assertEqual(_OP_PIPE, "|")


if __name__ == "__main__":
    unittest.main()
