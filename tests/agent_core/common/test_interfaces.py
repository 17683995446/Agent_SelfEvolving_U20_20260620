"""
接口模块单元测试。

覆盖接口定义的四类用例。
"""

import unittest
from abc import ABC

from agent_core.common.interfaces import (
    ModuleInterface,
    IEnvironmentPerception,
    IDriveEngine,
    IPredictionModel,
    IMultiLayerPredictor,
    IErrorEvaluator,
    ITaskGenerator,
    IDecisionEngine,
    IMemorySystem,
    IResourceGuardian,
)


class TestInterfaces(unittest.TestCase):
    """测试接口定义。"""

    def test_module_interface_is_abc(self) -> None:
        """正常值测试：ModuleInterface是ABC。"""
        self.assertTrue(issubclass(ModuleInterface, ABC))

    def test_all_interfaces_are_abc(self) -> None:
        """正常值测试：所有接口继承ABC。"""
        interfaces = [
            IEnvironmentPerception,
            IDriveEngine,
            IPredictionModel,
            IMultiLayerPredictor,
            IErrorEvaluator,
            ITaskGenerator,
            IDecisionEngine,
            IMemorySystem,
            IResourceGuardian,
        ]
        for iface in interfaces:
            self.assertTrue(issubclass(iface, ABC))

    def test_module_interface_has_abstract_methods(self) -> None:
        """正常值测试：抽象方法存在。"""
        abstract_methods = getattr(ModuleInterface, "__abstractmethods__", set())
        self.assertIn("version", abstract_methods)
        self.assertIn("module_name", abstract_methods)
        self.assertIn("initialize", abstract_methods)
        self.assertIn("health_check", abstract_methods)
        self.assertIn("shutdown", abstract_methods)

    def test_cannot_instantiate_module_interface(self) -> None:
        """非法操作测试：不能直接实例化抽象类。"""
        with self.assertRaises(TypeError):
            ModuleInterface()

    def test_iprediction_model_methods(self) -> None:
        """正常值测试：预测模型接口方法。"""
        abstract_methods = getattr(IPredictionModel, "__abstractmethods__", set())
        self.assertIn("predict", abstract_methods)
        self.assertIn("update", abstract_methods)
        self.assertIn("get_error", abstract_methods)

    def test_idecision_engine_methods(self) -> None:
        """正常值测试：决策引擎接口方法。"""
        abstract_methods = getattr(IDecisionEngine, "__abstractmethods__", set())
        self.assertIn("select", abstract_methods)
        self.assertIn("should_interrupt", abstract_methods)

    def test_imemory_system_methods(self) -> None:
        """正常值测试：记忆系统接口方法。"""
        abstract_methods = getattr(IMemorySystem, "__abstractmethods__", set())
        self.assertIn("store", abstract_methods)
        self.assertIn("sample_experiences", abstract_methods)
        self.assertIn("offline_review", abstract_methods)

    def test_iresource_guardian_methods(self) -> None:
        """正常值测试：资源守护接口方法。"""
        abstract_methods = getattr(IResourceGuardian, "__abstractmethods__", set())
        self.assertIn("check", abstract_methods)
        self.assertIn("enforce", abstract_methods)

    def test_empty_abstract_methods_for_non_abc(self) -> None:
        """边界测试：非ABC类无抽象方法限制。"""
        self.assertFalse(issubclass(object, ABC))


if __name__ == "__main__":
    unittest.main()
