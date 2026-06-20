"""
驱力引擎

第一性原理：人脑的动机系统通过多巴胺预测误差驱动行为。
驱力引擎将预测误差转换为行动动机，实现"缺口驱动"的自主目标生成。
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple
import numpy as np

from core import DriveType, Drive, DriveState
from core import STATE_VECTOR_DIM, STATE_IDX_CPU_OVERALL, STATE_IDX_MEM_USED, STATE_IDX_DISK_USED
from core.interfaces import IDriveEngine


class DriveEngine(IDriveEngine):
    """
    驱力引擎
    
    计算安全、收益、能效三种核心驱力，支持冲突消解和动态权重调整。
    """
    
    def __init__(self,
                 config_or_safety_weight=None,
                 gain_weight: float = 0.4,
                 efficiency_weight: float = 0.2,
                 emergency_threshold: float = 0.95,
                 steady_state_threshold: float = 0.05):
        # 支持 AgentConfig 作为第一个参数
        if hasattr(config_or_safety_weight, 'safety_weight'):
            config = config_or_safety_weight
            safety_weight = config.safety_weight
            gain_weight = config.gain_weight
            efficiency_weight = config.efficiency_weight
            # 可选：从配置读取更多参数
            emergency_threshold = getattr(config, 'emergency_threshold', emergency_threshold)
            steady_state_threshold = getattr(config, 'steady_state_threshold', steady_state_threshold)
        else:
            safety_weight = config_or_safety_weight if config_or_safety_weight is not None else 0.4

        self.weights = {
            DriveType.SAFETY: safety_weight,
            DriveType.GAIN: gain_weight,
            DriveType.EFFICIENCY: efficiency_weight,
        }
        # 保存用户配置的初始权重作为平滑恢复的目标值
        # （避免_smooth_weights硬编码0.4/0.4/0.2覆盖用户配置）
        self._target_weights = {
            DriveType.SAFETY: safety_weight,
            DriveType.GAIN: gain_weight,
            DriveType.EFFICIENCY: efficiency_weight,
        }
        self.emergency_threshold = emergency_threshold
        self.steady_state_threshold = steady_state_threshold
        
        # 历史误差窗口（用于稳态检测）
        self._error_history = []
        self._max_history = 100
        
        # 上次驱力状态
        self._last_state = DriveState()
    
    def compute(self, 
                state_vector: np.ndarray,
                prediction_error: float = 0.0) -> DriveState:
        """
        计算当前驱力状态
        
        Args:
            state_vector: 28维状态向量
            prediction_error: 预测误差（用于收益驱力）
        
        Returns:
            DriveState: 完整的驱力状态
        """
        current_time = __import__('time').time()
        
        # 1. 计算各驱力
        safety_drive = self._compute_safety(state_vector)
        gain_drive = self._compute_gain(prediction_error)
        efficiency_drive = self._compute_efficiency(state_vector)
        
        drives = {
            DriveType.SAFETY: safety_drive,
            DriveType.GAIN: gain_drive,
            DriveType.EFFICIENCY: efficiency_drive,
        }
        
        # 2. 检测紧急状态
        emergency = self._detect_emergency(state_vector)
        if emergency:
            safety_drive.intensity = 1.0
            safety_drive.priority = 1
        
        # 3. 检测稳态
        steady_state = self._detect_steady_state(prediction_error)
        
        # 4. 冲突消解（安全绝对优先）
        if emergency:
            self.weights[DriveType.SAFETY] = 0.9
            self.weights[DriveType.GAIN] = 0.05
            self.weights[DriveType.EFFICIENCY] = 0.05
        else:
            # 正常情况下的权重平滑恢复
            self._smooth_weights()
        
        # 5. 归一化权重
        total = sum(self.weights.values())
        if total > 0:
            for k in self.weights:
                self.weights[k] /= total
        
        state = DriveState(
            drives=drives,
            weights=self.weights.copy(),
            emergency=bool(emergency),
            steady_state=bool(steady_state),
        )
        
        self._last_state = state
        return state
    
    def _compute_safety(self, state_vector: np.ndarray) -> Drive:
        """计算安全驱力"""
        # 提取风险指标
        cpu = state_vector[STATE_IDX_CPU_OVERALL]
        mem = state_vector[STATE_IDX_MEM_USED]
        disk = state_vector[STATE_IDX_DISK_USED]
        
        # 加权风险
        risks = [cpu, mem, disk]
        weights = [0.4, 0.4, 0.2]
        weighted_risk = sum(r * w for r, w in zip(risks, weights))
        
        # 安全驱力 = 1 - exp(-lambda * risk)
        intensity = 1.0 - np.exp(-3.0 * weighted_risk)
        
        # 紧急状态检测
        is_emergency = any(r > self.emergency_threshold for r in risks)
        priority = 1 if is_emergency else 3
        
        return Drive(
            drive_type=DriveType.SAFETY,
            intensity=float(np.clip(intensity, 0, 1)),
            priority=priority,
        )
    
    def _compute_gain(self, prediction_error: float) -> Drive:
        """计算收益驱力（认知缺口）"""
        # 收益驱力与预测误差正相关
        # 误差越大 = 认知缺口越大 = 收益驱力越强
        intensity = np.tanh(prediction_error * 2.0)
        
        return Drive(
            drive_type=DriveType.GAIN,
            intensity=float(np.clip(intensity, 0, 1)),
            priority=2,
        )
    
    def _compute_efficiency(self, state_vector: np.ndarray) -> Drive:
        """计算能效驱力"""
        # 能效驱力与资源使用负相关
        # 资源使用越高 = 能效越低 = 能效驱力越强
        cpu = state_vector[STATE_IDX_CPU_OVERALL]
        mem = state_vector[STATE_IDX_MEM_USED]
        
        resource_usage = (cpu + mem) / 2.0
        intensity = resource_usage  # 资源使用越高，越需要优化能效
        
        return Drive(
            drive_type=DriveType.EFFICIENCY,
            intensity=float(np.clip(intensity, 0, 1)),
            priority=4,
        )
    
    def _detect_emergency(self, state_vector: np.ndarray) -> bool:
        """检测紧急状态"""
        cpu = state_vector[STATE_IDX_CPU_OVERALL]
        mem = state_vector[STATE_IDX_MEM_USED]
        disk = state_vector[STATE_IDX_DISK_USED]
        
        return cpu > self.emergency_threshold or \
               mem > self.emergency_threshold or \
               disk > self.emergency_threshold
    
    def _detect_steady_state(self, prediction_error: float) -> bool:
        """检测稳态（误差持续低）"""
        self._error_history.append(prediction_error)
        if len(self._error_history) > self._max_history:
            self._error_history.pop(0)
        
        if len(self._error_history) < 20:
            return False
        
        recent_errors = self._error_history[-20:]
        mean_error = np.mean(recent_errors)
        std_error = np.std(recent_errors)
        
        # 稳态：误差低且稳定
        return mean_error < self.steady_state_threshold and std_error < self.steady_state_threshold
    
    def _smooth_weights(self, alpha: float = 0.9) -> None:
        """平滑权重恢复（指数平滑，向用户配置的初始权重收敛）"""
        for k in self.weights:
            target = self._target_weights.get(k, self.weights[k])
            self.weights[k] = alpha * self.weights[k] + (1 - alpha) * target
    
    def get_total_reward(self, drive_state: DriveState) -> float:
        """计算全局总奖励"""
        total = 0.0
        for drive_type, drive in drive_state.drives.items():
            weight = drive_state.weights.get(drive_type, 0.0)
            total += weight * drive.intensity
        return float(np.clip(total, 0, 1))
