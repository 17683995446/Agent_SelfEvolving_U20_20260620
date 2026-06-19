# 第二阶段：完整自主闭环 —— 记忆与持久化模块详细技术方案

## 1. 模块概述

记忆与持久化模块是整个自驱永续进化Agent系统的记忆层，负责管理Agent的在线短期记忆和离线长期记忆。本模块实现了环境状态、预测误差、驱力输出、任务执行结果等关键数据的持久化存储，为系统的离线复盘、模型进化、历史分析提供数据基础。第一阶段重点实现基础的数据持久化能力，为第三阶段的离线复盘模块做准备。

## 2. 设计目标

1. 分层存储：在线短期记忆（内存）+ 离线长期记忆（本地存储）
2. 高效写入：高频数据的批量写入，降低I/O开销
3. 数据完整性：关键数据不丢失，支持断点恢复
4. 存储可控：本地存储自动清理，仅保留高价值样本
5. 快速查询：支持按时间、类型、维度等多条件查询

## 3. 记忆数据分类

### 3.1 原始感知数据

```python
@dataclass
class PerceptionRecord:
    timestamp: datetime
    state_vector: StateVector          # 完整环境状态向量
    raw_data: Dict[str, Any]           # 原始采集数据（用于调试）
    data_quality: float                # 数据质量评分
```

### 3.2 驱力计算数据

```python
@dataclass
class DriveRecord:
    timestamp: datetime
    reward_safe: float
    reward_gain: float
    reward_eff: float
    reward_total: float
    gap_safe: float
    gap_gain: float
    gap_eff: float
    weights: Dict[str, float]          # 当前权重配置
    urgency: float
```

### 3.3 预测数据

```python
@dataclass
class PredictionRecord:
    timestamp: datetime
    model_id: str
    model_level: str                   # low/mid/high
    prediction_values: np.ndarray
    confidence_interval: Tuple[float, float]
    actual_values: np.ndarray          # 实际值（后续回填）
    error_metrics: Dict[str, float]    # 误差指标
```

### 3.4 任务执行数据

```python
@dataclass
class TaskExecutionRecord:
    timestamp: datetime
    task_id: str
    task_type: str
    drive_type: str
    execution_duration: timedelta
    success: bool
    actual_reward: float
    expected_reward: float
    resource_consumed: ResourceUsage
    state_before: StateVector
    state_after: StateVector
```

### 3.5 决策数据

```python
@dataclass
class DecisionRecord:
    timestamp: datetime
    selected_task_id: str
    selection_mode: str                # exploit/explore
    exploration_rate: float
    candidate_count: int
    top_scores: List[Tuple[str, float]]
    interrupt: bool
    interrupt_reason: str
```

## 4. 在线短期记忆

### 4.1 内存缓存架构

```python
class ShortTermMemory:
    def __init__(self, capacity: int = 10000):
        self.perception_buffer: deque = deque(maxlen=capacity)
        self.drive_buffer: deque = deque(maxlen=capacity)
        self.prediction_buffer: deque = deque(maxlen=capacity)
        self.task_buffer: deque = deque(maxlen=capacity)
        self.decision_buffer: deque = deque(maxlen=capacity)
```

### 4.2 缓存策略

#### 4.2.1 写入策略

所有新数据首先写入内存缓存：

```python
def record_perception(self, state_vector: StateVector):
    record = PerceptionRecord(
        timestamp=datetime.now(),
        state_vector=state_vector,
        raw_data=self.get_raw_data(),
        data_quality=self.assess_data_quality(state_vector)
    )
    self.perception_buffer.append(record)
```

#### 4.2.2 读取策略

优先从内存缓存读取近期数据：

```python
def get_recent_perceptions(self, duration: timedelta) -> List[PerceptionRecord]:
    cutoff = datetime.now() - duration
    return [r for r in self.perception_buffer if r.timestamp > cutoff]
```

### 4.3 缓存同步

内存缓存定期同步到长期存储：

```python
async def sync_to_long_term(self):
    """将内存缓存同步到长期存储"""
    # 批量写入感知数据
    if len(self.perception_buffer) > SYNC_BATCH_SIZE:
        batch = list(self.perception_buffer)[-SYNC_BATCH_SIZE:]
        await self.long_term_store.write_perceptions(batch)
    
    # 批量写入驱力数据
    if len(self.drive_buffer) > SYNC_BATCH_SIZE:
        batch = list(self.drive_buffer)[-SYNC_BATCH_SIZE:]
        await self.long_term_store.write_drives(batch)
    
    # 其他数据类型类似处理
```

## 5. 离线长期记忆

### 5.1 存储架构

采用SQLite + JSON文件的混合存储方案：

```
storage/
├── main.db              # SQLite主数据库
│   ├── perceptions      # 感知数据表
│   ├── drives           # 驱力数据表
│   ├── predictions      # 预测数据表
│   ├── tasks            # 任务执行数据表
│   ├── decisions        # 决策数据表
│   └── metadata         # 元数据表
│
├── snapshots/           # 模型快照目录
│   ├── model_YYYYMMDD_HHMMSS.pkl
│   └── ...
│
├── logs/                # 详细日志
│   ├── agent_YYYYMMDD.log
│   └── ...
│
└── config/              # 配置备份
    └── config_YYYYMMDD.json
```

### 5.2 SQLite数据库设计

#### 5.2.1 感知数据表

```sql
CREATE TABLE perceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    state_vector BLOB NOT NULL,        -- 序列化的状态向量
    data_quality REAL,
    created_at REAL DEFAULT (datetime('now'))
);

CREATE INDEX idx_perceptions_time ON perceptions(timestamp);
```

#### 5.2.2 驱力数据表

```sql
CREATE TABLE drives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    reward_safe REAL,
    reward_gain REAL,
    reward_eff REAL,
    reward_total REAL,
    gap_safe REAL,
    gap_gain REAL,
    gap_eff REAL,
    weight_safe REAL,
    weight_gain REAL,
    weight_eff REAL,
    urgency REAL
);

CREATE INDEX idx_drives_time ON drives(timestamp);
```

#### 5.2.3 预测数据表

```sql
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    model_id TEXT,
    model_level TEXT,
    prediction_values TEXT,            -- JSON序列化
    confidence_lower REAL,
    confidence_upper REAL,
    actual_values TEXT,                -- JSON序列化（后续回填）
    mae REAL,
    mse REAL,
    direction_accuracy REAL
);

CREATE INDEX idx_predictions_time ON predictions(timestamp);
CREATE INDEX idx_predictions_model ON predictions(model_id);
```

#### 5.2.4 任务执行数据表

```sql
CREATE TABLE task_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    task_id TEXT,
    task_type TEXT,
    drive_type TEXT,
    execution_duration_ms INTEGER,
    success INTEGER,
    actual_reward REAL,
    expected_reward REAL,
    cpu_consumed REAL,
    memory_consumed REAL
);

CREATE INDEX idx_tasks_time ON task_executions(timestamp);
CREATE INDEX idx_tasks_type ON task_executions(task_type);
```

### 5.3 数据压缩

#### 5.3.1 状态向量压缩

使用numpy的save/load进行二进制序列化：

```python
def serialize_state_vector(state_vector: StateVector) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, state_vector.values, allow_pickle=False)
    return buffer.getvalue()

def deserialize_state_vector(data: bytes) -> StateVector:
    buffer = io.BytesIO(data)
    values = np.load(buffer)
    return StateVector(values=values)
```

#### 5.3.2 数据采样

对于高频数据，采用分层采样减少存储量：

```python
def stratified_sample(records: List, target_size: int) -> List:
    """分层采样：保留高价值样本"""
    # 按数据质量分层
    high_quality = [r for r in records if r.data_quality > 0.8]
    medium_quality = [r for r in records if 0.5 <= r.data_quality <= 0.8]
    low_quality = [r for r in records if r.data_quality < 0.5]
    
    # 按比例采样
    n_high = int(target_size * 0.5)
    n_medium = int(target_size * 0.3)
    n_low = target_size - n_high - n_medium
    
    sampled = (
        random.sample(high_quality, min(n_high, len(high_quality))) +
        random.sample(medium_quality, min(n_medium, len(medium_quality))) +
        random.sample(low_quality, min(n_low, len(low_quality)))
    )
    
    return sampled
```

## 6. 存储管理

### 6.1 容量控制

#### 6.1.1 存储上限

```python
MAX_STORAGE_SIZE_GB = 10  # 最大存储容量
CLEANUP_THRESHOLD = 0.8   # 达到80%时触发清理
```

#### 6.1.2 自动清理策略

```python
def auto_cleanup(self):
    """自动清理过期和低价值数据"""
    current_size = self.get_storage_size()
    max_size = MAX_STORAGE_SIZE_GB * 1024 * 1024 * 1024
    
    if current_size < max_size * CLEANUP_THRESHOLD:
        return
    
    # 计算需要释放的空间
    target_size = max_size * 0.5
    need_to_free = current_size - target_size
    
    # 按优先级清理
    freed = 0
    
    # 1. 清理超过30天的详细日志
    freed += self.clean_old_logs(days=30)
    if freed >= need_to_free:
        return
    
    # 2. 清理低质量感知数据（保留Top 30%）
    freed += self.clean_low_quality_perceptions(keep_ratio=0.3)
    if freed >= need_to_free:
        return
    
    # 3. 压缩历史数据
    freed += self.compress_old_data(days=7)
```

### 6.2 数据保留策略

#### 6.2.1 分级保留

| 数据类型 | 保留时长 | 保留比例 | 备注 |
|---------|---------|---------|------|
| 感知数据 | 7天 | 30%高质量 | 原始数据 |
| 驱力数据 | 30天 | 100% | 关键决策依据 |
| 预测数据 | 14天 | 50% | 含误差反馈 |
| 任务执行 | 30天 | 100% | 效果评估 |
| 决策记录 | 30天 | 100% | 策略进化 |
| 模型快照 | 保留最近10个 | - | 支持回滚 |

#### 6.2.2 高价值样本识别

```python
def calculate_sample_value(record) -> float:
    """计算样本价值"""
    value = 0.0
    
    # 异常事件价值高
    if hasattr(record, 'is_anomaly') and record.is_anomaly:
        value += 0.3
    
    # 高误差样本价值高（用于训练）
    if hasattr(record, 'prediction_error'):
        value += record.prediction_error * 0.3
    
    # 探索任务的结果价值高
    if hasattr(record, 'is_exploration') and record.is_exploration:
        value += 0.2
    
    # 近期样本价值略高
    if hasattr(record, 'timestamp'):
        age_hours = (datetime.now() - record.timestamp).total_seconds() / 3600
        value += max(0, 0.2 - age_hours * 0.001)
    
    return min(value, 1.0)
```

## 7. 数据查询接口

### 7.1 时间范围查询

```python
def query_perceptions(self, start: datetime, end: datetime, 
                     dimensions: List[str] = None) -> List[PerceptionRecord]:
    """查询指定时间范围的感知数据"""
    sql = "SELECT * FROM perceptions WHERE timestamp BETWEEN ? AND ?"
    params = [start.timestamp(), end.timestamp()]
    
    if dimensions:
        # 过滤特定维度
        pass
    
    return self.execute_query(sql, params)
```

### 7.2 聚合统计查询

```python
def get_drive_statistics(self, duration: timedelta) -> DriveStatistics:
    """获取指定时间范围的驱力统计"""
    sql = """
    SELECT 
        AVG(reward_total) as avg_reward,
        AVG(gap_safe) as avg_gap_safe,
        AVG(gap_gain) as avg_gap_gain,
        AVG(gap_eff) as avg_gap_eff,
        MAX(urgency) as max_urgency
    FROM drives 
    WHERE timestamp > ?
    """
    
    cutoff = (datetime.now() - duration).timestamp()
    result = self.execute_query(sql, [cutoff])
    return DriveStatistics(**result[0])
```

### 7.3 模型训练数据查询

```python
def get_training_data(self, model_type: str, 
                     sample_size: int = 1000) -> TrainingDataset:
    """获取模型训练数据"""
    # 查询高价值样本
    sql = """
    SELECT p.state_vector, pr.prediction_values, pr.actual_values
    FROM perceptions p
    JOIN predictions pr ON p.timestamp = pr.timestamp
    WHERE pr.actual_values IS NOT NULL
    ORDER BY pr.mse DESC
    LIMIT ?
    """
    
    return self.execute_query(sql, [sample_size])
```

## 8. 模型快照管理

### 8.1 快照创建

```python
def create_snapshot(self, tag: str = None) -> str:
    """创建模型快照"""
    snapshot_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if tag:
        snapshot_id += f"_{tag}"
    
    snapshot_path = self.snapshots_dir / f"{snapshot_id}.pkl"
    
    snapshot_data = {
        'timestamp': datetime.now(),
        'predictor_state': self.predictor.get_state(),
        'drive_engine_state': self.drive_engine.get_state(),
        'decision_weights': self.decision_engine.get_weights(),
        'baseline_stats': self.drive_engine.get_baseline(),
        'performance_metrics': self.get_performance_metrics()
    }
    
    with open(snapshot_path, 'wb') as f:
        pickle.dump(snapshot_data, f)
    
    return snapshot_id
```

### 8.2 快照回滚

```python
def rollback_to_snapshot(self, snapshot_id: str) -> bool:
    """回滚到指定快照"""
    snapshot_path = self.snapshots_dir / f"{snapshot_id}.pkl"
    
    if not snapshot_path.exists():
        return False
    
    with open(snapshot_path, 'rb') as f:
        snapshot_data = pickle.load(f)
    
    # 恢复各模块状态
    self.predictor.set_state(snapshot_data['predictor_state'])
    self.drive_engine.set_state(snapshot_data['drive_engine_state'])
    self.decision_engine.set_weights(snapshot_data['decision_weights'])
    
    return True
```

### 8.3 快照清理

```python
def cleanup_snapshots(self, keep_count: int = 10):
    """清理旧快照，仅保留最近N个"""
    snapshots = sorted(
        self.snapshots_dir.glob("*.pkl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    
    for old_snapshot in snapshots[keep_count:]:
        old_snapshot.unlink()
```

## 9. 接口定义

### 9.1 对外接口

```python
class MemorySystem:
    def __init__(self, config: MemoryConfig):
        """初始化记忆系统"""
        pass
    
    # 写入接口
    def record_perception(self, state_vector: StateVector):
        """记录感知数据"""
        pass
    
    def record_drive(self, drive_output: DriveOutput):
        """记录驱力数据"""
        pass
    
    def record_prediction(self, prediction: PredictionRecord):
        """记录预测数据"""
        pass
    
    def record_task_execution(self, execution: TaskExecutionRecord):
        """记录任务执行"""
        pass
    
    def record_decision(self, decision: DecisionRecord):
        """记录决策"""
        pass
    
    # 查询接口
    def get_recent_perceptions(self, duration: timedelta) -> List[PerceptionRecord]:
        """获取近期感知数据"""
        pass
    
    def get_drive_history(self, duration: timedelta) -> List[DriveRecord]:
        """获取驱力历史"""
        pass
    
    def get_task_stats(self, task_type: str, 
                      duration: timedelta) -> TaskStatistics:
        """获取任务统计"""
        pass
    
    # 快照接口
    def create_snapshot(self, tag: str = None) -> str:
        """创建快照"""
        pass
    
    def rollback_to_snapshot(self, snapshot_id: str) -> bool:
        """回滚到快照"""
        pass
    
    # 管理接口
    def auto_cleanup(self):
        """自动清理"""
        pass
    
    def get_storage_stats(self) -> StorageStatistics:
        """获取存储统计"""
        pass
```

### 9.2 配置参数

```python
@dataclass
class MemoryConfig:
    # 存储路径
    storage_dir: str = "./agent_storage"
    
    # 缓存配置
    short_term_capacity: int = 10000
    sync_interval_seconds: int = 60
    sync_batch_size: int = 1000
    
    # 存储限制
    max_storage_size_gb: float = 10.0
    cleanup_threshold: float = 0.8
    
    # 保留策略
    perception_retention_days: int = 7
    perception_keep_ratio: float = 0.3
    drive_retention_days: int = 30
    prediction_retention_days: int = 14
    task_retention_days: int = 30
    decision_retention_days: int = 30
    
    # 快照配置
    max_snapshots: int = 10
    auto_snapshot_interval_hours: int = 24
    
    # 数据库配置
    db_path: str = "storage/main.db"
    db_wal_mode: bool = True
```

## 10. 测试与验证

### 10.1 单元测试

1. 数据序列化/反序列化测试
2. 数据库读写性能测试
3. 缓存同步正确性测试
4. 快照创建/回滚测试

### 10.2 集成测试

1. 长时间运行的存储稳定性测试
2. 存储容量达到上限时的行为测试
3. 数据清理后的查询正确性测试
4. 快照回滚后的系统一致性测试

### 10.3 性能测试

1. 写入吞吐量测试
2. 查询响应时间测试
3. 存储空间增长速率测试

---

记忆与持久化模块作为Agent系统的"海马体"，其设计质量直接决定了Agent能否积累认知经验、支持离线学习和实现状态恢复。通过分层存储架构和智能的存储管理策略，确保Agent在有限的单机资源下实现最大化的记忆价值。
