"""
配置管理

第一性原理：人脑的行为受内部状态和外部环境共同调节。
配置系统模拟这种"内部状态"，允许Agent根据环境动态调整参数。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional
import json


@dataclass
class AgentConfig:
    """
    Agent配置类
    
    第一性原理：生物体的行为由基因（固定配置）和环境适应（动态调整）共同决定。
    AgentConfig包含"基因级"的固定参数和可动态调整的"适应级"参数。
    """
    
    # === 基础配置（基因级 —— 启动后不可变） ===
    agent_name: str = "SelfEvolvingAgent"
    version: str = "1.0.0"
    log_level: str = "INFO"
    data_dir: str = "./data"
    state_vector_dim: int = 28  # 统一状态向量维度，与 core.types 保持一致
    
    # === 资源限制（刚性边界） ===
    max_cpu_percent: float = 20.0
    max_memory_mb: float = 512.0
    max_disk_gb: float = 10.0
    
    # === 运行配置（适应级 —— 可动态调整） ===
    main_loop_interval_ms: int = 1000
    enable_offline_review: bool = True
    idle_threshold_seconds: int = 300
    
    # === 感知配置 ===
    perception_interval_ms: int = 1000
    anomaly_threshold: float = 0.7
    state_history_window: int = 60
    
    # === 驱力权重（适应级 —— 驱力引擎动态调整） ===
    safety_weight: float = 0.4
    gain_weight: float = 0.4
    efficiency_weight: float = 0.2
    exploration_weight: float = 0.0
    
    # === 探索-利用 ===
    exploration_ratio: float = 0.30
    exploration_bonus: float = 0.3
    
    # === 任务系统 ===
    max_task_pool_size: int = 100
    task_timeout_seconds: int = 300
    max_concurrent_tasks: int = 3
    
    # === 预测模型 ===
    prediction_horizon: int = 10
    gru_hidden_dim: int = 64
    gru_num_layers: int = 2
    online_learning_rate: float = 0.001
    model_save_interval: int = 1000
    
    # === 记忆系统 ===
    short_term_memory_size: int = 10000
    long_term_db_path: str = "./data/memory.db"
    snapshot_dir: str = "./data/snapshots"
    replay_buffer_size: int = 1000
    
    # === 优化器 ===
    enable_structural_evolution: bool = False  # MVP阶段禁用
    offline_review_interval_hours: int = 24
    max_optimization_iterations: int = 3
    
    # === 安全约束 ===
    forbidden_paths: List[str] = field(default_factory=lambda: [
        "/etc", "/usr/bin", "/bin", "/sbin", "/sys", "/proc"
    ])
    max_exploration_without_reward: int = 5
    enable_auto_rollback: bool = True
    emergency_cpu_threshold: float = 0.95
    emergency_mem_threshold: float = 0.95
    emergency_disk_threshold: float = 0.95

    # === 执行配置（阶段1：集成打通） ===
    # 第一性原理：运动皮层输出需经过小脑审核才能驱动肌肉。
    # execution_dry_run=True 时只打印命令不执行（安全默认），
    # 生产环境显式设为 False 才会真正执行系统操作。
    execution_dry_run: bool = True

    # === 持久化状态加载（秩序化阶段1：测试数据隔离） ===
    # 第一性原理：构造函数不应有副作用。状态加载是运行时行为，应在 start() 中执行。
    # auto_load_state=True 时，start() 会自动调用 load_state() 加载持久化状态。
    # 测试中设为 False 可避免加载被污染的状态，实现测试隔离。
    auto_load_state: bool = True

    # === 阶段1-6 组件配置（秩序化阶段4：配置秩序化） ===
    # 第一性原理：所有可配置参数应纳入 AgentConfig，而非硬编码在 agent.py。
    # 这样可通过配置文件/环境变量统一调整，无需修改代码。
    # 阶段1：目标驱动循环
    working_memory_capacity: int = 7
    # 阶段2：技能库
    skill_max_count: int = 100
    # 阶段3：多agent协作
    collaboration_heartbeat_interval_seconds: float = 3.0
    # 阶段5：技能进化
    skill_evolution_min_invocations: int = 3

    # === 进化目标 ===
    precision_target: float = 0.01
    coverage_target: float = 0.95
    efficiency_target: float = 0.1
    
    def validate(self) -> List[str]:
        """验证配置有效性"""
        errors = []
        
        if self.max_cpu_percent <= 0 or self.max_cpu_percent > 100:
            errors.append("max_cpu_percent must be in (0, 100]")
        
        if self.max_memory_mb <= 0:
            errors.append("max_memory_mb must be positive")
        
        weight_sum = (self.safety_weight + self.gain_weight + 
                      self.efficiency_weight + self.exploration_weight)
        if abs(weight_sum - 1.0) > 0.01:
            errors.append(f"Drive weights must sum to 1.0, got {weight_sum}")
        
        if self.exploration_ratio < 0 or self.exploration_ratio > 1:
            errors.append("exploration_ratio must be in [0, 1]")
        
        if self.main_loop_interval_ms < 100:
            errors.append("main_loop_interval_ms must be >= 100")
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentConfig:
        """从字典创建配置"""
        # 过滤掉不存在的字段
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)
    
    def save(self, path: str) -> None:
        """保存配置到JSON文件"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def load(cls, path: str) -> AgentConfig:
        """从JSON文件加载配置"""
        with open(path, 'r') as f:
            data = json.load(f)
        config = cls.from_dict(data)
        errors = config.validate()
        if errors:
            raise ValueError(f"Config validation failed: {errors}")
        return config
