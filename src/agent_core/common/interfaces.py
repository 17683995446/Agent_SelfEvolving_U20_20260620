"""
模块接口定义。

所有功能模块必须显式继承abc.ABC抽象基类，并定义抽象方法。
禁止无约束实体类存在。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import numpy as np

from .data_contracts import (
    DriveSignals,
    EnvironmentState,
    ErrorMetrics,
    Experience,
    PredictionResult,
    Task,
)


class ModuleInterface(ABC):
    """
    模块接口基类。

    所有功能模块必须实现本基类定义的接口契约。
    """

    @property
    @abstractmethod
    def version(self) -> str:
        """
        获取模块版本号。

        Returns:
            版本号字符串，格式为major.minor.patch。
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def module_name(self) -> str:
        """
        获取模块唯一标识名。

        Returns:
            模块标识字符串。
        """
        raise NotImplementedError

    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> bool:
        """
        初始化模块。

        Args:
            config: 配置字典。

        Returns:
            初始化成功返回True，否则返回False。
        """
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        执行健康检查。

        Returns:
            包含status与metrics的字典，status取值为healthy、degraded、unhealthy。
        """
        raise NotImplementedError

    @abstractmethod
    async def shutdown(self) -> None:
        """
        优雅关闭模块，释放资源。
        """
        raise NotImplementedError


class IEnvironmentPerception(ModuleInterface, ABC):
    """
    环境感知模块接口。
    """

    @abstractmethod
    async def perceive(self) -> EnvironmentState:
        """
        执行环境感知，返回标准化状态向量。

        Returns:
            环境状态对象。
        """
        raise NotImplementedError

    @abstractmethod
    def get_state_history(self, history_size: int) -> List[EnvironmentState]:
        """
        获取最近history_size条状态记录。

        Args:
            history_size: 历史记录数量。

        Returns:
            环境状态对象列表。
        """
        raise NotImplementedError


class IDriveEngine(ModuleInterface, ABC):
    """
    驱力引擎模块接口。
    """

    @abstractmethod
    async def compute(self, env_state: EnvironmentState) -> DriveSignals:
        """
        计算驱力信号。

        Args:
            env_state: 环境状态对象。

        Returns:
            驱力信号对象。
        """
        raise NotImplementedError

    @abstractmethod
    def set_base_weights(self, weights: Dict[str, float]) -> None:
        """
        设置基础权重。

        Args:
            weights: 权重字典。
        """
        raise NotImplementedError


class IPredictionModel(ABC):
    """
    预测模型接口，单一层级预测器。
    """

    @abstractmethod
    def predict(self, state: np.ndarray) -> np.ndarray:
        """
        预测下一个状态。

        Args:
            state: 当前状态向量。

        Returns:
            预测状态向量。
        """
        raise NotImplementedError

    @abstractmethod
    def update(self, state: np.ndarray, actual: np.ndarray) -> None:
        """
        在线更新模型。

        Args:
            state: 当前状态向量。
            actual: 实际状态向量。
        """
        raise NotImplementedError

    @abstractmethod
    def get_error(self) -> float:
        """
        获取当前预测误差。

        Returns:
            误差浮点数值。
        """
        raise NotImplementedError


class IMultiLayerPredictor(ModuleInterface, ABC):
    """
    多层预测器接口。
    """

    @abstractmethod
    def predict_all(self, state: np.ndarray) -> PredictionResult:
        """
        生成多层预测。

        Args:
            state: 当前状态向量。

        Returns:
            预测结果对象。
        """
        raise NotImplementedError

    @abstractmethod
    def update_all(self, state: np.ndarray, actual: np.ndarray) -> None:
        """
        更新所有层级。

        Args:
            state: 当前状态向量。
            actual: 实际状态向量。
        """
        raise NotImplementedError


class IErrorEvaluator(ABC):
    """
    误差评估模块接口。
    """

    @abstractmethod
    def evaluate(self, prediction: np.ndarray, actual: np.ndarray) -> ErrorMetrics:
        """
        评估预测误差。

        Args:
            prediction: 预测向量。
            actual: 实际向量。

        Returns:
            误差指标对象。
        """
        raise NotImplementedError


class ITaskGenerator(ModuleInterface, ABC):
    """
    任务生成模块接口。
    """

    @abstractmethod
    def generate(
        self, drive_signals: DriveSignals, errors: ErrorMetrics
    ) -> List[Task]:
        """
        生成候选任务。

        Args:
            drive_signals: 驱力信号对象。
            errors: 误差指标对象。

        Returns:
            任务对象列表。
        """
        raise NotImplementedError


class IDecisionEngine(ModuleInterface, ABC):
    """
    决策引擎接口。
    """

    @abstractmethod
    def select(
        self, tasks: List[Task], drive_signals: DriveSignals
    ) -> Optional[Task]:
        """
        从任务池中选择最优任务。

        Args:
            tasks: 任务对象列表。
            drive_signals: 驱力信号对象。

        Returns:
            选中的任务对象，无合适任务时返回None。
        """
        raise NotImplementedError

    @abstractmethod
    def should_interrupt(
        self, current_task: Task, new_drives: DriveSignals
    ) -> bool:
        """
        判断是否应该中断当前任务。

        Args:
            current_task: 当前执行任务。
            new_drives: 新的驱力信号。

        Returns:
            应中断返回True，否则返回False。
        """
        raise NotImplementedError


class IMemorySystem(ModuleInterface, ABC):
    """
    记忆系统接口。
    """

    @abstractmethod
    async def store(self, experience: Experience) -> None:
        """
        存储经验。

        Args:
            experience: 经验对象。
        """
        raise NotImplementedError

    @abstractmethod
    async def sample_experiences(self, sample_size: int) -> List[Experience]:
        """
        采样经验。

        Args:
            sample_size: 采样数量。

        Returns:
            经验对象列表。
        """
        raise NotImplementedError

    @abstractmethod
    async def offline_review(self, predictor: IMultiLayerPredictor) -> None:
        """
        离线复盘，批量优化模型。

        Args:
            predictor: 多层预测器对象。
        """
        raise NotImplementedError


class IResourceGuardian(ABC):
    """
    资源守护接口。
    """

    @abstractmethod
    async def check(self) -> Dict[str, Any]:
        """
        检查资源使用。

        Returns:
            资源状态字典。
        """
        raise NotImplementedError

    @abstractmethod
    async def enforce(self) -> None:
        """
        强制执行资源限制。
        """
        raise NotImplementedError
