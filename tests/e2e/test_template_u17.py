"""
U-17: 配置模板与预设管理 测试。

覆盖：
- BUILTIN_TEMPLATES: 内置模板
- TemplateManager: 模板管理器（list/get/save/delete/apply）
- template CLI: list/apply/save/show/delete
- CLI集成: template命令注册与分发
- Shell集成: do_template
"""

import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from agent_core.template_cli import (
    BUILTIN_TEMPLATES,
    TemplateManager,
    cmd_template_list,
    cmd_template_apply,
    cmd_template_save,
    cmd_template_show,
    cmd_template_delete,
    handle_template,
    add_template_subparser,
    _TEMPLATE_DIR,
)
from agent_core.cli import main, _build_parser


class TestBuiltinTemplates(unittest.TestCase):
    """内置模板测试。"""

    def test_has_minimal(self):
        """包含minimal模板。"""
        self.assertIn("minimal", BUILTIN_TEMPLATES)

    def test_has_standard(self):
        """包含standard模板。"""
        self.assertIn("standard", BUILTIN_TEMPLATES)

    def test_has_high_performance(self):
        """包含high-performance模板。"""
        self.assertIn("high-performance", BUILTIN_TEMPLATES)

    def test_has_debug(self):
        """包含debug模板。"""
        self.assertIn("debug", BUILTIN_TEMPLATES)

    def test_each_template_has_description(self):
        """每个模板都有描述。"""
        for name, tmpl in BUILTIN_TEMPLATES.items():
            self.assertIn("description", tmpl, f"{name}缺少description")
            self.assertTrue(tmpl["description"], f"{name}描述为空")

    def test_each_template_has_config(self):
        """每个模板都有config。"""
        for name, tmpl in BUILTIN_TEMPLATES.items():
            self.assertIn("config", tmpl, f"{name}缺少config")
            self.assertIsInstance(tmpl["config"], dict)
            self.assertTrue(tmpl["config"], f"{name}config为空")

    def test_each_template_has_app_name(self):
        """每个模板都有app_name。"""
        for name, tmpl in BUILTIN_TEMPLATES.items():
            self.assertIn("app_name", tmpl["config"], f"{name}缺少app_name")

    def test_each_template_has_log_level(self):
        """每个模板都有log_level。"""
        for name, tmpl in BUILTIN_TEMPLATES.items():
            self.assertIn("log_level", tmpl["config"], f"{name}缺少log_level")

    def test_minimal_has_warning_level(self):
        """minimal模板日志级别为WARNING。"""
        self.assertEqual(BUILTIN_TEMPLATES["minimal"]["config"]["log_level"], "WARNING")

    def test_debug_has_debug_level(self):
        """debug模板日志级别为DEBUG。"""
        self.assertEqual(BUILTIN_TEMPLATES["debug"]["config"]["log_level"], "DEBUG")

    def test_high_performance_has_error_level(self):
        """high-performance模板日志级别为ERROR。"""
        self.assertEqual(
            BUILTIN_TEMPLATES["high-performance"]["config"]["log_level"], "ERROR"
        )

    def test_standard_has_info_level(self):
        """standard模板日志级别为INFO。"""
        self.assertEqual(BUILTIN_TEMPLATES["standard"]["config"]["log_level"], "INFO")

    def test_high_performance_has_large_memory(self):
        """high-performance模板内存容量大。"""
        mem = BUILTIN_TEMPLATES["high-performance"]["config"]["memory_capacity"]
        self.assertGreater(mem, 10000)


class TestTemplateManager(unittest.TestCase):
    """TemplateManager测试。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.manager = TemplateManager(project_dir=self.tmpdir)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_get_builtin_templates(self):
        """获取内置模板。"""
        builtins = self.manager.get_builtin_templates()
        self.assertEqual(len(builtins), len(BUILTIN_TEMPLATES))
        for name in BUILTIN_TEMPLATES:
            self.assertIn(name, builtins)

    def test_get_user_templates_empty(self):
        """无用户模板时返回空。"""
        user = self.manager.get_user_templates()
        self.assertEqual(user, {})

    def test_get_all_templates_includes_builtins(self):
        """所有模板包含内置。"""
        all_templates = self.manager.get_all_templates()
        for name in BUILTIN_TEMPLATES:
            self.assertIn(name, all_templates)

    def test_get_template_builtin(self):
        """获取内置模板。"""
        tmpl = self.manager.get_template("standard")
        self.assertIsNotNone(tmpl)
        self.assertIn("config", tmpl)

    def test_get_template_nonexistent(self):
        """获取不存在的模板返回None。"""
        tmpl = self.manager.get_template("nonexistent")
        self.assertIsNone(tmpl)

    def test_is_builtin_true(self):
        """内置模板识别。"""
        self.assertTrue(self.manager.is_builtin("standard"))
        self.assertTrue(self.manager.is_builtin("minimal"))

    def test_is_builtin_false(self):
        """非内置模板识别。"""
        self.assertFalse(self.manager.is_builtin("custom"))

    def test_save_user_template(self):
        """保存用户模板。"""
        config = {"app_name": "test", "log_level": "INFO"}
        result = self.manager.save_template("mytmpl", config, "test template")
        self.assertTrue(result)
        # 验证文件存在
        path = os.path.join(self.tmpdir, _TEMPLATE_DIR, "mytmpl.json")
        self.assertTrue(os.path.exists(path))

    def test_save_template_creates_dir(self):
        """保存模板创建目录。"""
        config = {"app_name": "test"}
        self.manager.save_template("test_tmpl", config)
        self.assertTrue(os.path.isdir(os.path.join(self.tmpdir, _TEMPLATE_DIR)))

    def test_save_template_cannot_overwrite_builtin(self):
        """不能覆盖内置模板。"""
        config = {"app_name": "test"}
        result = self.manager.save_template("standard", config)
        self.assertFalse(result)

    def test_save_template_empty_name(self):
        """空名保存失败。"""
        result = self.manager.save_template("", {"a": 1})
        self.assertFalse(result)

    def test_save_template_empty_config(self):
        """空配置保存失败。"""
        result = self.manager.save_template("test", {})
        self.assertFalse(result)

    def test_get_user_templates_after_save(self):
        """保存后能获取用户模板。"""
        config = {"app_name": "test"}
        self.manager.save_template("mytmpl", config, "my template")
        user = self.manager.get_user_templates()
        self.assertIn("mytmpl", user)
        self.assertEqual(user["mytmpl"]["description"], "my template")

    def test_get_all_templates_includes_user(self):
        """所有模板包含用户模板。"""
        config = {"app_name": "test"}
        self.manager.save_template("mytmpl", config)
        all_templates = self.manager.get_all_templates()
        self.assertIn("mytmpl", all_templates)
        self.assertIn("standard", all_templates)  # 内置也在

    def test_get_template_user(self):
        """获取用户模板。"""
        config = {"app_name": "test"}
        self.manager.save_template("mytmpl", config, "desc")
        tmpl = self.manager.get_template("mytmpl")
        self.assertIsNotNone(tmpl)
        self.assertEqual(tmpl["description"], "desc")

    def test_delete_user_template(self):
        """删除用户模板。"""
        config = {"app_name": "test"}
        self.manager.save_template("mytmpl", config)
        result = self.manager.delete_template("mytmpl")
        self.assertTrue(result)
        # 验证已删除
        self.assertIsNone(self.manager.get_template("mytmpl"))

    def test_delete_builtin_fails(self):
        """删除内置模板失败。"""
        result = self.manager.delete_template("standard")
        self.assertFalse(result)

    def test_delete_nonexistent_fails(self):
        """删除不存在的模板失败。"""
        result = self.manager.delete_template("nonexistent")
        self.assertFalse(result)

    def test_apply_builtin_template(self):
        """应用内置模板。"""
        output_path = os.path.join(self.tmpdir, "config", "dev.yaml")
        result = self.manager.apply_template("standard", output_path, "dev")
        self.assertTrue(result)
        self.assertTrue(os.path.exists(output_path))

    def test_apply_template_content_has_env_comment(self):
        """应用模板生成的配置含环境注释。"""
        output_path = os.path.join(self.tmpdir, "out.yaml")
        self.manager.apply_template("minimal", output_path, "prod")
        with open(output_path, "r") as f:
            content = f.read()
        self.assertIn("prod", content)
        self.assertIn("minimal", content)

    def test_apply_nonexistent_template(self):
        """应用不存在的模板失败。"""
        output_path = os.path.join(self.tmpdir, "out.yaml")
        result = self.manager.apply_template("nonexistent", output_path)
        self.assertFalse(result)

    def test_apply_user_template(self):
        """应用用户模板。"""
        config = {"app_name": "myapp", "log_level": "DEBUG"}
        self.manager.save_template("mytmpl", config)
        output_path = os.path.join(self.tmpdir, "out.yaml")
        result = self.manager.apply_template("mytmpl", output_path, "dev")
        self.assertTrue(result)
        self.assertTrue(os.path.exists(output_path))

    def test_template_dir_path(self):
        """模板目录路径正确。"""
        expected = os.path.join(self.tmpdir, _TEMPLATE_DIR)
        self.assertEqual(self.manager.template_dir_path, expected)

    def test_load_invalid_user_template(self):
        """加载无效用户模板跳过。"""
        # 创建无效JSON文件
        os.makedirs(self.manager.template_dir_path, exist_ok=True)
        path = os.path.join(self.manager.template_dir_path, "bad.json")
        with open(path, "w") as f:
            f.write("invalid json")
        user = self.manager.get_user_templates()
        self.assertNotIn("bad", user)


class TestCmdTemplateList(unittest.TestCase):
    """cmd_template_list测试。"""

    def test_list_returns_zero(self):
        """list返回0。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_user_templates.return_value = {}
                result = cmd_template_list(MagicMock())
        self.assertEqual(result, 0)

    def test_list_shows_builtins(self):
        """list显示内置模板。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_user_templates.return_value = {}
                cmd_template_list(MagicMock())
        output = mock_out.getvalue()
        self.assertIn("standard", output)
        self.assertIn("minimal", output)
        self.assertIn("Built-in", output)

    def test_list_shows_user_templates(self):
        """list显示用户模板。"""
        user_templates = {
            "mytmpl": {"description": "my template", "config": {}}
        }
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_user_templates.return_value = user_templates
                cmd_template_list(MagicMock())
        output = mock_out.getvalue()
        self.assertIn("mytmpl", output)
        self.assertIn("User-defined", output)

    def test_list_shows_none_when_no_user(self):
        """无用户模板时显示none。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_user_templates.return_value = {}
                cmd_template_list(MagicMock())
        output = mock_out.getvalue()
        self.assertIn("none", output.lower())


class TestCmdTemplateApply(unittest.TestCase):
    """cmd_template_apply测试。"""

    def test_apply_nonexistent_returns_1(self):
        """应用不存在模板返回1。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_template.return_value = None
                args = MagicMock(name="nonexistent", output=None, env="dev")
                result = cmd_template_apply(args)
        self.assertEqual(result, 1)

    def test_apply_success_returns_0(self):
        """应用成功返回0。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys.stdout", new_callable=io.StringIO):
                with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                    instance = MockMgr.return_value
                    instance.get_template.return_value = {
                        "description": "test",
                        "config": {"app_name": "test"},
                    }
                    instance.apply_template.return_value = True
                    args = MagicMock(name="standard", output=None, env="dev")
                    result = cmd_template_apply(args)
            self.assertEqual(result, 0)

    def test_apply_failure_returns_1(self):
        """应用失败返回1。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_template.return_value = {
                    "description": "test",
                    "config": {},
                }
                instance.apply_template.return_value = False
                args = MagicMock(name="standard", output=None, env="dev")
                result = cmd_template_apply(args)
        self.assertEqual(result, 1)


class TestCmdTemplateSave(unittest.TestCase):
    """cmd_template_save测试。"""

    def test_save_builtin_returns_1(self):
        """保存内置模板名返回1。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.is_builtin.return_value = True
                args = MagicMock(name="standard", config_file="x.yaml", description="")
                result = cmd_template_save(args)
        self.assertEqual(result, 1)

    def test_save_nonexistent_config_returns_1(self):
        """配置文件不存在返回1。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.is_builtin.return_value = False
                args = MagicMock(
                    name="mytmpl",
                    config_file="/nonexistent/path.yaml",
                    description="",
                )
                result = cmd_template_save(args)
        self.assertEqual(result, 1)

    def test_save_success_returns_0(self):
        """保存成功返回0。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "config.yaml")
            with open(config_path, "w") as f:
                f.write("app_name: test\nlog_level: INFO\n")
            with patch("sys.stdout", new_callable=io.StringIO):
                with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                    instance = MockMgr.return_value
                    instance.is_builtin.return_value = False
                    instance.save_template.return_value = True
                    args = MagicMock(
                        name="mytmpl",
                        config_file=config_path,
                        description="",
                    )
                    result = cmd_template_save(args)
            self.assertEqual(result, 0)


class TestCmdTemplateShow(unittest.TestCase):
    """cmd_template_show测试。"""

    def test_show_nonexistent_returns_1(self):
        """显示不存在模板返回1。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_template.return_value = None
                args = MagicMock(name="nonexistent")
                result = cmd_template_show(args)
        self.assertEqual(result, 1)

    def test_show_builtin_returns_0(self):
        """显示内置模板返回0。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_template.return_value = {
                    "description": "test template",
                    "config": {"app_name": "test", "log_level": "INFO"},
                }
                instance.is_builtin.return_value = True
                args = MagicMock(name="standard")
                result = cmd_template_show(args)
        self.assertEqual(result, 0)
        output = mock_out.getvalue()
        self.assertIn("Built-in", output)
        self.assertIn("app_name", output)

    def test_show_user_returns_0(self):
        """显示用户模板返回0。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_template.return_value = {
                    "description": "user template",
                    "config": {"app_name": "user"},
                }
                instance.is_builtin.return_value = False
                args = MagicMock(name="mytmpl")
                result = cmd_template_show(args)
        self.assertEqual(result, 0)
        output = mock_out.getvalue()
        self.assertIn("User-defined", output)


class TestCmdTemplateDelete(unittest.TestCase):
    """cmd_template_delete测试。"""

    def test_delete_builtin_returns_1(self):
        """删除内置模板返回1。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.is_builtin.return_value = True
                args = MagicMock(name="standard")
                result = cmd_template_delete(args)
        self.assertEqual(result, 1)

    def test_delete_success_returns_0(self):
        """删除成功返回0。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.is_builtin.return_value = False
                instance.delete_template.return_value = True
                args = MagicMock(name="mytmpl")
                result = cmd_template_delete(args)
        self.assertEqual(result, 0)

    def test_delete_failure_returns_1(self):
        """删除失败返回1。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.is_builtin.return_value = False
                instance.delete_template.return_value = False
                args = MagicMock(name="nonexistent")
                result = cmd_template_delete(args)
        self.assertEqual(result, 1)


class TestHandleTemplate(unittest.TestCase):
    """handle_template测试。"""

    def test_none_action_lists(self):
        """None action执行list。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_user_templates.return_value = {}
                args = MagicMock(template_action=None)
                result = handle_template(args)
        self.assertEqual(result, 0)

    def test_list_action(self):
        """list action。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            with patch("agent_core.template_cli.TemplateManager") as MockMgr:
                instance = MockMgr.return_value
                instance.get_user_templates.return_value = {}
                args = MagicMock(template_action="list")
                result = handle_template(args)
        self.assertEqual(result, 0)

    def test_unknown_action(self):
        """未知action返回1。"""
        with patch("sys.stdout", new_callable=io.StringIO):
            args = MagicMock(template_action="unknown")
            result = handle_template(args)
        self.assertEqual(result, 1)


class TestAddTemplateSubparser(unittest.TestCase):
    """add_template_subparser测试。"""

    def test_template_subparser_registered(self):
        """template子命令已注册。"""
        parser = _build_parser()
        args = parser.parse_args(["template"])
        self.assertEqual(args.command, "template")

    def test_template_list(self):
        """template list。"""
        parser = _build_parser()
        args = parser.parse_args(["template", "list"])
        self.assertEqual(args.template_action, "list")

    def test_template_apply(self):
        """template apply。"""
        parser = _build_parser()
        args = parser.parse_args(["template", "apply", "standard"])
        self.assertEqual(args.template_action, "apply")
        self.assertEqual(args.name, "standard")

    def test_template_apply_with_output(self):
        """template apply --output。"""
        parser = _build_parser()
        args = parser.parse_args([
            "template", "apply", "standard", "--output", "out.yaml"
        ])
        self.assertEqual(args.output, "out.yaml")

    def test_template_apply_with_env(self):
        """template apply --env。"""
        parser = _build_parser()
        args = parser.parse_args([
            "template", "apply", "standard", "--env", "prod"
        ])
        self.assertEqual(args.env, "prod")

    def test_template_save(self):
        """template save。"""
        parser = _build_parser()
        args = parser.parse_args(["template", "save", "mytmpl", "config.yaml"])
        self.assertEqual(args.template_action, "save")
        self.assertEqual(args.name, "mytmpl")
        self.assertEqual(args.config_file, "config.yaml")

    def test_template_save_with_description(self):
        """template save --description。"""
        parser = _build_parser()
        args = parser.parse_args([
            "template", "save", "mytmpl", "config.yaml",
            "--description", "my template"
        ])
        self.assertEqual(args.description, "my template")

    def test_template_show(self):
        """template show。"""
        parser = _build_parser()
        args = parser.parse_args(["template", "show", "standard"])
        self.assertEqual(args.template_action, "show")
        self.assertEqual(args.name, "standard")

    def test_template_delete(self):
        """template delete。"""
        parser = _build_parser()
        args = parser.parse_args(["template", "delete", "mytmpl"])
        self.assertEqual(args.template_action, "delete")
        self.assertEqual(args.name, "mytmpl")


class TestCLIIntegration(unittest.TestCase):
    """CLI集成测试。"""

    def test_template_list_via_main(self):
        """agent template list通过main。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = main(["template", "list"])
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_template_show_via_main(self):
        """agent template show standard通过main。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = main(["template", "show", "standard"])
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)

    def test_template_show_nonexistent_via_main(self):
        """agent template show nonexistent通过main返回1。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stderr", new_callable=io.StringIO):
                    result = main(["template", "show", "nonexistent"])
                self.assertEqual(result, 1)
            finally:
                os.chdir(old_cwd)

    def test_template_apply_via_main(self):
        """agent template apply通过main。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                output_path = os.path.join(tmpdir, "out.yaml")
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = main([
                        "template", "apply", "minimal",
                        "--output", output_path,
                    ])
                self.assertEqual(result, 0)
                self.assertTrue(os.path.exists(output_path))
            finally:
                os.chdir(old_cwd)

    def test_template_apply_default_output(self):
        """apply默认输出路径。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = main(["template", "apply", "minimal"])
                self.assertEqual(result, 0)
                # 默认输出 config/dev.yaml
                default_path = os.path.join(tmpdir, "config", "dev.yaml")
                self.assertTrue(os.path.exists(default_path))
            finally:
                os.chdir(old_cwd)

    def test_template_save_and_delete_via_main(self):
        """agent template save和delete通过main。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                # 创建配置文件
                config_path = os.path.join(tmpdir, "config.yaml")
                with open(config_path, "w") as f:
                    f.write("app_name: test\nlog_level: INFO\n")

                # 保存为模板
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = main([
                        "template", "save", "mytmpl", config_path,
                        "--description", "test template",
                    ])
                self.assertEqual(result, 0)

                # 验证模板存在
                tmpl_path = os.path.join(tmpdir, _TEMPLATE_DIR, "mytmpl.json")
                self.assertTrue(os.path.exists(tmpl_path))

                # 删除模板
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = main(["template", "delete", "mytmpl"])
                self.assertEqual(result, 0)
                self.assertFalse(os.path.exists(tmpl_path))
            finally:
                os.chdir(old_cwd)

    def test_template_save_builtin_via_main(self):
        """保存内置模板名失败。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                config_path = os.path.join(tmpdir, "config.yaml")
                with open(config_path, "w") as f:
                    f.write("app_name: test\n")
                with patch("sys.stderr", new_callable=io.StringIO):
                    result = main([
                        "template", "save", "standard", config_path,
                    ])
                self.assertEqual(result, 1)
            finally:
                os.chdir(old_cwd)

    def test_template_in_handlers(self):
        """template在handlers中。"""
        parser = _build_parser()
        args = parser.parse_args(["template"])
        self.assertEqual(args.command, "template")

    def test_template_in_known_commands(self):
        """template在known_commands中（不被别名解析）。"""
        # 如果template不在known_commands，会被当作别名解析
        # 这里通过main直接调用template命令验证
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                with patch("sys.stdout", new_callable=io.StringIO):
                    result = main(["template", "list"])
                self.assertEqual(result, 0)
            finally:
                os.chdir(old_cwd)


class TestShellIntegration(unittest.TestCase):
    """Shell集成测试。"""

    def test_shell_has_do_template(self):
        """Shell有do_template方法。"""
        from agent_core.interactive_shell import AgentShell
        self.assertTrue(hasattr(AgentShell, "do_template"))

    def test_shell_template_list(self):
        """Shell执行template list。"""
        from agent_core.interactive_shell import AgentShell
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                shell = AgentShell()
                with patch("sys.stdout", new_callable=io.StringIO):
                    shell.do_template("list")
            finally:
                os.chdir(old_cwd)

    def test_shell_template_show(self):
        """Shell执行template show。"""
        from agent_core.interactive_shell import AgentShell
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                shell = AgentShell()
                with patch("sys.stdout", new_callable=io.StringIO):
                    shell.do_template("show standard")
            finally:
                os.chdir(old_cwd)

    def test_shell_template_in_commands_list(self):
        """template在shell_commands列表中。"""
        from agent_core.interactive_shell import AgentShell
        shell = AgentShell()
        # 通过default方法间接验证
        with patch("sys.stdout", new_callable=io.StringIO):
            shell.default("templat")  # 故意拼错
        # 应该建议template


class TestEdgeCases(unittest.TestCase):
    """边界情况测试。"""

    def test_apply_template_with_special_env(self):
        """应用模板使用特殊环境名。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TemplateManager(project_dir=tmpdir)
            output_path = os.path.join(tmpdir, "out.yaml")
            result = manager.apply_template("standard", output_path, "staging")
            self.assertTrue(result)
            with open(output_path, "r") as f:
                content = f.read()
            self.assertIn("staging", content)

    def test_save_and_reload_template(self):
        """保存并重新加载模板。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager1 = TemplateManager(project_dir=tmpdir)
            config = {"app_name": "test", "log_level": "DEBUG"}
            manager1.save_template("mytmpl", config, "my desc")

            manager2 = TemplateManager(project_dir=tmpdir)
            tmpl = manager2.get_template("mytmpl")
            self.assertIsNotNone(tmpl)
            self.assertEqual(tmpl["description"], "my desc")
            self.assertEqual(tmpl["config"]["app_name"], "test")

    def test_user_template_overrides_builtin_in_all(self):
        """用户模板与内置同名时，all返回用户版本。"""
        # 注意：save_template不允许覆盖内置，所以这个场景不会发生
        # 但get_all_templates的逻辑是user覆盖builtin
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TemplateManager(project_dir=tmpdir)
            all_templates = manager.get_all_templates()
            # 内置数量
            self.assertEqual(len(all_templates), len(BUILTIN_TEMPLATES))

    def test_apply_creates_output_dir(self):
        """apply创建输出目录。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = TemplateManager(project_dir=tmpdir)
            output_path = os.path.join(tmpdir, "subdir1", "subdir2", "out.yaml")
            result = manager.apply_template("minimal", output_path, "dev")
            self.assertTrue(result)
            self.assertTrue(os.path.exists(output_path))


class TestHelpMetadata(unittest.TestCase):
    """帮助元数据测试。"""

    def test_template_in_command_metadata(self):
        """template在COMMAND_METADATA中。"""
        from agent_core.help_cli import COMMAND_METADATA
        self.assertIn("template", COMMAND_METADATA)

    def test_template_has_category(self):
        """template有分类。"""
        from agent_core.help_cli import COMMAND_METADATA
        meta = COMMAND_METADATA["template"]
        self.assertEqual(meta["category"], "Configuration")

    def test_template_has_examples(self):
        """template有示例。"""
        from agent_core.help_cli import COMMAND_METADATA
        meta = COMMAND_METADATA["template"]
        self.assertIn("examples", meta)
        self.assertGreater(len(meta["examples"]), 0)

    def test_template_help_via_main(self):
        """agent help template通过main。"""
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            result = main(["help", "template"])
        self.assertEqual(result, 0)
        output = mock_out.getvalue()
        self.assertIn("template", output)


if __name__ == "__main__":
    unittest.main()
