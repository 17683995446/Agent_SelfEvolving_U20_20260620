"""
U-5: 快速启动向导与项目脚手架 测试。

覆盖：脚手架生成、配置模板、启动脚本、示例代码、README。
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from agent_core.project_scaffolder import (
    ProjectScaffolder,
    scaffold_project,
    _CONFIG_TEMPLATE,
    _START_SCRIPT_TEMPLATE,
    _EXAMPLE_TEMPLATE,
    _README_TEMPLATE,
    _ENV_PRESETS,
)


class TestScaffolderGeneration(unittest.TestCase):
    """脚手架生成测试。"""

    def setUp(self):
        self.scaffolder = ProjectScaffolder()

    def test_generate_creates_directory_structure(self):
        """生成创建目录结构。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "test_project")
            result = self.scaffolder.generate(
                project, app_name="test_app", interactive=False
            )
            self.assertTrue(result)
            self.assertTrue(os.path.isdir(project))
            self.assertTrue(os.path.isdir(os.path.join(project, "config")))
            self.assertTrue(os.path.isdir(os.path.join(project, "scripts")))
            self.assertTrue(os.path.isdir(os.path.join(project, "examples")))
            self.assertTrue(os.path.isdir(os.path.join(project, "logs")))

    def test_generate_creates_config_files(self):
        """生成配置文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "test_project")
            self.scaffolder.generate(
                project, app_name="test_app", interactive=False
            )
            config_dir = os.path.join(project, "config")
            self.assertTrue(os.path.exists(os.path.join(config_dir, "base.yaml")))
            self.assertTrue(os.path.exists(os.path.join(config_dir, "dev.yaml")))
            self.assertTrue(os.path.exists(os.path.join(config_dir, "prod.yaml")))
            self.assertTrue(os.path.exists(os.path.join(config_dir, "test.yaml")))

    def test_generate_creates_start_script(self):
        """生成启动脚本。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "test_project")
            self.scaffolder.generate(
                project, app_name="test_app", env="dev", interactive=False
            )
            start_script = os.path.join(project, "scripts", "start.sh")
            self.assertTrue(os.path.exists(start_script))
            # 检查可执行权限
            self.assertTrue(os.access(start_script, os.X_OK))

    def test_generate_creates_example(self):
        """生成示例代码。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "test_project")
            self.scaffolder.generate(
                project, app_name="test_app", interactive=False
            )
            example = os.path.join(project, "examples", "main.py")
            self.assertTrue(os.path.exists(example))

    def test_generate_creates_readme(self):
        """生成README。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "test_project")
            self.scaffolder.generate(
                project, app_name="test_app", interactive=False
            )
            readme = os.path.join(project, "README.md")
            self.assertTrue(os.path.exists(readme))

    def test_generate_creates_requirements(self):
        """生成requirements.txt。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "test_project")
            self.scaffolder.generate(
                project, app_name="test_app", interactive=False
            )
            req = os.path.join(project, "requirements.txt")
            self.assertTrue(os.path.exists(req))
            with open(req) as f:
                content = f.read()
            self.assertIn("numpy", content)
            self.assertIn("psutil", content)

    def test_generate_returns_true_on_success(self):
        """成功生成返回True。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "test_project")
            result = self.scaffolder.generate(
                project, interactive=False
            )
            self.assertTrue(result)

    def test_generate_with_custom_app_name(self):
        """自定义应用名称。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "test_project")
            self.scaffolder.generate(
                project, app_name="my_custom_agent", interactive=False
            )
            # 检查配置文件中包含自定义名称
            with open(os.path.join(project, "config", "dev.yaml")) as f:
                content = f.read()
            self.assertIn("my_custom_agent", content)

    def test_generate_with_different_envs(self):
        """不同环境生成不同配置。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "test_project")
            self.scaffolder.generate(
                project, app_name="test", env="prod", interactive=False
            )
            # 检查启动脚本使用prod环境
            with open(os.path.join(project, "scripts", "start.sh")) as f:
                content = f.read()
            self.assertIn("prod", content)


class TestConfigTemplate(unittest.TestCase):
    """配置模板测试。"""

    def test_config_template_has_required_keys(self):
        """配置模板包含必需键。"""
        content = _CONFIG_TEMPLATE.format(
            env="dev", app_name="test", **_ENV_PRESETS["dev"]
        )
        required_keys = [
            "app_name", "log_level", "online_interval_seconds",
            "memory_capacity", "exploration_rate", "epsilon",
            "base_weights",
        ]
        for key in required_keys:
            self.assertIn(key, content)

    def test_config_template_env_presets_complete(self):
        """环境预设完整。"""
        for env in ["dev", "prod", "test"]:
            self.assertIn(env, _ENV_PRESETS)
            preset = _ENV_PRESETS[env]
            required_preset_keys = [
                "log_level", "online_interval", "offline_interval",
                "memory_capacity", "exploration_rate", "epsilon",
                "interrupt_threshold", "feature_dimensions",
            ]
            for key in required_preset_keys:
                self.assertIn(key, preset, f"{env} preset missing {key}")

    def test_dev_preset_debug_level(self):
        """dev预设使用DEBUG日志级别。"""
        self.assertEqual(_ENV_PRESETS["dev"]["log_level"], "DEBUG")

    def test_prod_preset_info_level(self):
        """prod预设使用INFO日志级别。"""
        self.assertEqual(_ENV_PRESETS["prod"]["log_level"], "INFO")

    def test_prod_preset_higher_memory(self):
        """prod预设内存更大。"""
        dev_mem = int(_ENV_PRESETS["dev"]["memory_capacity"])
        prod_mem = int(_ENV_PRESETS["prod"]["memory_capacity"])
        self.assertGreater(prod_mem, dev_mem)

    def test_generated_config_is_valid_yaml(self):
        """生成的配置是有效YAML。"""
        import yaml
        content = _CONFIG_TEMPLATE.format(
            env="dev", app_name="test", **_ENV_PRESETS["dev"]
        )
        config = yaml.safe_load(content)
        self.assertIsInstance(config, dict)
        self.assertGreater(len(config), 10)

    def test_generated_config_passes_validation(self):
        """生成的配置通过校验。"""
        from agent_core.common.config_validator import ConfigValidator
        import yaml
        content = _CONFIG_TEMPLATE.format(
            env="dev", app_name="test", **_ENV_PRESETS["dev"]
        )
        config = yaml.safe_load(content)
        ok, errors = ConfigValidator().validate(config)
        self.assertTrue(ok, f"Generated config invalid: {errors}")


class TestStartScriptTemplate(unittest.TestCase):
    """启动脚本模板测试。"""

    def test_start_script_template_generates_valid_bash(self):
        """启动脚本模板生成有效bash。"""
        content = _START_SCRIPT_TEMPLATE.format(
            app_name="test_app", env="dev"
        )
        self.assertIn("#!/bin/bash", content)
        self.assertIn("python3 -m agent_core start", content)
        self.assertIn("AGENT_ENV=dev", content)

    def test_start_script_template_has_pythonpath(self):
        """启动脚本设置PYTHONPATH。"""
        content = _START_SCRIPT_TEMPLATE.format(
            app_name="test", env="dev"
        )
        self.assertIn("PYTHONPATH", content)


class TestExampleTemplate(unittest.TestCase):
    """示例代码模板测试。"""

    def test_example_template_has_app_name(self):
        """示例代码包含应用名称。"""
        content = _EXAMPLE_TEMPLATE.replace("{app_name}", "my_agent")
        self.assertIn("my_agent", content)

    def test_example_template_imports_agent(self):
        """示例代码导入Agent。"""
        content = _EXAMPLE_TEMPLATE.replace("{app_name}", "test")
        self.assertIn("from agent_core.memory.agent_main", content)
        self.assertIn("SelfEvolvingAgent", content)

    def test_example_template_has_main_function(self):
        """示例代码有main函数。"""
        content = _EXAMPLE_TEMPLATE.replace("{app_name}", "test")
        self.assertIn("async def main", content)
        self.assertIn("if __name__", content)

    def test_example_template_demonstrates_lifecycle(self):
        """示例代码演示完整生命周期。"""
        content = _EXAMPLE_TEMPLATE.replace("{app_name}", "test")
        self.assertIn("initialize", content)
        self.assertIn("health_check", content)
        self.assertIn("start", content)
        self.assertIn("stop", content)


class TestReadmeTemplate(unittest.TestCase):
    """README模板测试。"""

    def test_readme_template_has_app_name(self):
        """README包含应用名称。"""
        content = _README_TEMPLATE.format(app_name="my_agent")
        self.assertIn("my_agent", content)

    def test_readme_template_has_quick_start(self):
        """README有快速开始。"""
        content = _README_TEMPLATE.format(app_name="test")
        self.assertIn("快速开始", content)
        self.assertIn("pip install", content)

    def test_readme_template_has_config_section(self):
        """README有配置说明。"""
        content = _README_TEMPLATE.format(app_name="test")
        self.assertIn("配置", content)
        self.assertIn("base.yaml", content)


class TestInteractiveMode(unittest.TestCase):
    """交互模式测试。"""

    def setUp(self):
        self.scaffolder = ProjectScaffolder()

    def test_non_interactive_mode_skips_questions(self):
        """非交互模式跳过提问。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "test_project")
            # 不应调用input
            with patch("builtins.input", side_effect=AssertionError("input should not be called")):
                result = self.scaffolder.generate(
                    project, interactive=False
                )
            self.assertTrue(result)

    def test_interactive_mode_asks_app_name(self):
        """交互模式询问应用名称。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "test_project")
            with patch("builtins.input", return_value="custom_name"):
                result = self.scaffolder.generate(
                    project, interactive=True
                )
            self.assertTrue(result)
            # 检查使用了自定义名称
            with open(os.path.join(project, "config", "dev.yaml")) as f:
                content = f.read()
            self.assertIn("custom_name", content)

    def test_interactive_mode_empty_input_uses_default(self):
        """交互模式空输入使用默认值。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "test_project")
            with patch("builtins.input", return_value=""):
                result = self.scaffolder.generate(
                    project, app_name="default_name", interactive=True
                )
            self.assertTrue(result)

    def test_interactive_mode_non_empty_dir_confirms(self):
        """交互模式非空目录确认。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建非空目录
            with open(os.path.join(tmpdir, "existing.txt"), "w") as f:
                f.write("existing")
            with patch("builtins.input", return_value="y"):
                result = self.scaffolder.generate(
                    tmpdir, interactive=True
                )
            self.assertTrue(result)

    def test_interactive_mode_non_empty_dir_decline(self):
        """交互模式非空目录拒绝则中止。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "existing.txt"), "w") as f:
                f.write("existing")
            with patch("builtins.input", return_value="n"):
                result = self.scaffolder.generate(
                    tmpdir, interactive=True
                )
            self.assertFalse(result)


class TestScaffoldFunction(unittest.TestCase):
    """scaffold_project便捷函数测试。"""

    def test_scaffold_project_returns_true(self):
        """scaffold_project返回True。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "test")
            result = scaffold_project(
                project, app_name="test", interactive=False
            )
            self.assertTrue(result)

    def test_scaffold_project_creates_files(self):
        """scaffold_project创建文件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "test")
            scaffold_project(project, interactive=False)
            self.assertTrue(os.path.exists(os.path.join(project, "README.md")))
            self.assertTrue(os.path.exists(os.path.join(project, "config", "base.yaml")))


class TestEndToEndScaffold(unittest.TestCase):
    """端到端脚手架测试。"""

    def test_generated_project_has_all_components(self):
        """生成的项目包含所有组件。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "e2e_project")
            self.scaffolder = ProjectScaffolder()
            self.scaffolder.generate(
                project, app_name="e2e_app", env="prod", interactive=False
            )

            # 验证所有文件存在
            expected_files = [
                "README.md",
                "requirements.txt",
                "config/base.yaml",
                "config/dev.yaml",
                "config/prod.yaml",
                "config/test.yaml",
                "scripts/start.sh",
                "examples/main.py",
            ]
            for f in expected_files:
                path = os.path.join(project, f)
                self.assertTrue(
                    os.path.exists(path),
                    f"Missing file: {f}"
                )

    def test_generated_configs_are_valid(self):
        """生成的配置文件有效。"""
        from agent_core.common.config_validator import ConfigValidator
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "validate_project")
            self.scaffolder = ProjectScaffolder()
            self.scaffolder.generate(
                project, app_name="valid_app", interactive=False
            )

            validator = ConfigValidator()
            for env in ["base", "dev", "prod", "test"]:
                path = os.path.join(project, "config", f"{env}.yaml")
                with open(path) as f:
                    config = yaml.safe_load(f)
                ok, errors = validator.validate(config)
                self.assertTrue(
                    ok,
                    f"{env}.yaml validation failed: {errors}"
                )

    def test_generated_example_is_importable(self):
        """生成的示例代码可导入。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = os.path.join(tmpdir, "import_project")
            self.scaffolder = ProjectScaffolder()
            self.scaffolder.generate(
                project, app_name="import_test", interactive=False
            )
            example_path = os.path.join(project, "examples", "main.py")
            # 验证语法正确（编译不抛出）
            with open(example_path) as f:
                code = f.read()
            compile(code, example_path, "exec")


if __name__ == "__main__":
    unittest.main()
