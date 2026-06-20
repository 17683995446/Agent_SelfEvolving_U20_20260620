"""
U-13: 命令别名与快捷操作 测试。

覆盖：
- BUILTIN_ALIASES: 内置别名
- AliasManager: 别名管理器（加载/保存/增删/解析）
- resolve_alias/resolve_command_args: 别名解析
- alias CLI: list/add/remove/clear
- CLI集成: 别名解析在命令分发前
- Shell集成: do_alias命令
"""

import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from agent_core.alias_cli import (
    BUILTIN_ALIASES,
    AliasManager,
    resolve_alias,
    resolve_command_args,
    cmd_alias_list,
    cmd_alias_add,
    cmd_alias_remove,
    cmd_alias_clear,
    handle_alias,
    add_alias_subparser,
    _ALIAS_FILE,
)
from agent_core.cli import main, _build_parser


class TestBuiltinAliases(unittest.TestCase):
    """内置别名测试。"""

    def test_not_empty(self):
        """内置别名非空。"""
        self.assertGreater(len(BUILTIN_ALIASES), 0)

    def test_contains_start_alias(self):
        """包含start的别名。"""
        self.assertIn("s", BUILTIN_ALIASES)
        self.assertEqual(BUILTIN_ALIASES["s"], "start")

    def test_contains_status_alias(self):
        """包含status的别名。"""
        self.assertIn("st", BUILTIN_ALIASES)
        self.assertEqual(BUILTIN_ALIASES["st"], "status")

    def test_contains_help_alias(self):
        """包含help的别名。"""
        self.assertIn("?", BUILTIN_ALIASES)
        self.assertEqual(BUILTIN_ALIASES["?"], "help")

    def test_all_values_are_strings(self):
        """所有值都是字符串。"""
        for v in BUILTIN_ALIASES.values():
            self.assertIsInstance(v, str)

    def test_all_keys_are_strings(self):
        """所有键都是字符串。"""
        for k in BUILTIN_ALIASES.keys():
            self.assertIsInstance(k, str)


class TestAliasManager(unittest.TestCase):
    """AliasManager测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manager = AliasManager(project_dir=self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_get_builtin(self):
        """获取内置别名。"""
        builtins = self.manager.get_builtin()
        self.assertEqual(builtins, BUILTIN_ALIASES)

    def test_get_user_empty_initially(self):
        """初始用户别名为空。"""
        user = self.manager.get_user()
        self.assertEqual(user, {})

    def test_get_all_includes_builtin(self):
        """get_all包含内置别名。"""
        all_aliases = self.manager.get_all()
        for k, v in BUILTIN_ALIASES.items():
            self.assertIn(k, all_aliases)
            self.assertEqual(all_aliases[k], v)

    def test_add_user_alias(self):
        """添加用户别名。"""
        self.assertTrue(self.manager.add("go", "start"))
        self.assertEqual(self.manager.get_user()["go"], "start")

    def test_add_saves_to_file(self):
        """添加别名保存到文件。"""
        self.manager.add("go", "start")
        self.assertTrue(os.path.exists(self.manager.alias_file_path))
        with open(self.manager.alias_file_path, "r") as f:
            data = json.load(f)
        self.assertEqual(data["go"], "start")

    def test_add_cannot_override_builtin(self):
        """不能覆盖内置别名。"""
        result = self.manager.add("s", "other")
        self.assertFalse(result)

    def test_remove_user_alias(self):
        """删除用户别名。"""
        self.manager.add("go", "start")
        self.assertTrue(self.manager.remove("go"))
        self.assertNotIn("go", self.manager.get_user())

    def test_remove_builtin_fails(self):
        """删除内置别名失败。"""
        self.assertFalse(self.manager.remove("s"))

    def test_remove_nonexistent_fails(self):
        """删除不存在的别名失败。"""
        self.assertFalse(self.manager.remove("nonexistent"))

    def test_clear_all_user_aliases(self):
        """清除所有用户别名。"""
        self.manager.add("go", "start")
        self.manager.add("run", "start")
        self.assertTrue(self.manager.clear())
        self.assertEqual(self.manager.get_user(), {})

    def test_is_builtin(self):
        """检查是否内置。"""
        self.assertTrue(self.manager.is_builtin("s"))
        self.assertFalse(self.manager.is_builtin("go"))

    def test_resolve_builtin(self):
        """解析内置别名。"""
        self.assertEqual(self.manager.resolve("s"), "start")

    def test_resolve_user(self):
        """解析用户别名。"""
        self.manager.add("go", "start")
        self.assertEqual(self.manager.resolve("go"), "start")

    def test_resolve_nonexistent_returns_none(self):
        """解析不存在的别名返回None。"""
        self.assertIsNone(self.manager.resolve("nonexistent"))

    def test_resolve_chain(self):
        """解析链式别名。"""
        self.manager.add("go", "start")
        self.assertEqual(self.manager.resolve("go"), "start")

    def test_resolve_circular_returns_none(self):
        """循环引用返回None。"""
        # 手动构造循环引用
        self.manager._user_aliases = {"a": "b", "b": "a"}
        self.assertIsNone(self.manager.resolve("a"))

    def test_load_from_file(self):
        """从文件加载别名。"""
        # 先保存
        self.manager.add("go", "start")
        # 重新加载
        manager2 = AliasManager(project_dir=self.tmpdir)
        self.assertEqual(manager2.get_user().get("go"), "start")

    def test_load_invalid_json(self):
        """加载无效JSON不报错。"""
        with open(self.manager.alias_file_path, "w") as f:
            f.write("invalid json")
        manager2 = AliasManager(project_dir=self.tmpdir)
        self.assertEqual(manager2.get_user(), {})

    def test_alias_file_path(self):
        """别名文件路径正确。"""
        expected = os.path.join(self.tmpdir, _ALIAS_FILE)
        self.assertEqual(self.manager.alias_file_path, expected)


class TestResolveAlias(unittest.TestCase):
    """resolve_alias函数测试。"""

    def test_resolves_builtin(self):
        """解析内置别名。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.resolve.return_value = "start"
                result = resolve_alias("s")
                self.assertEqual(result, "start")

    def test_returns_original_if_not_alias(self):
        """非别名返回原值。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.resolve.return_value = None
                result = resolve_alias("nonexistent")
                self.assertEqual(result, "nonexistent")


class TestResolveCommandArgs(unittest.TestCase):
    """resolve_command_args测试。"""

    def test_resolves_first_token(self):
        """解析第一个token。"""
        with patch("agent_core.alias_cli.AliasManager") as MockManager:
            instance = MockManager.return_value
            instance.resolve.return_value = "start"
            result = resolve_command_args(["s", "--env", "prod"])
            self.assertEqual(result[0], "start")
            self.assertEqual(result[1], "--env")
            self.assertEqual(result[2], "prod")

    def test_preserves_remaining_args(self):
        """保留其余参数。"""
        with patch("agent_core.alias_cli.AliasManager") as MockManager:
            instance = MockManager.return_value
            instance.resolve.return_value = "start"
            result = resolve_command_args(["s", "arg1", "arg2"])
            self.assertEqual(result, ["start", "arg1", "arg2"])

    def test_no_resolution_if_not_alias(self):
        """非别名不替换。"""
        with patch("agent_core.alias_cli.AliasManager") as MockManager:
            instance = MockManager.return_value
            instance.resolve.return_value = None
            result = resolve_command_args(["nonexistent", "arg1"])
            self.assertEqual(result, ["nonexistent", "arg1"])

    def test_empty_argv(self):
        """空argv返回空。"""
        result = resolve_command_args([])
        self.assertEqual(result, [])


class TestCmdAliasList(unittest.TestCase):
    """cmd_alias_list测试。"""

    def test_returns_0(self):
        """返回0。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.get_all.return_value = dict(BUILTIN_ALIASES)
                instance.get_user.return_value = {}
                result = cmd_alias_list(MagicMock())
        self.assertEqual(result, 0)

    def test_shows_builtin_section(self):
        """显示内置别名部分。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.get_all.return_value = dict(BUILTIN_ALIASES)
                instance.get_user.return_value = {}
                cmd_alias_list(MagicMock())
        output = mock_out.getvalue()
        self.assertIn("Built-in", output)

    def test_shows_user_section(self):
        """显示用户别名部分。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.get_all.return_value = dict(BUILTIN_ALIASES)
                instance.get_user.return_value = {"go": "start"}
                cmd_alias_list(MagicMock())
        output = mock_out.getvalue()
        self.assertIn("User-defined", output)
        self.assertIn("go", output)

    def test_shows_none_when_no_user_aliases(self):
        """无用户别名时显示none。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.get_all.return_value = dict(BUILTIN_ALIASES)
                instance.get_user.return_value = {}
                cmd_alias_list(MagicMock())
        output = mock_out.getvalue()
        self.assertIn("none", output.lower())


class TestCmdAliasAdd(unittest.TestCase):
    """cmd_alias_add测试。"""

    def test_add_success(self):
        """添加成功。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                with patch("agent_core.alias_cli.AliasManager") as MockManager:
                    instance = MockManager.return_value
                    instance.is_builtin.return_value = False
                    instance.add.return_value = True
                    args = MagicMock(name="go", target="start")
                    result = cmd_alias_add(args)
            self.assertEqual(result, 0)

    def test_add_builtin_fails(self):
        """添加内置别名失败。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.is_builtin.return_value = True
                args = MagicMock(name="s", target="other")
                result = cmd_alias_add(args)
        self.assertEqual(result, 1)

    def test_add_failure(self):
        """添加失败。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.is_builtin.return_value = False
                instance.add.return_value = False
                args = MagicMock(name="go", target="start")
                result = cmd_alias_add(args)
        self.assertEqual(result, 1)


class TestCmdAliasRemove(unittest.TestCase):
    """cmd_alias_remove测试。"""

    def test_remove_success(self):
        """删除成功。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.is_builtin.return_value = False
                instance.remove.return_value = True
                args = MagicMock(name="go")
                result = cmd_alias_remove(args)
        self.assertEqual(result, 0)

    def test_remove_builtin_fails(self):
        """删除内置别名失败。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.is_builtin.return_value = True
                args = MagicMock(name="s")
                result = cmd_alias_remove(args)
        self.assertEqual(result, 1)

    def test_remove_nonexistent_fails(self):
        """删除不存在的别名失败。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.is_builtin.return_value = False
                instance.remove.return_value = False
                args = MagicMock(name="nonexistent")
                result = cmd_alias_remove(args)
        self.assertEqual(result, 1)


class TestCmdAliasClear(unittest.TestCase):
    """cmd_alias_clear测试。"""

    def test_clear_success(self):
        """清除成功。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.clear.return_value = True
                result = cmd_alias_clear(MagicMock())
        self.assertEqual(result, 0)

    def test_clear_failure(self):
        """清除失败。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.clear.return_value = False
                result = cmd_alias_clear(MagicMock())
        self.assertEqual(result, 1)


class TestHandleAlias(unittest.TestCase):
    """handle_alias测试。"""

    def test_none_action_lists(self):
        """None action执行list。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.get_all.return_value = dict(BUILTIN_ALIASES)
                instance.get_user.return_value = {}
                args = MagicMock(alias_action=None)
                result = handle_alias(args)
        self.assertEqual(result, 0)

    def test_list_action(self):
        """list action。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.alias_cli.AliasManager") as MockManager:
                instance = MockManager.return_value
                instance.get_all.return_value = dict(BUILTIN_ALIASES)
                instance.get_user.return_value = {}
                args = MagicMock(alias_action="list")
                result = handle_alias(args)
        self.assertEqual(result, 0)

    def test_unknown_action(self):
        """未知action返回1。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            args = MagicMock(alias_action="unknown")
            result = handle_alias(args)
        self.assertEqual(result, 1)


class TestAddAliasSubparser(unittest.TestCase):
    """add_alias_subparser测试。"""

    def test_alias_subparser_registered(self):
        """alias子命令已注册。"""
        parser = _build_parser()
        args = parser.parse_args(["alias"])
        self.assertEqual(args.command, "alias")

    def test_alias_list(self):
        """alias list。"""
        parser = _build_parser()
        args = parser.parse_args(["alias", "list"])
        self.assertEqual(args.alias_action, "list")

    def test_alias_add(self):
        """alias add。"""
        parser = _build_parser()
        args = parser.parse_args(["alias", "add", "go", "start"])
        self.assertEqual(args.alias_action, "add")
        self.assertEqual(args.name, "go")
        self.assertEqual(args.target, "start")

    def test_alias_remove(self):
        """alias remove。"""
        parser = _build_parser()
        args = parser.parse_args(["alias", "remove", "go"])
        self.assertEqual(args.alias_action, "remove")
        self.assertEqual(args.name, "go")

    def test_alias_clear(self):
        """alias clear。"""
        parser = _build_parser()
        args = parser.parse_args(["alias", "clear"])
        self.assertEqual(args.alias_action, "clear")


class TestCLIIntegration(unittest.TestCase):
    """CLI集成测试。"""

    def test_alias_list_via_main(self):
        """agent alias list通过main。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            result = main(["alias", "list"])
        self.assertEqual(result, 0)

    def test_alias_via_main_no_action(self):
        """agent alias（无action）通过main。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            result = main(["alias"])
        self.assertEqual(result, 0)

    def test_alias_add_remove_via_main(self):
        """agent alias add/remove通过main。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    # add
                    result = main(["alias", "add", "go", "start"])
                    self.assertEqual(result, 0)
                    # remove
                    result = main(["alias", "remove", "go"])
                    self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_alias_in_handlers(self):
        """alias在handlers中。"""
        parser = _build_parser()
        args = parser.parse_args(["alias"])
        self.assertEqual(args.command, "alias")

    def test_builtin_alias_resolves_via_main(self):
        """内置别名通过main解析。"""
        # s → start，但start需要参数会失败，但至少别名解析生效
        # 使用 v → version 更安全
        with patch("sys.stdout", new_callable=io.StringIO):
            result = main(["v"])
        self.assertEqual(result, 0)


class TestShellAliasCommand(unittest.TestCase):
    """Shell alias命令测试。"""

    def test_shell_alias_list(self):
        """Shell alias list。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO):
            shell.do_alias("list")

    def test_shell_alias_no_arg(self):
        """Shell alias无参数。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO):
            shell.do_alias("")

    def test_shell_help_includes_alias(self):
        """Shell帮助包含alias。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            shell.do_help("")
        output = mock_out.getvalue()
        self.assertIn("alias", output)


class TestEdgeCases(unittest.TestCase):
    """边界情况测试。"""

    def test_add_empty_alias_fails(self):
        """添加空别名失败。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = AliasManager(project_dir=tmpdir)
            self.assertFalse(manager.add("", "start"))
            self.assertFalse(manager.add("go", ""))

    def test_overwrite_user_alias(self):
        """覆盖已有用户别名。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = AliasManager(project_dir=tmpdir)
            manager.add("go", "start")
            manager.add("go", "status")
            self.assertEqual(manager.get_user()["go"], "status")

    def test_alias_file_persistence(self):
        """别名文件持久化。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager1 = AliasManager(project_dir=tmpdir)
            manager1.add("go", "start")
            manager1.add("run", "start")

            manager2 = AliasManager(project_dir=tmpdir)
            self.assertEqual(manager2.get_user()["go"], "start")
            self.assertEqual(manager2.get_user()["run"], "start")

    def test_resolve_after_clear(self):
        """清除后解析返回None。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = AliasManager(project_dir=tmpdir)
            manager.add("go", "start")
            self.assertEqual(manager.resolve("go"), "start")
            manager.clear()
            self.assertIsNone(manager.resolve("go"))


if __name__ == "__main__":
    unittest.main()
