"""
核心接口定义

第一性原理：模块间通信应通过明确的契约（接口）而非具体实现。
此文件定义所有模块必须遵循的抽象接口，确保：
1. 模块可替换性：任何实现相同接口的模块可无缝替换
2. 可测试性：可注入Mock实现进行单元测试
3. 可扩展性：新增模块只需实现对应接口

接口设计规范：
- 每个接口方法必须有明确的Precondition/Postcondition
- 输入参数类型必须明确，不接受Any类型
- 返回值类型必须明确，Optional仅用于可能返回None的场景
- 异常必须在文档中说明
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, Tuple

import numpy as np

from .types import (
    PerceptionInput, PerceptionOutput,
    DriveState,
    Prediction, PredictionError,
    MemoryEntry,
    Task,
    OptimizationResult,
    SafetyEvent,
)


# =============================================================================
# 感知接口
# =============================================================================

class ISensor(ABC):
    """
    感知源接口
    
    所有感知源（系统监控、日志解析、文件监控等）必须实现此接口。
    
    生命周期：
        start() → [read()]* → stop()
    
    线程安全：
        read() 方法必须线程安全，可被多个消费者并发调用。
    """
    
    @abstractmethod
    def start(self) -> None:
        """
        启动感知源采集
        
        Precondition: 未启动或已停止
        Postcondition: running == True
        """
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """
        停止感知源采集
        
        Precondition: 已启动
        Postcondition: running == False
        """
        pass
    
    @abstractmethod
    def read(self) -> Optional[PerceptionInput]:
        """
        读取单次感知数据（非阻塞）
        
        Returns:
            PerceptionInput: 感知数据
            None: 无数据可用或采集失败
        
        异常：
            不应抛出异常，失败时返回None
        """
        pass
    
    @abstractmethod
    def encode_to_vector(self, input_data: PerceptionInput) -> PerceptionOutput:
        """
        将原始感知数据编码为28维状态向量

        Precondition:
            - input_data 不为 None
        Postcondition:
            - 返回的 PerceptionOutput.feature_vector 维度为 STATE_VECTOR_DIM
            - feature_vector 值域 [0, 1]
        """
        pass

    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            Dict 必须包含以下键：
            - status: str - "healthy" | "degraded" | "unhealthy"
            - error_rate: float - [0, 1]
            - success_count: int
            - error_count: int
        """
        pass


class IPerceptionPipeline(ABC):
    """
    感知流水线接口
    
    负责将原始感知数据转换为标准化的28维状态向量。
    """
    
    @abstractmethod
    def process(self, input_data: PerceptionInput) -> PerceptionOutput:
        """
        处理感知输入
        
        Precondition: input_data 不为 None
        Postcondition: 输出 feature_vector 维度为 STATE_VECTOR_DIM (28)
        
        Args:
            input_data: 原始感知数据
        
        Returns:
            PerceptionOutput: 标准化输出，feature_vector 值域 [0, 1]
        
        异常：
            ValueError: 输入格式不合法
        """
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, float]:
        """
        获取流水线统计
        
        Returns:
            Dict 必须包含：
            - throughput: float - 每秒处理条数
            - avg_latency_ms: float - 平均延迟（毫秒）
            - error_rate: float - [0, 1]
        """
        pass


# =============================================================================
# 驱力接口
# =============================================================================

class IDriveEngine(ABC):
    """
    驱力引擎接口
    
    根据当前状态和预测误差计算驱力状态。
    
    约束：
    - 安全驱力（SAFETY）优先级最高
    - 紧急状态下，安全驱力权重自动提升至0.9
    - 所有驱力强度值域 [0, 1]
    """
    
    @abstractmethod
    def compute(self, state_vector: np.ndarray, prediction_error: float) -> DriveState:
        """
        计算驱力状态
        
        Precondition:
            - state_vector 维度为 STATE_VECTOR_DIM (28)
            - state_vector 值域 [0, 1]
            - prediction_error >= 0
        
        Postcondition:
            - 返回的 DriveState 包含所有 DriveType
            - 各驱力 intensity 值域 [0, 1]
            - weights 之和为 1.0（允许浮点误差）
        
        Args:
            state_vector: 当前状态向量
            prediction_error: 预测误差（MSE）
        
        Returns:
            DriveState: 完整驱力状态
        """
        pass
    
    @abstractmethod
    def get_total_reward(self, drive_state: DriveState) -> float:
        """
        计算全局总奖励
        
        Returns:
            float: [0, 1] 加权驱力强度
        """
        pass


# =============================================================================
# 预测接口
# =============================================================================

class IPredictor(ABC):
    """
    预测器接口
    
    所有预测模型（GRU、Transformer、GNN、Ensemble）必须实现此接口。
    
    契约：
    - predict() 必须是无副作用的（不修改内部状态）
    - update() 是在线学习入口，可能修改模型参数
    - reset() 重置所有状态
    """
    
    @abstractmethod
    def predict(self, state_vector: np.ndarray) -> Prediction:
        """
        预测下一步状态
        
        Precondition:
            - state_vector 维度为 STATE_VECTOR_DIM (28)
            - state_vector 值域 [0, 1]
        
        Postcondition:
            - 返回的 Prediction.value 维度为 STATE_VECTOR_DIM
            - Prediction.value 值域 [0, 1]（经sigmoid/tanh约束）
            - Prediction.confidence 值域 [0, 1]
        
        Args:
            state_vector: 当前状态向量
        
        Returns:
            Prediction: 预测结果
        """
        pass
    
    @abstractmethod
    def update(self, state_vector: np.ndarray, actual_next: np.ndarray) -> PredictionError:
        """
        在线学习
        
        Precondition:
            - state_vector 和 actual_next 维度均为 STATE_VECTOR_DIM
            - 值域 [0, 1]
        
        Postcondition:
            - 模型参数可能被更新
            - 返回的 PredictionError.mse >= 0
        
        Args:
            state_vector: 当前状态
            actual_next: 实际下一状态（作为监督信号）
        
        Returns:
            PredictionError: 预测误差统计
        """
        pass
    
    @abstractmethod
    def reset(self) -> None:
        """
        重置预测器状态
        
        Postcondition: 所有内部状态（隐藏状态、序列缓冲区等）清零
        """
        pass


# =============================================================================
# 记忆接口
# =============================================================================

class IMemory(ABC):
    """
    记忆系统接口
    
    支持存储、检索、更新记忆条目。
    """
    
    @abstractmethod
    def store(self, entry: MemoryEntry) -> str:
        """
        存储记忆
        
        Precondition: entry 不为 None
        Postcondition: 返回唯一ID
        
        Returns:
            str: 记忆条目ID
        """
        pass
    
    @abstractmethod
    def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        """
        检索记忆
        
        Args:
            entry_id: 记忆ID
        
        Returns:
            MemoryEntry or None（不存在）
        """
        pass
    
    @abstractmethod
    def update_value(self, entry_id: str, value_score: float) -> bool:
        """
        更新记忆价值
        
        Precondition: value_score 值域 [0, 1]
        
        Returns:
            bool: 是否成功更新
        """
        pass


# =============================================================================
# 任务接口
# =============================================================================

class ITaskGenerator(ABC):
    """
    任务生成器接口
    
    根据驱力状态生成可执行任务。
    """
    
    @abstractmethod
    def generate(self, drive_state: DriveState, state_vector: np.ndarray) -> List[Task]:
        """
        生成任务列表
        
        Precondition:
            - drive_state 不为 None
            - state_vector 维度为 STATE_VECTOR_DIM
        
        Postcondition:
            - 返回的任务列表无重复（相同name且PENDING状态）
            - 任务优先级已排序（CRITICAL > HIGH > NORMAL）
        
        Returns:
            List[Task]: 任务列表（可能为空）
        """
        pass
    
    @abstractmethod
    def complete_task(self, task_id: str, reward: float) -> bool:
        """
        完成任务
        
        Precondition: reward 值域 [-1, 1]
        
        Returns:
            bool: 是否成功找到并完成任务
        """
        pass


# =============================================================================
# 优化器接口
# =============================================================================

class IOptimizer(ABC):
    """
    优化器接口
    
    支持在线和离线两种优化模式。
    """
    
    @abstractmethod
    def optimize(self, predictor: IPredictor, data: Any) -> OptimizationResult:
        """
        执行优化
        
        Args:
            predictor: 待优化的预测器
            data: 优化数据（经验缓冲区或数据集）
        
        Returns:
            OptimizationResult: 优化结果
        """
        pass


# =============================================================================
# 安全接口
# =============================================================================

class ISafetyMonitor(ABC):
    """
    安全监控接口

    监控资源使用和边界约束。
    """

    @abstractmethod
    def check(self) -> List[SafetyEvent]:
        """
        检查安全状态

        Returns:
            List[SafetyEvent]: 安全事件列表（空列表表示正常）
        """
        pass

    @abstractmethod
    def is_within_limits(self) -> bool:
        """
        检查是否在资源限制内

        Returns:
            bool: True if all limits satisfied
        """
        pass


# =============================================================================
# 阶段1-6 新组件接口（秩序化阶段2：接口契约秩序化）
# 第一性原理：模块间通信应通过明确的契约（接口）而非具体实现。
# 6个新阶段组件必须有对应接口，确保可Mock注入、可替换。
# =============================================================================

class IGoalDrivenLoop(ABC):
    """
    目标驱动循环接口（阶段1）

    管理长任务目标的设定、分解、执行和持久化。
    """

    @abstractmethod
    def set_long_task(self, description: str, sub_tasks: List[str],
                      priority: float, deadline_hours: float,
                      steps_per_subgoal: int) -> str:
        """设定长任务目标并分解为子目标序列，返回父目标ID"""
        pass

    @abstractmethod
    def has_active_goal(self) -> bool:
        """是否有活跃的未完成目标"""
        pass

    @abstractmethod
    def execute_step(self, state_vector: np.ndarray,
                     action_executor: Any) -> Dict[str, Any]:
        """执行一步目标驱动，返回执行结果"""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """获取目标驱动状态"""
        pass


class ISkillLibrary(ABC):
    """
    技能库接口（阶段2）

    管理技能的注册、验证、调用和习得。
    """

    @abstractmethod
    def register(self, name: str, description: str, code: str,
                 auto_validate: bool = True) -> Dict[str, Any]:
        """注册新技能"""
        pass

    @abstractmethod
    def invoke(self, name: str, **kwargs) -> Dict[str, Any]:
        """调用技能"""
        pass

    @abstractmethod
    def learn_from_requirement(self, requirement: str,
                               skill_name: Optional[str] = None) -> Dict[str, Any]:
        """从需求描述生成并习得技能"""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """获取技能库统计"""
        pass


class ICollaborator(ABC):
    """
    多agent协作接口（阶段3）

    封装通信/发现/分派/共识四要素。
    """

    @abstractmethod
    def register_capability(self, task_type: str, handler: Any) -> None:
        """注册本agent能处理的任务类型"""
        pass

    @abstractmethod
    def broadcast_heartbeat(self, load_score: float = 0.0,
                            metadata: Optional[Dict[str, Any]] = None) -> None:
        """广播心跳"""
        pass

    @abstractmethod
    def dispatch_task(self, task_type: str, payload: Dict[str, Any],
                      required_capability: Optional[str] = None,
                      on_result: Optional[Any] = None) -> Tuple[str, Any]:
        """分派任务到最佳邻居"""
        pass

    @abstractmethod
    def process_messages(self, max_messages: int = 100) -> int:
        """处理收到的消息"""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """获取协作状态"""
        pass


class ILongTaskOrchestrator(ABC):
    """
    长任务编排接口（阶段4）

    整合目标驱动、技能库、多agent协作，实现自驱长任务执行。
    """

    @abstractmethod
    def start_task(self, description: str,
                   phases: List[List[Dict[str, Any]]],
                   metadata: Optional[Dict[str, Any]] = None) -> str:
        """启动长任务，返回task_id"""
        pass

    @abstractmethod
    def execute_next(self) -> Dict[str, Any]:
        """执行下一步"""
        pass

    @abstractmethod
    def checkpoint(self) -> Any:
        """保存断点"""
        pass

    @abstractmethod
    def resume(self, task_id: str) -> bool:
        """从断点恢复"""
        pass

    @abstractmethod
    def get_progress(self) -> Dict[str, Any]:
        """获取进度"""
        pass


class ISkillEvolution(ABC):
    """
    技能进化接口（阶段5）

    评估技能性能，自动优化低性能技能，回滚退化版本。
    """

    @abstractmethod
    def evaluate(self, skill_name: str) -> Any:
        """评估单个技能性能"""
        pass

    @abstractmethod
    def optimize(self, skill_name: str) -> Dict[str, Any]:
        """自动优化技能代码"""
        pass

    @abstractmethod
    def run_evolution_cycle(self) -> Dict[str, Any]:
        """运行一个技能进化周期"""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """获取进化引擎状态"""
        pass


class ISelfOrganization(ABC):
    """
    自组织接口（阶段6）

    管理角色分化、组队和共识决策。
    """

    @abstractmethod
    def assign_role(self, role: Any, reason: str = "") -> None:
        """分配/变更角色"""
        pass

    @abstractmethod
    def get_role(self) -> Any:
        """获取当前角色"""
        pass

    @abstractmethod
    def form_team(self, task_description: str,
                  required_capabilities: List[str],
                  team_members: Optional[List[str]] = None) -> Any:
        """基于能力组队"""
        pass

    @abstractmethod
    def propose_decision(self, decision_id: str,
                         proposal: Dict[str, Any],
                         participant_ids: Optional[List[str]] = None,
                         on_approved: Optional[Any] = None) -> Dict[str, Any]:
        """发起共识决策"""
        pass

    @abstractmethod
    def run_organization_cycle(self) -> Dict[str, Any]:
        """运行自组织周期"""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """获取自组织状态"""
        pass
