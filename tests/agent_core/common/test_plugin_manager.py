"""
插件管理器测试。

覆盖：依赖解析、加载顺序、卸载检查、健康检查。
"""

import pytest

from agent_core.common.plugin_manager import PluginManager


class TestPluginManager:
    """PluginManager测试类。"""

    @pytest.fixture
    def manager(self):
        """创建插件管理器实例。"""
        return PluginManager()

    def test_resolve_load_order_no_deps(self, manager):
        """测试无依赖时加载顺序。"""
        order = manager._resolve_load_order("a")
        assert order == ["a"]

    def test_resolve_load_order_with_deps(self, manager):
        """测试有依赖时的拓扑排序。"""
        manager.register_dependency("c", ["b"])
        manager.register_dependency("b", ["a"])
        order = manager._resolve_load_order("c")
        assert order == ["a", "b", "c"]

    def test_resolve_load_order_diamond(self, manager):
        """测试菱形依赖。"""
        manager.register_dependency("d", ["b", "c"])
        manager.register_dependency("b", ["a"])
        manager.register_dependency("c", ["a"])
        order = manager._resolve_load_order("d")
        assert order.index("a") < order.index("b")
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("d")
        assert order.index("c") < order.index("d")

    def test_list_plugins_empty(self, manager):
        """测试空插件列表。"""
        assert manager.list_plugins() == []

    @pytest.mark.asyncio
    async def test_unload_with_dependents_blocked(self, manager):
        """测试有依赖者时卸载被阻止。"""
        manager.register_dependency("b", ["a"])
        result = await manager.unload_plugin("a")
        assert result is False

    @pytest.mark.asyncio
    async def test_unload_no_dependents_allowed(self, manager):
        """测试无依赖者时卸载允许。"""
        result = await manager.unload_plugin("a")
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_all_empty(self, manager):
        """测试空管理器健康检查。"""
        result = await manager.health_check_all()
        assert result == {}
