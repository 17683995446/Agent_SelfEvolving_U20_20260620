"""
数据契约模块。

定义全系统共享的不可变数据对象，所有模块间通信必须通过本模块定义的数据契约进行。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np

from .constants import (
    GAP_MAX_VALUE,
    GAP_MIN_VALUE,
    REWARD_MAX_VALUE,
    REWARD_MIN_VALUE,
    WEIGHT_SUM_TARGET,
    WEIGHT_TOLERANCE,
)


@dataclass(frozen=True)
class EnvironmentState:
    """
    环境状态向量。

    感知模块输出，全系统输入。包含原始传感器数据与标准化特征向量。

    Args:
        timestamp: 状态采集时间戳，单位为秒。
        raw_sensors: 原始传感器数据字典。
        feature_vector: 标准化后的特征向量，取值范围为[0, 1]。

    Raises:
        ValueError: 当特征向量不在合理范围内时抛出。
    """

    timestamp: float
    raw_sensors: Dict[str, Any]
    feature_vector: np.ndarray

    def __post_init__(self) -> None:
        if not isinstance(self.feature_vector, np.ndarray):
            object.__setattr__(
                self,
                "feature_vector",
                np.array(self.feature_vector, dtype=np.float32),
            )


@dataclass(frozen=True)
class DriveSignals:
    """
    驱力信号。

    内生动机的量化表示，包含三大驱力的奖励值、缺口值与动态权重。

    Args:
        safety_reward: 安全驱力奖励值，范围为[0, 1]。
        gain_reward: 收益驱力奖励值，范围为[0, 1]。
        efficiency_reward: 能效驱力奖励值，范围为[0, 1]。
        safety_gap: 安全驱力缺口，范围为[0, 1]。
        gain_gap: 收益驱力缺口，范围为[0, 1]。
        efficiency_gap: 能效驱力缺口，范围为[0, 1]。
        weights: 动态权重字典，三项之和必须为1.0。
        total_reward: 加权总奖励值。

    Raises:
        ValueError: 当奖励值或缺口值超出范围，或权重和不等于1.0时抛出。
    """

    safety_reward: float
    gain_reward: float
    efficiency_reward: float
    safety_gap: float
    gain_gap: float
    efficiency_gap: float
    weights: Dict[str, float]
    total_reward: float

    def __post_init__(self) -> None:
        reward_attrs = [
            "safety_reward",
            "gain_reward",
            "efficiency_reward",
        ]
        gap_attrs = [
            "safety_gap",
            "gain_gap",
            "efficiency_gap",
        ]
        for attr in reward_attrs + gap_attrs:
            val = getattr(self, attr)
            if not (REWARD_MIN_VALUE <= val <= REWARD_MAX_VALUE):
                raise ValueError(
                    f"{attr} must be in [{REWARD_MIN_VALUE}, {REWARD_MAX_VALUE}], got {val}"
                )
        weight_sum = sum(self.weights.values())
        if abs(weight_sum - WEIGHT_SUM_TARGET) > WEIGHT_TOLERANCE:
            raise ValueError(
                f"Weights must sum to {WEIGHT_SUM_TARGET}, got {weight_sum}"
            )


@dataclass(frozen=True)
class PredictionResult:
    """
    预测结果。

    多层预测模型的输出，包含低层、中层、高层及集成预测结果。

    Args:
        low_level: 底层高频微预测向量。
        mid_level: 中层中频趋势预测向量。
        high_level: 高层低频抽象预测向量。
        ensemble: 集成预测结果向量。
        confidence: 预测置信度，范围为[0, 1]。
    """

    low_level: np.ndarray
    mid_level: np.ndarray
    high_level: np.ndarray
    ensemble: np.ndarray
    confidence: float


@dataclass(frozen=True)
class ErrorMetrics:
    """
    误差指标。

    预测与实际的对齐程度评估结果。

    Args:
        mse: 均方误差。
        mae: 平均绝对误差。
        mape: 平均绝对百分比误差。
        direction_accuracy: 方向预测准确率。
        error_vector: 逐维误差向量。
    """

    mse: float
    mae: float
    mape: float
    direction_accuracy: float
    error_vector: np.ndarray


@dataclass
class Task:
    """
    任务对象。

    自主生成的行为单元，包含任务属性与评分方法。

    Args:
        task_id: 任务唯一标识符。
        name: 任务名称。
        task_type: 任务类型，可选值为safety、gain、efficiency、exploration。
        priority: 任务优先级，范围为[0, 1]。
        expected_reward: 预期奖励值。
        expected_cost: 预期成本值。
        novelty_score: 新颖性评分。
        params: 任务附加参数字典。
        created_at: 任务创建时间戳。

    Raises:
        ValueError: 当权重字典缺少必要键时抛出。
    """

    task_id: str
    name: str
    task_type: str
    priority: float
    expected_reward: float
    expected_cost: float
    novelty_score: float
    params: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: 0.0)

    def compute_score(self, weights: Dict[str, float]) -> float:
        """
        计算任务综合得分。

        公式：奖励权重 * 预期奖励 + 新颖性权重 * 新颖性评分 - 成本权重 * 预期成本。

        Args:
            weights: 权重字典，必须包含reward、novelty、cost三个键。

        Returns:
            综合得分浮点数值。

        Raises:
            ValueError: 当weights缺少必要键时抛出。
        """
        required_keys = {"reward", "novelty", "cost"}
        if not required_keys.issubset(weights.keys()):
            raise ValueError(f"Weights must contain keys: {required_keys}")
        reward_score = weights["reward"] * self.expected_reward
        novelty_score = weights["novelty"] * self.novelty_score
        cost_score = weights["cost"] * self.expected_cost
        return reward_score + novelty_score - cost_score


@dataclass
class Experience:
    """
    经验记录。

    单次感知-行动-结果的完整记录，用于记忆存储与离线复盘。

    Args:
        timestamp: 经验记录时间戳。
        state: 环境状态对象。
        prediction: 预测结果对象。
        drive_signals: 驱力信号对象。
        selected_task: 被选中的任务对象，可能为None。
        execution_result: 执行结果字典。
        error_metrics: 误差指标对象。
        priority: 经验优先级，用于回放采样。
    """

    timestamp: float
    state: EnvironmentState
    prediction: PredictionResult
    drive_signals: DriveSignals
    selected_task: Optional[Task]
    execution_result: Dict[str, Any]
    error_metrics: ErrorMetrics
    priority: float = 1.0
