"""
依赖注入容器单元测试。

覆盖注册、解析、单例、重置的四类用例。
"""

import unittest
from typing import Any

from agent_core.common.di_container import (
    DIContainer,
    get_di_container,
    register_default_factories,
    reset_di_container,
)
from agent_core.common.interfaces import ModuleInterface


class DummyModule(ModuleInterface):
    """测试用虚拟模块。"""

    def __init__(self, value: int = 0) -> None:
        self.value = value

    @property
    def version(self) -> str:
        return "0.0.1"

    @property
    def module_name(self) -> str:
        return "DummyModule"

    async def initialize(self, config: dict[str, Any]) -> bool:
        return True

    async def health_check(self) -> dict[str, Any]:
        return {"status": "healthy"}

    async def shutdown(self) -> None:
        pass


class TestDIContainer(unittest.TestCase):
    """测试DI容器。"""

    def setUp(self) -> None:
        """设置测试环境。"""
        self.container = DIContainer()

    def test_register_and_resolve(self) -> None:
        """正常值测试：注册并解析模块。"""
        self.container.register("dummy", DummyModule)
        module = self.container.resolve("dummy")
        self.assertIsInstance(module, DummyModule)

    def test_resolve_not_registered(self) -> None:
        """非法测试：解析未注册模块。"""
        with self.assertRaises(KeyError):
            self.container.resolve("nonexistent")

    def test_resolve_singleton(self) -> None:
        """正常值测试：单例模式。"""
        self.container.register("dummy", DummyModule)
        a = self.container.resolve_singleton("dummy")
        b = self.container.resolve_singleton("dummy")
        self.assertIs(a, b)

    def test_singleton_vs_resolve(self) -> None:
        """边界测试：resolve每次创建新实例，singleton复用。"""
        self.container.register("dummy", DummyModule)
        a = self.container.resolve("dummy")
        b = self.container.resolve("dummy")
        c = self.container.resolve_singleton("dummy")
        self.assertIsNot(a, b)
        self.assertIs(c, self.container.resolve_singleton("dummy"))

    def test_has_factory(self) -> None:
        """正常值测试：检查工厂是否存在。"""
        self.assertFalse(self.container.has_factory("dummy"))
        self.container.register("dummy", DummyModule)
        self.assertTrue(self.container.has_factory("dummy"))

    def test_list_registered(self) -> None:
        """正常值测试：列出已注册工厂。"""
        self.assertEqual(self.container.list_registered(), [])
        self.container.register("a", DummyModule)
        self.container.register("b", DummyModule)
        self.assertEqual(self.container.list_registered(), ["a", "b"])

    def test_clear(self) -> None:
        """正常值测试：清空注册。"""
        self.container.register("dummy", DummyModule)
        self.container.clear()
        self.assertFalse(self.container.has_factory("dummy"))
        self.assertEqual(self.container.list_registered(), [])

    def test_clear_removes_singletons(self) -> None:
        """边界测试：清空也移除单例。"""
        self.container.register("dummy", DummyModule)
        self.container.resolve_singleton("dummy")
        self.container.clear()
        self.container.register("dummy", DummyModule)
        a = self.container.resolve_singleton("dummy")
        self.assertIs(a, self.container.resolve_singleton("dummy"))

    def test_lambda_factory(self) -> None:
        """正常值测试：lambda工厂。"""
        self.container.register("dummy", lambda: DummyModule(value=42))
        module = self.container.resolve("dummy")
        self.assertEqual(module.value, 42)


class TestGlobalDIContainer(unittest.TestCase):
    """测试全局DI容器。"""

    def test_get_di_container(self) -> None:
        """正常值测试：获取全局容器。"""
        container = get_di_container()
        self.assertIsInstance(container, DIContainer)

    def test_reset_di_container(self) -> None:
        """正常值测试：重置全局容器。"""
        original = get_di_container()
        reset = reset_di_container()
        self.assertIsNot(original, reset)
        self.assertIs(reset, get_di_container())

    def test_default_factories_registered(self) -> None:
        """正常值测试：默认工厂已注册。"""
        container = reset_di_container()
        expected = [
            "perception",
            "drive_engine",
            "predictor",
            "error_evaluator",
            "task_generator",
            "decision_engine",
            "task_executor",
            "memory",
            "guardian",
        ]
        for name in expected:
            self.assertTrue(
                container.has_factory(name),
                f"Factory {name} not registered",
            )

    def test_resolve_default_modules(self) -> None:
        """正常值测试：解析默认模块。"""
        container = reset_di_container()
        perception = container.resolve("perception")
        self.assertIsNotNone(perception)
        predictor = container.resolve("predictor")
        self.assertIsNotNone(predictor)

    def test_register_default_factories_idempotent(self) -> None:
        """边界测试：重复注册覆盖。"""
        container = DIContainer()
        register_default_factories(container)
        register_default_factories(container)
        self.assertTrue(container.has_factory("perception"))


if __name__ == "__main__":
    unittest.main()
