# 第三十二章：模块详细设计与接口规范

## 32.1 模块接口设计原则

### 32.1.1 接口设计哲学

自驱永续进化Agent系统的模块接口设计遵循以下核心原则：

**1. 最小暴露原则**
每个模块仅暴露必要的操作接口，隐藏内部实现细节。这确保模块间的松耦合，便于独立进化。

**2. 异步优先原则**
所有可能阻塞的接口均采用异步设计，确保主循环不会被单点阻塞。

**3. 版本兼容原则**
接口支持版本控制，允许模块独立升级而不破坏整体系统。

**4. 可观测原则**
每个接口调用都产生可追踪的日志和指标，便于调试和优化。

### 32.1.2 接口规范模板

```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import asyncio

class ModuleInterface(ABC):
    """
    模块接口基类
    
    所有功能模块必须实现此接口
    """
    
    @property
    @abstractmethod
    def version(self) -> str:
        """返回模块版本号，格式：major.minor.patch"""
        pass
        
    @property
    @abstractmethod
    def module_name(self) -> str:
        """返回模块唯一标识名"""
        pass
        
    @abstractmethod
    async def initialize(self, config: Dict[str, Any]) -> bool:
        """
        初始化模块
        
        Args:
            config: 模块配置字典
            
        Returns:
            初始化是否成功
            
        Raises:
            InitializationError: 初始化失败时抛出
        """
        pass
        
    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            {
                'status': 'healthy' | 'degraded' | 'unhealthy',
                'metrics': {},
                'last_error': Optional[str]
            }
        """
        pass
        
    @abstractmethod
    async def shutdown(self) -> None:
        """优雅关闭模块，释放资源"""
        pass
```

## 32.2 感知模块详细接口

### 32.2.1 感知模块接口定义

```python
from dataclasses import dataclass
from typing import List, Callable, AsyncIterator
import numpy as np

@dataclass(frozen=True)
class PerceptionData:
    """感知数据不可变对象"""
    timestamp: float
    sensor_id: str
    raw_value: Any
    processed_value: np.ndarray
    confidence: float
    metadata: Dict[str, Any]

class PerceptionModule(ModuleInterface):
    """
    环境感知模块
    
    负责采集、处理、标准化环境数据
    """
    
    @abstractmethod
    async def register_sensor(
        self,
        sensor_id: str,
        sensor_type: str,
        sampling_rate: float,
        handler: Callable[[], Any]
    ) -> None:
        """
        注册传感器
        
        Args:
            sensor_id: 传感器唯一标识
            sensor_type: 传感器类型（system/log/file/self）
            sampling_rate: 采样频率（Hz）
            handler: 数据采集回调函数
        """
        pass
        
    @abstractmethod
    async def unregister_sensor(self, sensor_id: str) -> None:
        """注销传感器"""
        pass
        
    @abstractmethod
    async def perceive(self, sensor_types: Optional[List[str]] = None) -> Dict[str, PerceptionData]:
        """
        执行感知采集
        
        Args:
            sensor_types: 指定采集的传感器类型，None表示全部
            
        Returns:
            {sensor_id: PerceptionData}
        """
        pass
        
    @abstractmethod
    async def stream_perception(self, sensor_types: Optional[List[str]] = None) -> AsyncIterator[PerceptionData]:
        """
        流式感知数据
        
        Yields:
            持续产生的感知数据
        """
        pass
        
    @abstractmethod
    async def get_perception_history(
        self,
        start_time: float,
        end_time: float,
        sensor_id: Optional[str] = None
    ) -> List[PerceptionData]:
        """获取历史感知数据"""
        pass
        
    @abstractmethod
    async def calibrate_sensor(self, sensor_id: str, calibration_data: Dict) -> bool:
        """校准传感器"""
        pass
```

### 32.2.2 传感器实现示例

```python
class SystemSensor:
    """系统资源传感器"""
    
    def __init__(self):
        self.last_cpu_times = None
        self.last_net_io = None
        
    async def sample(self) -> Dict[str, float]:
        """采集系统指标"""
        import psutil
        
        # CPU（非阻塞方式）
        cpu_percent = psutil.cpu_percent(interval=None)
        
        # 内存
        mem = psutil.virtual_memory()
        
        # 磁盘
        disk = psutil.disk_usage('/')
        
        # 网络速率计算
        net_io = psutil.net_io_counters()
        net_rate = 0
        if self.last_net_io:
            time_delta = time.time() - self.last_net_io['time']
            if time_delta > 0:
                bytes_delta = (net_io.bytes_sent + net_io.bytes_recv - 
                              self.last_net_io['bytes_total'])
                net_rate = bytes_delta / time_delta / 1024 / 1024  # MB/s
                
        self.last_net_io = {
            'time': time.time(),
            'bytes_total': net_io.bytes_sent + net_io.bytes_recv
        }
        
        return {
            'cpu_percent': cpu_percent,
            'memory_percent': mem.percent,
            'memory_available_gb': mem.available / (1024**3),
            'disk_percent': disk.percent,
            'disk_free_gb': disk.free / (1024**3),
            'network_rate_mbps': net_rate,
            'process_count': len(psutil.pids()),
            'load_average_1m': os.getloadavg()[0] if hasattr(os, 'getloadavg') else 0
        }
```

## 32.3 驱力引擎详细接口

### 32.3.1 驱力引擎接口定义

```python
from enum import Enum, auto
from typing import Tuple

class DriveType(Enum):
    SAFE = auto()  # 安全驱力
    GAIN = auto()  # 收益驱力
    EFF = auto()   # 能效驱力

@dataclass
class DriveVector:
    """驱力向量"""
    safe: float  # [0, 1]
    gain: float  # [0, 1]
    eff: float   # [0, 1]
    
    def __post_init__(self):
        # 自动裁剪到有效范围
        object.__setattr__(self, 'safe', max(0.0, min(1.0, self.safe)))
        object.__setattr__(self, 'gain', max(0.0, min(1.0, self.gain)))
        object.__setattr__(self, 'eff', max(0.0, min(1.0, self.eff)))
        
    @property
    def dominant(self) -> DriveType:
        """返回主导驱力类型"""
        values = [(DriveType.SAFE, self.safe), 
                  (DriveType.GAIN, self.gain), 
                  (DriveType.EFF, self.eff)]
        return max(values, key=lambda x: x[1])[0]

@dataclass
class WeightVector:
    """权重向量"""
    w_safe: float
    w_gain: float
    w_eff: float
    
    def __post_init__(self):
        # 自动归一化
        total = self.w_safe + self.w_gain + self.w_eff
        if total > 0:
            object.__setattr__(self, 'w_safe', self.w_safe / total)
            object.__setattr__(self, 'w_gain', self.w_gain / total)
            object.__setattr__(self, 'w_eff', self.w_eff / total)

@dataclass
class GapVector:
    """缺口向量"""
    safe_gap: float
    gain_gap: float
    eff_gap: float
    
    @property
    def total_gap(self) -> float:
        return self.safe_gap + self.gain_gap + self.eff_gap
        
    @property
    def dominant_gap(self) -> DriveType:
        gaps = [(DriveType.SAFE, self.safe_gap),
                (DriveType.GAIN, self.gain_gap),
                (DriveType.EFF, self.eff_gap)]
        return max(gaps, key=lambda x: x[1])[0]

class DriveEngine(ModuleInterface):
    """
    驱力引擎模块
    
    计算原生驱力、动态权重、价值缺口
    """
    
    @abstractmethod
    async def compute_drives(self, perception: Dict[str, PerceptionData]) -> DriveVector:
        """
        计算当前驱力状态
        
        Args:
            perception: 感知数据
            
        Returns:
            驱力向量
        """
        pass
        
    @abstractmethod
    async def compute_weights(self, drives: DriveVector, context: Dict) -> WeightVector:
        """
        计算动态权重
        
        Args:
            drives: 当前驱力
            context: 上下文信息（紧急状态、资源状况等）
            
        Returns:
            权重向量
        """
        pass
        
    @abstractmethod
    async def compute_gaps(self, drives: DriveVector, weights: WeightVector) -> GapVector:
        """
        计算价值缺口
        
        Args:
            drives: 驱力向量
            weights: 权重向量
            
        Returns:
            缺口向量
        """
        pass
        
    @abstractmethod
    async def update_base_weights(self, new_weights: WeightVector) -> None:
        """更新基础权重（人工干预接口）"""
        pass
        
    @abstractmethod
    async def get_drive_history(self, n: int = 100) -> List[Tuple[float, DriveVector]]:
        """获取驱力历史"""
        pass
```

## 32.4 任务生成模块详细接口

### 32.4.1 任务模型定义

```python
from enum import Enum
from typing import Set, Optional
import uuid

class TaskPriority(Enum):
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    BACKGROUND = 4

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    FROZEN = "frozen"

@dataclass
class Task:
    """任务定义"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    task_type: DriveType = DriveType.GAIN
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    
    # 评分相关
    expected_reward: float = 0.0
    expected_cost: float = 0.0
    novelty_score: float = 0.0
    success_rate: float = 0.5
    
    # 执行相关
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    execution_count: int = 0
    
    # 依赖关系
    dependencies: Set[str] = field(default_factory=set)
    
    # 元数据
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def score(self) -> float:
        """计算任务综合得分"""
        if self.execution_count > 0:
            return (self.expected_reward * self.success_rate - 
                   self.expected_cost + 
                   self.novelty_score * 0.1)
        return self.expected_reward * 0.5 + self.novelty_score * 0.5
        
    @property
    def is_executable(self) -> bool:
        """检查任务是否可执行"""
        return self.status == TaskStatus.PENDING and len(self.dependencies) == 0

class TaskGenerator(ModuleInterface):
    """
    任务生成模块
    
    根据缺口动态生成、更新、淘汰任务
    """
    
    @abstractmethod
    async def generate_tasks(self, gap: GapVector, perception: Dict) -> List[Task]:
        """
        根据缺口生成候选任务
        
        Args:
            gap: 价值缺口
            perception: 当前感知状态
            
        Returns:
            候选任务列表
        """
        pass
        
    @abstractmethod
    async def evaluate_task(self, task: Task) -> float:
        """
        评估任务价值
        
        Returns:
            任务得分
        """
        pass
        
    @abstractmethod
    async def add_task(self, task: Task) -> bool:
        """添加任务到任务池"""
        pass
        
    @abstractmethod
    async def remove_task(self, task_id: str) -> bool:
        """从任务池移除任务"""
        pass
        
    @abstractmethod
    async def get_task_pool(self, status: Optional[TaskStatus] = None) -> List[Task]:
        """获取任务池"""
        pass
        
    @abstractmethod
    async def update_task_status(self, task_id: str, status: TaskStatus, result: Optional[Dict] = None) -> bool:
        """更新任务状态"""
        pass
        
    @abstractmethod
    async def cleanup_stale_tasks(self, max_age_seconds: float = 3600) -> int:
        """清理过期任务，返回清理数量"""
        pass
```

## 32.5 决策模块详细接口

### 32.5.1 决策模块接口定义

```python
from typing import Tuple

class DecisionRecord:
    """决策记录"""
    def __init__(self):
        self.timestamp: float = time.time()
        self.selected_task: Optional[Task] = None
        self.candidate_tasks: List[Task] = []
        self.exploration_mode: bool = False
        self.drive_state: Optional[DriveVector] = None
        self.reasoning: str = ""
        
class DecisionMaker(ModuleInterface):
    """
    决策模块
    
    负责任务选择、探索-利用平衡、动态中断
    """
    
    @abstractmethod
    async def select_task(
        self,
        task_pool: List[Task],
        drives: DriveVector,
        exploration_ratio: float = 0.3
    ) -> Tuple[Optional[Task], DecisionRecord]:
        """
        选择最优任务
        
        Args:
            task_pool: 候选任务池
            drives: 当前驱力状态
            exploration_ratio: 探索比例
            
        Returns:
            (选中的任务, 决策记录)
        """
        pass
        
    @abstractmethod
    async def should_interrupt(
        self,
        current_task: Task,
        new_gap: GapVector,
        emergency: bool = False
    ) -> bool:
        """
        判断是否中断当前任务
        
        Args:
            current_task: 当前执行的任务
            new_gap: 新的缺口状态
            emergency: 是否紧急状态
            
        Returns:
            是否中断
        """
        pass
        
    @abstractmethod
    async def update_exploration_ratio(self, performance_history: List[float]) -> float:
        """
        动态调整探索比例
        
        Args:
            performance_history: 近期性能历史
            
        Returns:
            新的探索比例
        """
        pass
        
    @abstractmethod
    async def get_decision_history(self, n: int = 100) -> List[DecisionRecord]:
        """获取决策历史"""
        pass
```

## 32.6 预测模块详细接口

### 32.6.1 预测模块接口定义

```python
from typing import TypeVar, Generic

T = TypeVar('T')

class PredictionResult(Generic[T]):
    """预测结果"""
    def __init__(self):
        self.value: T
        self.confidence: float
        self.horizon: int
        self.model_version: str
        self.prediction_time: float
        
class PredictionModel(ABC, Generic[T]):
    """预测模型基类"""
    
    @abstractmethod
    async def predict(self, input_data: np.ndarray, horizon: int = 1) -> PredictionResult[T]:
        """执行预测"""
        pass
        
    @abstractmethod
    async def update(self, actual: T, predicted: T) -> float:
        """更新模型，返回误差"""
        pass
        
    @abstractmethod
    async def evaluate(self, test_data: List[Tuple[np.ndarray, T]]) -> Dict[str, float]:
        """评估模型性能"""
        pass
        
    @abstractmethod
    async def save(self, path: str) -> bool:
        """保存模型"""
        pass
        
    @abstractmethod
    async def load(self, path: str) -> bool:
        """加载模型"""
        pass

class MultiLevelPredictor(ModuleInterface):
    """
    多层预测器
    
    底层：高频微预测
    中层：中频趋势预测
    高层：低频抽象预测
    """
    
    @abstractmethod
    async def predict_low_level(self, data: np.ndarray, horizon: int = 1) -> PredictionResult:
        """底层高频预测"""
        pass
        
    @abstractmethod
    async def predict_mid_level(self, data: np.ndarray, horizon: int = 5) -> PredictionResult:
        """中层中频预测"""
        pass
        
    @abstractmethod
    async def predict_high_level(self, data: np.ndarray, horizon: int = 20) -> PredictionResult:
        """高层低频预测"""
        pass
        
    @abstractmethod
    async def ensemble_predict(self, data: np.ndarray, horizon: int = 1) -> PredictionResult:
        """集成预测（融合三层）"""
        pass
        
    @abstractmethod
    async def get_prediction_error(self, level: str = "ensemble") -> float:
        """获取预测误差"""
        pass
        
    @abstractmethod
    async def trigger_rebuild(self, level: Optional[str] = None) -> bool:
        """触发模型重构"""
        pass
```

## 32.7 记忆模块详细接口

### 32.7.1 记忆模块接口定义

```python
from typing import TypeVar

M = TypeVar('M')

class MemoryEntry(Generic[M]):
    """记忆条目"""
    def __init__(self):
        self.id: str
        self.content: M
        self.importance: float  # [0, 1]
        self.created_at: float
        self.last_accessed: float
        self.access_count: int
        self.tags: Set[str]

class MemorySystem(ModuleInterface):
    """
    记忆系统
    
    在线短期记忆 + 离线长期记忆
    """
    
    @abstractmethod
    async def store_short_term(self, entry: MemoryEntry) -> bool:
        """存储到短期记忆"""
        pass
        
    @abstractmethod
    async def store_long_term(self, entry: MemoryEntry) -> bool:
        """存储到长期记忆"""
        pass
        
    @abstractmethod
    async def retrieve(self, query: str, limit: int = 10) -> List[MemoryEntry]:
        """
        检索记忆
        
        Args:
            query: 检索查询
            limit: 返回数量限制
            
        Returns:
            匹配的记忆条目
        """
        pass
        
    @abstractmethod
    async def consolidate(self, strategy: str = "importance") -> int:
        """
        记忆巩固（短期→长期）
        
        Args:
            strategy: 巩固策略
            
        Returns:
            巩固的条目数量
        """
        pass
        
    @abstractmethod
    async def forget(self, threshold: float = 0.1) -> int:
        """
        遗忘低价值记忆
        
        Args:
            threshold: 重要性阈值
            
        Returns:
            遗忘的条目数量
        """
        pass
        
    @abstractmethod
    async def save_snapshot(self, name: str) -> str:
        """保存系统快照"""
        pass
        
    @abstractmethod
    async def load_snapshot(self, snapshot_id: str) -> bool:
        """加载系统快照"""
        pass
```

## 32.8 安全守护模块详细接口

### 32.8.1 安全守护模块接口定义

```python
class SafetyViolation:
    """安全违规记录"""
    def __init__(self):
        self.timestamp: float
        self.violation_type: str
        self.severity: str  # "low", "medium", "high", "critical"
        self.description: str
        self.action_taken: str
        
class SafetyGuard(ModuleInterface):
    """
    安全守护模块
    
    实施刚性边界约束
    """
    
    @abstractmethod
    async def check_task(self, task: Task) -> Tuple[bool, Optional[SafetyViolation]]:
        """
        检查任务是否安全
        
        Returns:
            (是否通过, 违规记录)
        """
        pass
        
    @abstractmethod
    async def check_resource_usage(self) -> Tuple[bool, Dict[str, float]]:
        """
        检查资源使用
        
        Returns:
            (是否在限制内, 当前使用量)
        """
        pass
        
    @abstractmethod
    async def check_file_access(self, path: str, operation: str) -> bool:
        """检查文件访问权限"""
        pass
        
    @abstractmethod
    async def enforce_limits(self) -> List[str]:
        """
        强制执行限制
        
        Returns:
            采取的措施列表
        """
        pass
        
    @abstractmethod
    async def get_violation_history(self, n: int = 100) -> List[SafetyViolation]:
        """获取违规历史"""
        pass
        
    @abstractmethod
    async def add_rule(self, rule: str, condition: Callable, action: Callable) -> bool:
        """动态添加安全规则"""
        pass
```

## 32.9 模块间通信规范

### 32.9.1 事件总线设计

```python
from typing import Callable, Awaitable
import asyncio

class EventBus:
    """
    模块间事件总线
    
    实现发布-订阅模式，解耦模块间通信
    """
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        
    async def start(self):
        """启动事件分发循环"""
        self._running = True
        while self._running:
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=1.0)
                await self._dispatch(event)
            except asyncio.TimeoutError:
                continue
                
    async def subscribe(self, event_type: str, handler: Callable[[Dict], Awaitable[None]]) -> str:
        """
        订阅事件
        
        Args:
            event_type: 事件类型
            handler: 异步处理函数
            
        Returns:
            订阅ID
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        sub_id = str(uuid.uuid4())
        self._subscribers[event_type].append((sub_id, handler))
        return sub_id
        
    async def publish(self, event_type: str, data: Dict) -> int:
        """
        发布事件
        
        Args:
            event_type: 事件类型
            data: 事件数据
            
        Returns:
            订阅者数量
        """
        await self._event_queue.put({
            'type': event_type,
            'data': data,
            'timestamp': time.time()
        })
        return len(self._subscribers.get(event_type, []))
        
    async def _dispatch(self, event: Dict):
        """分发事件到所有订阅者"""
        event_type = event['type']
        handlers = self._subscribers.get(event_type, [])
        
        # 并行调用所有处理器
        await asyncio.gather(*[
            handler(event['data']) 
            for _, handler in handlers
        ], return_exceptions=True)
```

### 32.9.2 标准事件类型

```python
class SystemEvents:
    """系统标准事件类型"""
    
    # 感知事件
    PERCEPTION_COMPLETED = "perception.completed"
    PERCEPTION_ANOMALY = "perception.anomaly"
    
    # 驱力事件
    DRIVE_CHANGED = "drive.changed"
    EMERGENCY_TRIGGERED = "drive.emergency"
    
    # 任务事件
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    
    # 预测事件
    PREDICTION_MADE = "prediction.made"
    PREDICTION_ERROR_HIGH = "prediction.error_high"
    
    # 进化事件
    MODEL_UPDATED = "model.updated"
    MODEL_REBUILT = "model.rebuilt"
    SNAPSHOT_CREATED = "snapshot.created"
    
    # 安全事件
    SAFETY_VIOLATION = "safety.violation"
    RESOURCE_LIMIT_APPROACHING = "resource.limit_approaching"
```

## 32.10 本章小结

本章详细定义了自驱永续进化Agent系统各模块的接口规范：

1. **接口设计原则**：最小暴露、异步优先、版本兼容、可观测
2. **感知模块**：传感器注册、数据采集、流式感知、历史查询
3. **驱力引擎**：驱力计算、权重调整、缺口评估
4. **任务生成**：任务创建、评估、池管理、清理
5. **决策模块**：任务选择、中断判断、探索比例调整
6. **预测模块**：多层预测、集成预测、模型重构
7. **记忆系统**：存储、检索、巩固、遗忘、快照
8. **安全守护**：任务检查、资源监控、规则执行
9. **模块通信**：事件总线、标准事件类型

这些接口规范确保了模块间的松耦合和系统的可扩展性。
