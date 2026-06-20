"""
U-7: 插件管理CLI 测试。

覆盖：CLI解析、plugin list/load/info/health、错误处理、Shell集成。
"""

import asyncio
import io
import os
import tempfile
import textwrap
import unittest
from unittest.mock import patch, MagicMock

from agent_core.cli import main, _build_parser
from agent_core.plugin_cli import (
    handle_plugin,
    cmd_plugin_list,
    cmd_plugin_load,
    cmd_plugin_info,
    cmd_plugin_health,
    _find_plugin_classes,
    add_plugin_subparser,
)


# 测试用有效插件模板
_VALID_PLUGIN_TEMPLATE = '''
"""测试插件。"""
from agent_core.common.interfaces import ModuleInterface


class TestPlugin(ModuleInterface):
    """测试用插件。"""

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "test_plugin"

    async def initialize(self, config):
        self._config = config
        return True

    async def health_check(self):
        return {"status": "healthy", "checks": {"init": True}}

    async def shutdown(self):
        pass
'''

# 测试用不健康插件
_UNHEALTHY_PLUGIN_TEMPLATE = '''
"""不健康测试插件。"""
from agent_core.common.interfaces import ModuleInterface


class BadPlugin(ModuleInterface):
    """不健康插件。"""

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def module_name(self) -> str:
        return "bad_plugin"

    async def initialize(self, config):
        return True

    async def health_check(self):
        return {"status": "unhealthy", "error": "something wrong"}

    async def shutdown(self):
        pass
'''

# 非插件文件（不实现ModuleInterface）
_NON_PLUGIN_TEMPLATE = '''
"""非插件文件。"""


class NotAPlugin:
    """不是插件。"""
    pass
'''

# 导入错误文件
_IMPORT_ERROR_TEMPLATE = '''
"""导入错误文件。"""
import nonexistent_module  # noqa


class BrokenPlugin:
    pass
'''


class TestPluginCLIParser(unittest.TestCase):
    """plugin子命令解析测试。"""

    def test_plugin_command_parsed(self):
        """plugin命令解析。"""
        parser = _build_parser()
        args = parser.parse_args(["plugin"])
        self.assertEqual(args.command, "plugin")

    def test_plugin_list_parsed(self):
        """plugin list解析。"""
        parser = _build_parser()
        args = parser.parse_args(["plugin", "list"])
        self.assertEqual(args.plugin_action, "list")
        self.assertEqual(args.dir, "plugins")

    def test_plugin_list_with_dir(self):
        """plugin list带目录参数。"""
        parser = _build_parser()
        args = parser.parse_args(["plugin", "list", "--dir", "/tmp/plugs"])
        self.assertEqual(args.dir, "/tmp/plugs")

    def test_plugin_load_parsed(self):
        """plugin load解析。"""
        parser = _build_parser()
        args = parser.parse_args([
            "plugin", "load", "--file", "plug.py", "--class", "MyPlugin"
        ])
        self.assertEqual(args.plugin_action, "load")
        self.assertEqual(args.file, "plug.py")
        self.assertEqual(args.class_name, "MyPlugin")

    def test_plugin_load_short_args(self):
        """plugin load短参数。"""
        parser = _build_parser()
        args = parser.parse_args([
            "plugin", "load", "-f", "plug.py", "-c", "MyPlugin"
        ])
        self.assertEqual(args.file, "plug.py")
        self.assertEqual(args.class_name, "MyPlugin")

    def test_plugin_load_with_config(self):
        """plugin load带配置。"""
        parser = _build_parser()
        args = parser.parse_args([
            "plugin", "load", "-f", "plug.py", "-c", "MyPlugin",
            "--config", '{"key": "value"}'
        ])
        self.assertEqual(args.config, '{"key": "value"}')

    def test_plugin_info_parsed(self):
        """plugin info解析。"""
        parser = _build_parser()
        args = parser.parse_args([
            "plugin", "info", "-f", "plug.py", "-c", "MyPlugin"
        ])
        self.assertEqual(args.plugin_action, "info")

    def test_plugin_health_parsed(self):
        """plugin health解析。"""
        parser = _build_parser()
        args = parser.parse_args([
            "plugin", "health", "-f", "plug.py", "-c", "MyPlugin"
        ])
        self.assertEqual(args.plugin_action, "health")

    def test_plugin_load_requires_file(self):
        """plugin load必须有--file。"""
        parser = _build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["plugin", "load", "-c", "MyPlugin"])

    def test_plugin_load_requires_class(self):
        """plugin load必须有--class。"""
        parser = _build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["plugin", "load", "-f", "plug.py"])


class TestFindPluginClasses(unittest.TestCase):
    """_find_plugin_classes测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write_plugin(self, content, filename="test_plugin.py"):
        path = os.path.join(self.tmpdir, filename)
        with open(path, "w") as f:
            f.write(content)
        return path

    def test_find_valid_plugin(self):
        """找到有效插件类。"""
        path = self._write_plugin(_VALID_PLUGIN_TEMPLATE)
        plugins = _find_plugin_classes(path)
        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0]["class_name"], "TestPlugin")
        # module_name是property，无法不实例化获取
        self.assertIn("requires instantiation", plugins[0]["module_name"])

    def test_find_no_plugin_in_non_plugin_file(self):
        """非插件文件无结果。"""
        path = self._write_plugin(_NON_PLUGIN_TEMPLATE)
        plugins = _find_plugin_classes(path)
        self.assertEqual(len(plugins), 0)

    def test_find_returns_empty_for_missing_file(self):
        """不存在的文件返回空。"""
        plugins = _find_plugin_classes("/nonexistent/plugin.py")
        self.assertEqual(len(plugins), 0)

    def test_find_returns_empty_for_import_error(self):
        """导入错误文件返回空。"""
        path = self._write_plugin(_IMPORT_ERROR_TEMPLATE)
        plugins = _find_plugin_classes(path)
        self.assertEqual(len(plugins), 0)


class TestPluginList(unittest.TestCase):
    """plugin list命令测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # 创建有效插件
        with open(os.path.join(self.tmpdir, "good.py"), "w") as f:
            f.write(_VALID_PLUGIN_TEMPLATE)
        # 创建非插件文件
        with open(os.path.join(self.tmpdir, "bad.py"), "w") as f:
            f.write(_NON_PLUGIN_TEMPLATE)
        # 创建下划线开头文件（应被忽略）
        with open(os.path.join(self.tmpdir, "_private.py"), "w") as f:
            f.write(_VALID_PLUGIN_TEMPLATE)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_list_with_plugins(self):
        """列出有插件的目录。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(dir=self.tmpdir)
            result = cmd_plugin_list(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("good.py", output)
        self.assertIn("TestPlugin", output)

    def test_list_nonexistent_dir(self):
        """不存在的目录。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(dir="/nonexistent/plugins")
            result = cmd_plugin_list(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("not found", output)

    def test_list_empty_dir(self):
        """空目录。"""
        empty_dir = tempfile.mkdtemp()
        try:
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                args = MagicMock(dir=empty_dir)
                result = cmd_plugin_list(args)
            self.assertEqual(result, 0)
            output = mock_stdout.getvalue()
            self.assertIn("No valid plugins", output)
        finally:
            import shutil
            shutil.rmtree(empty_dir, ignore_errors=True)

    def test_list_ignores_underscore_files(self):
        """忽略下划线开头文件。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(dir=self.tmpdir)
            result = cmd_plugin_list(args)
        output = mock_stdout.getvalue()
        self.assertNotIn("_private.py", output)


class TestPluginLoad(unittest.TestCase):
    """plugin load命令测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.valid_plugin = os.path.join(self.tmpdir, "good.py")
        with open(self.valid_plugin, "w") as f:
            f.write(_VALID_PLUGIN_TEMPLATE)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_load_valid_plugin(self):
        """加载有效插件。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.valid_plugin,
                class_name="TestPlugin",
                config=None,
            )
            result = cmd_plugin_load(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Plugin loaded", output)
        self.assertIn("healthy", output)

    def test_load_with_config(self):
        """带配置加载。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.valid_plugin,
                class_name="TestPlugin",
                config='{"name": "test"}',
            )
            result = cmd_plugin_load(args)
        self.assertEqual(result, 0)

    def test_load_file_not_found(self):
        """文件不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                file="/nonexistent.py",
                class_name="TestPlugin",
                config=None,
            )
            result = cmd_plugin_load(args)
        self.assertEqual(result, 1)

    def test_load_invalid_class(self):
        """类不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                file=self.valid_plugin,
                class_name="NonExistentClass",
                config=None,
            )
            result = cmd_plugin_load(args)
        self.assertEqual(result, 1)

    def test_load_invalid_config_json(self):
        """无效配置JSON。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                file=self.valid_plugin,
                class_name="TestPlugin",
                config="{invalid json}",
            )
            result = cmd_plugin_load(args)
        self.assertEqual(result, 1)

    def test_load_missing_file_arg(self):
        """缺少file参数。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(file=None, class_name="TestPlugin", config=None)
            result = cmd_plugin_load(args)
        self.assertEqual(result, 1)

    def test_load_missing_class_arg(self):
        """缺少class参数。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(file=self.valid_plugin, class_name=None, config=None)
            result = cmd_plugin_load(args)
        self.assertEqual(result, 1)


class TestPluginInfo(unittest.TestCase):
    """plugin info命令测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.valid_plugin = os.path.join(self.tmpdir, "good.py")
        with open(self.valid_plugin, "w") as f:
            f.write(_VALID_PLUGIN_TEMPLATE)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_info_valid_plugin(self):
        """查看有效插件信息。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.valid_plugin,
                class_name="TestPlugin",
            )
            result = cmd_plugin_info(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Plugin Info", output)
        self.assertIn("TestPlugin", output)
        # module_name是property，info命令显示需要实例化
        self.assertIn("requires instantiation", output)

    def test_info_file_not_found(self):
        """文件不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                file="/nonexistent.py",
                class_name="TestPlugin",
            )
            result = cmd_plugin_info(args)
        self.assertEqual(result, 1)

    def test_info_class_not_found(self):
        """类不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                file=self.valid_plugin,
                class_name="NonExistentClass",
            )
            result = cmd_plugin_info(args)
        self.assertEqual(result, 1)

    def test_info_missing_args(self):
        """缺少参数。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(file=None, class_name="TestPlugin")
            result = cmd_plugin_info(args)
        self.assertEqual(result, 1)


class TestPluginHealth(unittest.TestCase):
    """plugin health命令测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.valid_plugin = os.path.join(self.tmpdir, "good.py")
        with open(self.valid_plugin, "w") as f:
            f.write(_VALID_PLUGIN_TEMPLATE)
        self.unhealthy_plugin = os.path.join(self.tmpdir, "bad.py")
        with open(self.unhealthy_plugin, "w") as f:
            f.write(_UNHEALTHY_PLUGIN_TEMPLATE)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_health_healthy_plugin(self):
        """健康插件检查。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            args = MagicMock(
                file=self.valid_plugin,
                class_name="TestPlugin",
                config=None,
            )
            result = cmd_plugin_health(args)
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("healthy", output)

    def test_health_unhealthy_plugin(self):
        """不健康插件检查。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout, \
             patch("sys.stderr", new_callable=io.StringIO) as mock_stderr:
            args = MagicMock(
                file=self.unhealthy_plugin,
                class_name="BadPlugin",
                config=None,
            )
            result = cmd_plugin_health(args)
        self.assertEqual(result, 1)
        # "unhealthy"状态通过_print_error输出到stderr
        combined = mock_stdout.getvalue() + mock_stderr.getvalue()
        self.assertIn("unhealthy", combined)

    def test_health_file_not_found(self):
        """文件不存在。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(
                file="/nonexistent.py",
                class_name="TestPlugin",
                config=None,
            )
            result = cmd_plugin_health(args)
        self.assertEqual(result, 1)

    def test_health_missing_args(self):
        """缺少参数。"""
        with patch("sys.stderr", new_callable=io.StringIO):
            args = MagicMock(file=None, class_name=None, config=None)
            result = cmd_plugin_health(args)
        self.assertEqual(result, 1)


class TestPluginHandleDispatch(unittest.TestCase):
    """handle_plugin分发测试。"""

    def test_handle_list_action(self):
        """分发到list。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            args = MagicMock(
                plugin_action="list", dir="/nonexistent"
            )
            result = handle_plugin(args)
        self.assertEqual(result, 0)

    def test_handle_none_action_defaults_list(self):
        """无action时默认list。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            args = MagicMock(plugin_action=None, dir="/nonexistent")
            result = handle_plugin(args)
        self.assertEqual(result, 0)

    def test_handle_unknown_action(self):
        """未知action。"""
        args = MagicMock(plugin_action="unknown")
        with patch("sys.stderr", new_callable=io.StringIO):
            result = handle_plugin(args)
        self.assertEqual(result, 1)


class TestPluginCLIIntegration(unittest.TestCase):
    """CLI集成测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.valid_plugin = os.path.join(self.tmpdir, "good.py")
        with open(self.valid_plugin, "w") as f:
            f.write(_VALID_PLUGIN_TEMPLATE)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_cli_plugin_list_via_main(self):
        """通过main调用plugin list。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = main(["plugin", "list", "--dir", self.tmpdir])
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("good.py", output)

    def test_cli_plugin_info_via_main(self):
        """通过main调用plugin info。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = main([
                "plugin", "info",
                "--file", self.valid_plugin,
                "--class", "TestPlugin",
            ])
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("TestPlugin", output)

    def test_cli_plugin_load_via_main(self):
        """通过main调用plugin load。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            result = main([
                "plugin", "load",
                "--file", self.valid_plugin,
                "--class", "TestPlugin",
            ])
        self.assertEqual(result, 0)
        output = mock_stdout.getvalue()
        self.assertIn("Plugin loaded", output)


class TestShellPluginCommand(unittest.TestCase):
    """Shell plugin命令测试。"""

    def test_shell_plugin_help(self):
        """Shell plugin命令有帮助。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell(port=19999)
        self.assertTrue(hasattr(shell, "do_plugin"))
        doc = shell.do_plugin.__doc__
        self.assertIsNotNone(doc)
        self.assertIn("plugin", doc.lower())

    def test_shell_plugin_list(self):
        """Shell plugin list执行。"""
        from agent_core.interactive_shell import AgentShell
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "good.py"), "w") as f:
                f.write(_VALID_PLUGIN_TEMPLATE)
            shell = AgentShell(port=19999)
            with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
                shell.do_plugin(f"list --dir {tmpdir}")
            output = mock_stdout.getvalue()
            self.assertIn("good.py", output)

    def test_shell_help_includes_plugin(self):
        """Shell帮助包含plugin。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell(port=19999)
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            shell.do_help("")
        output = mock_stdout.getvalue()
        self.assertIn("Plugins", output)
        self.assertIn("plugin", output)


if __name__ == "__main__":
    unittest.main()
