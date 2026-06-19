"""
依赖注入容器模块。

实现模块工厂注册机制，支持像乐高一样插拔替换任意模块。

第一性原理：
- 大脑的不同功能区可以独立替换而不影响整体
- 依赖倒置：高层模块不应依赖低层模块的具体实现
- 工厂模式：通过注册表动态创建实例，消除硬编码 new
"""

from typing import Any, Callable, Dict, Optional

from agent_core.common.interfaces import ModuleInterface
from agent_core.common.logger import get_logger


class DIContainer:
    """
    依赖注入容器。

    通过注册表管理模块工厂，实现运行时模块替换。
    """

    def __init__(self) -> None:
        self._factories: Dict[str, Callable[[], ModuleInterface]] = {}
        self._singletons: Dict[str, ModuleInterface] = {}
        self._logger = get_logger()

    def register(
        self, name: str, factory: Callable[[], ModuleInterface]
    ) -> None:
        """注册模块工厂。"""
        self._factories[name] = factory
        self._logger.info(f"[DIContainer] Registered factory: {name}")

    def resolve(self, name: str) -> ModuleInterface:
        """解析模块实例。"""
        if name not in self._factories:
            raise KeyError(f"Factory not registered: {name}")
        return self._factories[name]()

    def resolve_singleton(self, name: str) -> ModuleInterface:
        """解析单例模块实例。"""
        if name in self._singletons:
            return self._singletons[name]
        instance = self.resolve(name)
        self._singletons[name] = instance
        return instance

    def has_factory(self, name: str) -> bool:
        """检查是否已注册工厂。"""
        return name in self._factories

    def list_registered(self) -> list[str]:
        """列出所有已注册工厂名称。"""
        return list(self._factories.keys())

    def clear(self) -> None:
        """清空所有注册。"""
        self._factories.clear()
        self._singletons.clear()


def register_default_factories(container: DIContainer) -> None:
    """注册所有默认模块工厂。"""
    from agent_core.perception.perception_module import EnvironmentPerception
    from agent_core.drive.drive_module import DriveEngine
    from agent_core.predictor.predictor_module import MultiLayerPredictor
    from agent_core.predictor.error_evaluator import PredictionErrorEvaluator
    from agent_core.task.task_generator import TaskGenerator
    from agent_core.task.decision_engine import DecisionEngine
    from agent_core.task.task_executor import TaskExecutor
    from agent_core.task.code_executor import CodeExecutor
    from agent_core.memory.memory_module import MemorySystem
    from agent_core.memory.resource_guardian import ResourceGuardian
    from agent_core.llm.siliconflow_client import SiliconFlowClient

    container.register("perception", EnvironmentPerception)
    container.register("drive_engine", DriveEngine)
    container.register("predictor", MultiLayerPredictor)
    container.register(
        "error_evaluator",
        lambda: PredictionErrorEvaluator(feature_dimensions=10),
    )
    container.register("task_generator", TaskGenerator)
    container.register("decision_engine", DecisionEngine)
    container.register("task_executor", TaskExecutor)
    container.register("code_executor", CodeExecutor)
    container.register("memory", MemorySystem)
    container.register("guardian", ResourceGuardian)
    container.register("llm", SiliconFlowClient)


def get_di_container() -> DIContainer:
    """获取全局DI容器实例。"""
    global _GLOBAL_CONTAINER
    if "_GLOBAL_CONTAINER" not in globals():
        _GLOBAL_CONTAINER = DIContainer()
        register_default_factories(_GLOBAL_CONTAINER)
    return _GLOBAL_CONTAINER


def reset_di_container() -> DIContainer:
    """重置全局DI容器。"""
    global _GLOBAL_CONTAINER
    _GLOBAL_CONTAINER = DIContainer()
    register_default_factories(_GLOBAL_CONTAINER)
    return _GLOBAL_CONTAINER
