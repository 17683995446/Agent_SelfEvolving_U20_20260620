"""
核心模块

第一性原理：所有模块共享的基础类型和工具。
"""

from .types import (
    # 感知
    PerceptionModality, PerceptionInput, PerceptionOutput,
    # 驱力
    DriveType, Drive, DriveState,
    # 预测
    PredictionHorizon, Prediction, PredictionError,
    # 记忆
    MemoryLevel, MemoryType, MemoryEntry,
    # 任务
    TaskStatus, TaskPriority, Task,
    # 优化
    OptimizationMode, OptimizationResult,
    # 安全
    SafetyLevel, SafetyEvent,
    # 事件
    EventType, SystemEvent,
    # 常量
    STATE_VECTOR_DIM,
    STATE_IDX_CPU_OVERALL,
    STATE_IDX_CPU_CORE,
    STATE_IDX_CPU_MAX,
    STATE_IDX_CPU_USER,
    STATE_IDX_CPU_SYSTEM,
    STATE_IDX_LOAD_1MIN,
    STATE_IDX_LOAD_5MIN,
    STATE_IDX_LOAD_15MIN,
    STATE_IDX_CTX_SWITCH,
    STATE_IDX_INTERRUPT,
    STATE_IDX_MEM_USED,
    STATE_IDX_MEM_AVAIL,
    STATE_IDX_MEM_CACHE,
    STATE_IDX_MEM_SWAP,
    STATE_IDX_MEM_ALLOC_RATE,
    STATE_IDX_DISK_USED,
    STATE_IDX_DISK_READ,
    STATE_IDX_DISK_WRITE,
    STATE_IDX_NET_SEND,
    STATE_IDX_NET_RECV,
    STATE_IDX_NET_CONN,
    STATE_IDX_NET_ERROR,
    STATE_IDX_PROC_TOTAL,
    STATE_IDX_PROC_RUNNING,
    STATE_IDX_PROC_ZOMBIE,
    STATE_IDX_PROC_HIGH_CPU,
    STATE_IDX_PROC_HIGH_MEM,
    STATE_IDX_PROC_SPAWN_RATE,
)

from .event_bus import EventBus
from .config import AgentConfig
from .logger import LogManager
from .model_registry import ModelRegistry, ModelSnapshot
from .config_adaptive import ConfigAdaptive
from .health_monitor import HealthMonitor, HealthLevel, HealthCheckResult
from .plugin_registry import PluginRegistry, PluginMeta, PluginEntry
from .module_factory import ModuleFactory
from .hot_swap import HotSwapManager

# 秩序化阶段5：导出阶段1-6新组件及其接口
from .goal_driven_loop import GoalDrivenLoop
from .skill_library import SkillLibrary, Skill
from .multi_agent_collaborator import MultiAgentCollaborator
from .long_task_orchestrator import LongTaskOrchestrator
from .skill_evolution import SkillEvolutionEngine
from .self_organization import SelfOrganizationEngine
from .interfaces import (
    IGoalDrivenLoop, ISkillLibrary, ICollaborator,
    ILongTaskOrchestrator, ISkillEvolution, ISelfOrganization,
)

__all__ = [
    # 感知
    "PerceptionModality", "PerceptionInput", "PerceptionOutput",
    # 驱力
    "DriveType", "Drive", "DriveState",
    # 预测
    "PredictionHorizon", "Prediction", "PredictionError",
    # 记忆
    "MemoryLevel", "MemoryType", "MemoryEntry",
    # 任务
    "TaskStatus", "TaskPriority", "Task",
    # 优化
    "OptimizationMode", "OptimizationResult",
    # 安全
    "SafetyLevel", "SafetyEvent",
    # 事件
    "EventType", "SystemEvent", "EventBus",
    # 配置
    "AgentConfig",
    # 日志
    "LogManager",
    # 模型注册
    "ModelRegistry", "ModelSnapshot",
    # 配置自适应
    "ConfigAdaptive",
    # 健康监控
    "HealthMonitor", "HealthLevel", "HealthCheckResult",
    # 插件注册
    "PluginRegistry", "PluginMeta", "PluginEntry",
    # 模块工厂
    "ModuleFactory",
    # 热插拔
    "HotSwapManager",
    # 阶段1-6 新组件
    "GoalDrivenLoop",
    "SkillLibrary", "Skill",
    "MultiAgentCollaborator",
    "LongTaskOrchestrator",
    "SkillEvolutionEngine",
    "SelfOrganizationEngine",
    # 接口契约
    "IGoalDrivenLoop", "ISkillLibrary", "ICollaborator",
    "ILongTaskOrchestrator", "ISkillEvolution", "ISelfOrganization",
    # 常量
    "STATE_VECTOR_DIM",
    "STATE_IDX_CPU_OVERALL",
    "STATE_IDX_MEM_USED",
]
