"""
插件注册表模块。

支持运行时动态加载、注册、卸载功能模块。
通过importlib标准库实现零额外依赖。

第一性原理：
- 生物大脑可动态招募不同脑区处理特定任务
- 模块加载应显式契约化，禁止隐式副作用
- 热插拔必须保证生命周期完整（init -> run -> shutdown）
"""

import importlib
import importlib.util
import os
from typing import Any, Dict, List, Optional, Type

from agent_core.common.interfaces import ModuleInterface
from agent_core.common.logger import get_logger


class PluginRegistry:
    """
    插件注册表。

    管理动态加载的模块实例，支持按名称查找和热插拔。
    """

    def __init__(self) -> None:
        self._plugins: Dict[str, ModuleInterface] = {}
        self._logger = get_logger()

    def list_plugins(self) -> List[str]:
        """列出所有已注册插件名称。"""
        return list(self._plugins.keys())

    def get_plugin(self, name: str) -> Optional[ModuleInterface]:
        """按名称获取插件实例。"""
        return self._plugins.get(name)

    async def load_from_path(
        self, module_path: str, class_name: str, config: Dict[str, Any]
    ) -> bool:
        """
        从文件路径动态加载插件。

        Args:
            module_path: Python文件绝对路径。
            class_name: 插件类名。
            config: 初始化配置。

        Returns:
            加载成功返回True。
        """
        if not os.path.isfile(module_path):
            self._logger.error(f"[PluginRegistry] File not found: {module_path}")
            return False
        module = self._import_module(module_path)
        if module is None:
            return False
        plugin_class = self._extract_class(module, class_name)
        if plugin_class is None:
            return False
        return await self._init_plugin(plugin_class, config)

    def _import_module(self, module_path: str) -> Optional[Any]:
        spec = importlib.util.spec_from_file_location("dynamic_plugin", module_path)
        if spec is None or spec.loader is None:
            self._logger.error(f"[PluginRegistry] Cannot load spec: {module_path}")
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _extract_class(
        self, module: Any, class_name: str
    ) -> Optional[Type[ModuleInterface]]:
        plugin_class = getattr(module, class_name, None)
        if plugin_class is None:
            self._logger.error(
                f"[PluginRegistry] Class {class_name} not found in module"
            )
            return None
        if not issubclass(plugin_class, ModuleInterface):
            self._logger.error(
                f"[PluginRegistry] Class {class_name} does not implement ModuleInterface"
            )
            return None
        return plugin_class

    async def _init_plugin(
        self, plugin_class: Type[ModuleInterface], config: Dict[str, Any]
    ) -> bool:
        try:
            instance = plugin_class()
            ok = await instance.initialize(config)
            if not ok:
                self._logger.error(
                    f"[PluginRegistry] Plugin {instance.module_name} init failed"
                )
                return False
            self._plugins[instance.module_name] = instance
            self._logger.info(
                f"[PluginRegistry] Loaded plugin: {instance.module_name}"
            )
            return True
        except Exception as exc:
            self._logger.error(f"[PluginRegistry] Load failed: {exc}")
            return False

    async def unload_plugin(self, name: str) -> bool:
        """
        卸载指定插件。

        Args:
            name: 插件名称。

        Returns:
            卸载成功返回True。
        """
        plugin = self._plugins.get(name)
        if plugin is None:
            return False
        await plugin.shutdown()
        del self._plugins[name]
        self._logger.info(f"[PluginRegistry] Unloaded plugin: {name}")
        return True

    async def unload_all(self) -> None:
        """卸载所有插件。"""
        for name in list(self._plugins.keys()):
            await self.unload_plugin(name)

    async def health_check_all(self) -> Dict[str, Any]:
        """执行所有插件健康检查。"""
        results: Dict[str, Any] = {}
        for name, plugin in self._plugins.items():
            try:
                results[name] = await plugin.health_check()
            except Exception as exc:
                results[name] = {"status": "error", "exception": str(exc)}
        return results
