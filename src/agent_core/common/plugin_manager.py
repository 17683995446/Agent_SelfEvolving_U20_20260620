"""
插件管理器模块。

在PluginRegistry基础上提供插件生命周期管理、依赖检查和热插拔。

第一性原理：
- 插件是有依赖关系的，必须按拓扑顺序加载
- 热插拔必须保证系统状态一致性
- 版本兼容性必须显式校验
"""

from typing import Any, Dict, List, Optional, Set

from agent_core.common.interfaces import ModuleInterface
from agent_core.common.logger import get_logger
from agent_core.common.plugin_registry import PluginRegistry


class PluginManager:
    """
    插件管理器。

    管理插件依赖、加载顺序和热插拔。
    """

    def __init__(self) -> None:
        self._registry = PluginRegistry()
        self._dependencies: Dict[str, List[str]] = {}
        self._logger = get_logger()

    def register_dependency(
        self, plugin_name: str, depends_on: List[str]
    ) -> None:
        """
        注册插件依赖关系。

        Args:
            plugin_name: 插件名称。
            depends_on: 依赖的插件名称列表。
        """
        self._dependencies[plugin_name] = depends_on

    def _resolve_load_order(self, target: str) -> List[str]:
        """
        解析插件加载顺序（拓扑排序）。

        Args:
            target: 目标插件名称。

        Returns:
            加载顺序列表。
        """
        visited: Set[str] = set()
        order: List[str] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            visited.add(name)
            for dep in self._dependencies.get(name, []):
                visit(dep)
            order.append(name)

        visit(target)
        return order

    async def load_with_deps(
        self,
        plugin_name: str,
        class_name: str,
        module_path: str,
        config: Dict[str, Any],
    ) -> bool:
        """
        加载插件及其所有依赖。

        Args:
            plugin_name: 插件名称。
            class_name: 插件类名。
            module_path: 模块文件路径。
            config: 初始化配置。

        Returns:
            全部加载成功返回True。
        """
        order = self._resolve_load_order(plugin_name)
        for name in order:
            if self._registry.get_plugin(name) is not None:
                continue
            ok = await self._registry.load_from_path(
                module_path, class_name, config
            )
            if not ok:
                self._logger.error(
                    f"[PluginManager] Failed to load dependency: {name}"
                )
                return False
        return True

    async def unload_plugin(self, name: str) -> bool:
        """
        卸载插件，检查是否有其他插件依赖它。

        Args:
            name: 插件名称。

        Returns:
            卸载成功返回True。
        """
        dependents = [
            k for k, deps in self._dependencies.items() if name in deps
        ]
        if dependents:
            self._logger.error(
                f"[PluginManager] Cannot unload {name}, dependents: {dependents}"
            )
            return False
        return await self._registry.unload_plugin(name)

    def get_plugin(self, name: str) -> Optional[ModuleInterface]:
        """获取插件实例。"""
        return self._registry.get_plugin(name)

    def list_plugins(self) -> List[str]:
        """列出所有已加载插件。"""
        return self._registry.list_plugins()

    async def health_check_all(self) -> Dict[str, Any]:
        """执行所有插件健康检查。"""
        return await self._registry.health_check_all()

    async def shutdown_all(self) -> None:
        """关闭所有插件。"""
        await self._registry.unload_all()
