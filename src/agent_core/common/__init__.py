"""
公共模块包初始化文件。

提供项目全局共享的数据契约、接口定义与常量枚举。
"""

from .constants import ErrorCode, EnvironmentConfigKey, LogLevel
from .data_contracts import (
    DriveSignals,
    EnvironmentState,
    ErrorMetrics,
    Experience,
    PredictionResult,
    Task,
)
from .interfaces import (
    IDecisionEngine,
    IDriveEngine,
    IEnvironmentPerception,
    IErrorEvaluator,
    IMemorySystem,
    IMultiLayerPredictor,
    IPredictionModel,
    IResourceGuardian,
    ITaskGenerator,
    ModuleInterface,
)

__all__ = [
    "DriveSignals",
    "EnvironmentConfigKey",
    "EnvironmentState",
    "ErrorCode",
    "ErrorMetrics",
    "Experience",
    "IDecisionEngine",
    "IDriveEngine",
    "IEnvironmentPerception",
    "IErrorEvaluator",
    "IMemorySystem",
    "IMultiLayerPredictor",
    "IPredictionModel",
    "IResourceGuardian",
    "ITaskGenerator",
    "LogLevel",
    "ModuleInterface",
    "PredictionResult",
    "Task",
]
