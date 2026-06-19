# 第二阶段：完整自主闭环 —— 自主目标生成模块详细技术方案

## 1. 模块概述

自主目标生成模块是整个自驱永续进化Agent系统的任务孵化层，负责根据驱力引擎输出的价值缺口信号，动态生成、更新、淘汰候选任务池。本模块实现了零人工任务输入的自主任务生成机制，是Agent从"被动响应"到"主动行为"的关键跃迁。

## 2. 设计目标

1. 自主生成：根据驱力缺口自动批量生成候选任务，无需人工输入
2. 动态刷新：任务池实时更新，动态淘汰过期任务，动态新增任务
3. 类型覆盖：覆盖安全、收益、能效三大维度的任务类型
4. 可执行性：生成的任务必须具有明确的执行逻辑和可量化的预期收益
5. 资源适配：任务资源需求与当前系统资源状态匹配

## 3. 任务定义与数据结构

### 3.1 任务核心属性

```python
@dataclass
class Task:
    # 基础标识
    task_id: str                    # 唯一标识符
    created_at: datetime            # 创建时间
    
    # 驱力关联
    drive_type: str                 # 关联驱力类型（safe/gain/eff）
    gap_value: float                # 触发该任务的缺口值
    
    # 任务描述
    task_type: str                  # 任务类型（见3.2节）
    description: str                # 任务描述
    target_dimensions: List[str]    # 目标环境维度
    
    # 执行参数
    execution_logic: Callable       # 执行逻辑
    required_resources: ResourceReq # 资源需求
    expected_duration: timedelta    # 预期执行时长
    
    # 收益评估
    expected_reward: float          # 预期收益
    success_criteria: Callable      # 成功判定条件
    
    # 状态管理
    status: str                     # 状态（pending/active/completed/failed/frozen）
    priority: float                 # 动态优先级
    attempt_count: int              # 尝试次数
    last_attempt: datetime          # 上次尝试时间
    
    # 历史记录
    execution_history: List[ExecutionRecord]
    actual_rewards: List[float]     # 历史实际收益
```

### 3.2 任务类型体系

#### 3.2.1 安全类任务

| 任务类型 | 任务描述 | 触发条件 |
|---------|---------|---------|
| risk_predict | 风险预测：基于当前趋势预测未来风险 | Gap_safe > 0.3 |
| anomaly_detect | 异常检测：深入分析异常信号来源 | 检测到异常事件 |
| state_monitor | 状态监控：增加关键指标监控频率 | 关键指标波动 |
| threat_investigate | 威胁调查：调查未知威胁来源 | 发现新威胁模式 |
| baseline_update | 基线更新：更新安全基线统计 | 基线漂移 |
| process_audit | 进程审计：审计异常进程行为 | 发现异常进程 |
| log_analyze | 日志分析：深度分析日志模式 | 日志异常增多 |
| resource_stabilize | 资源维稳：释放/优化资源 | 资源紧张 |

#### 3.2.2 收益类任务

| 任务类型 | 任务描述 | 触发条件 |
|---------|---------|---------|
| dimension_explore | 维度探索：探索未监控的环境维度 | Gap_gain > 0.3 |
| feature_test | 特征测试：测试新特征效果 | 发现潜在新特征 |
| pattern_mine | 规律挖掘：挖掘历史数据模式 | 数据积累充足 |
| model_expand | 模型扩展：建立新预测模型 | 新维度需要预测 |
| correlation_discover | 关联发现：发现变量间新关联 | 多变量数据充足 |
| prediction_optimize | 预测优化：优化现有预测模型 | 预测误差偏高 |
| knowledge_integrate | 知识整合：整合分散的认知 | 认知碎片积累 |
| strategy_evolve | 策略进化：进化决策策略 | 策略效果停滞 |

#### 3.2.3 能效类任务

| 任务类型 | 任务描述 | 触发条件 |
|---------|---------|---------|
| model_compress | 模型压缩：压缩模型参数 | Gap_eff > 0.3 |
| cache_optimize | 缓存优化：优化缓存策略 | 缓存命中率低 |
| frequency_adjust | 频率调整：调整采集/计算频率 | 资源使用率高 |
| redundancy_remove | 冗余清除：清除冗余计算 | 冗余度高 |
| algorithm_optimize | 算法优化：优化算法复杂度 | 计算耗时长 |
| data_clean | 数据清理：清理过期数据 | 存储压力大 |
| resource_reallocate | 资源重分配：优化资源分配 | 资源使用不均 |
| batch_optimize | 批处理优化：优化批处理策略 | 批处理效率低 |

## 4. 任务生成引擎

### 4.1 缺口-任务映射规则

#### 4.1.1 安全缺口映射

```python
SAFE_GAP_TASK_MAP = {
    (0.0, 0.1): [],                          # 低缺口：不生成任务
    (0.1, 0.3): ['state_monitor'],            # 中低缺口：监控任务
    (0.3, 0.5): ['risk_predict', 'anomaly_detect', 'state_monitor'],
    (0.5, 0.7): ['risk_predict', 'anomaly_detect', 'threat_investigate', 
                  'process_audit', 'log_analyze'],
    (0.7, 1.0): ['risk_predict', 'anomaly_detect', 'threat_investigate',
                  'process_audit', 'log_analyze', 'resource_stabilize', 
                  'baseline_update']
}
```

#### 4.1.2 收益缺口映射

```python
GAIN_GAP_TASK_MAP = {
    (0.0, 0.1): [],
    (0.1, 0.3): ['prediction_optimize'],
    (0.3, 0.5): ['prediction_optimize', 'feature_test', 'pattern_mine'],
    (0.5, 0.7): ['dimension_explore', 'feature_test', 'pattern_mine',
                  'model_expand', 'correlation_discover'],
    (0.7, 1.0): ['dimension_explore', 'feature_test', 'pattern_mine',
                  'model_expand', 'correlation_discover', 'knowledge_integrate',
                  'strategy_evolve']
}
```

#### 4.1.3 能效缺口映射

```python
EFF_GAP_TASK_MAP = {
    (0.0, 0.1): [],
    (0.1, 0.3): ['cache_optimize'],
    (0.3, 0.5): ['cache_optimize', 'frequency_adjust', 'data_clean'],
    (0.5, 0.7): ['model_compress', 'cache_optimize', 'frequency_adjust',
                  'redundancy_remove', 'data_clean'],
    (0.7, 1.0): ['model_compress', 'cache_optimize', 'frequency_adjust',
                  'redundancy_remove', 'algorithm_optimize', 'data_clean',
                  'resource_reallocate', 'batch_optimize']
}
```

### 4.2 任务实例化

#### 4.2.1 任务模板库

每个任务类型对应一个任务模板，定义任务的默认参数：

```python
TASK_TEMPLATES = {
    'risk_predict': {
        'description': '预测未来{horizon}分钟内的系统风险',
        'required_resources': {'cpu': 0.05, 'memory': 50, 'time': 30},
        'expected_duration': timedelta(seconds=30),
        'success_criteria': '生成风险报告且预测置信度>0.7'
    },
    'anomaly_detect': {
        'description': '检测并分析{target}中的异常模式',
        'required_resources': {'cpu': 0.1, 'memory': 100, 'time': 60},
        'expected_duration': timedelta(seconds=60),
        'success_criteria': '识别异常根因且误报率<0.1'
    },
    # ... 其他任务模板
}
```

#### 4.2.2 动态参数填充

根据当前环境状态动态填充任务参数：

```python
def instantiate_task(template, state_vector, gap_value):
    task = Task()
    task.task_type = template['type']
    task.description = template['description'].format(
        horizon=calculate_horizon(gap_value),
        target=identify_target_dimension(state_vector, gap_value)
    )
    task.required_resources = scale_resources(
        template['required_resources'], 
        state_vector.system_load
    )
    task.expected_reward = estimate_reward(task, state_vector)
    return task
```

### 4.3 任务去重与合并

#### 4.3.1 相似任务检测

```python
def is_similar(task1, task2):
    """判断两个任务是否相似"""
    if task1.task_type != task2.task_type:
        return False
    
    # 目标维度重叠度
    overlap = len(set(task1.target_dimensions) & set(task2.target_dimensions))
    union = len(set(task1.target_dimensions) | set(task2.target_dimensions))
    dimension_similarity = overlap / union
    
    # 描述相似度（使用简单的关键词匹配）
    description_similarity = keyword_similarity(
        task1.description, task2.description
    )
    
    return dimension_similarity > 0.8 and description_similarity > 0.7
```

#### 4.3.2 任务合并策略

```python
def merge_tasks(tasks):
    """合并相似任务"""
    merged = []
    for task in tasks:
        found_similar = False
        for existing in merged:
            if is_similar(task, existing):
                # 合并：保留缺口值更大的任务
                if task.gap_value > existing.gap_value:
                    existing.gap_value = task.gap_value
                    existing.priority = max(existing.priority, task.priority)
                found_similar = True
                break
        if not found_similar:
            merged.append(task)
    return merged
```

## 5. 任务池管理

### 5.1 任务池数据结构

```python
class TaskPool:
    def __init__(self, max_size=1000):
        self.tasks: Dict[str, Task] = {}           # 活跃任务
        self.frozen_tasks: Dict[str, Task] = {}     # 冻结任务
        self.completed_tasks: deque = deque(maxlen=10000)  # 历史任务
        self.max_size = max_size
```

### 5.2 任务生命周期管理

#### 5.2.1 任务状态转换

```
[pending] --选中执行--> [active] --执行完成--> [completed]
    |                      |
    |--条件不满足--> [frozen]  |--执行失败--> [pending] (重试)
    |                      |--连续失败--> [frozen]
    |--过期淘汰--> [removed]
```

#### 5.2.2 任务过期机制

```python
def is_expired(task, current_time):
    """判断任务是否过期"""
    # 基于创建时间的硬过期
    if current_time - task.created_at > TASK_MAX_AGE:
        return True
    
    # 基于环境变化的软过期
    if task.drive_type == 'safe':
        # 安全任务：当相关威胁消除后过期
        return task.gap_value < 0.1
    elif task.drive_type == 'gain':
        # 收益任务：当相关缺口被其他任务填补后过期
        return task.gap_value < 0.05
    elif task.drive_type == 'eff':
        # 能效任务：当资源压力缓解后过期
        return task.gap_value < 0.1
    
    return False
```

### 5.3 任务淘汰策略

#### 5.3.1 容量限制淘汰

当任务池超过最大容量时，按以下优先级淘汰：

1. 过期任务（最先淘汰）
2. 低优先级任务
3. 长期未执行的任务
4. 历史成功率低的任务类型

#### 5.3.2 动态淘汰算法

```python
def calculate_retention_score(task):
    """计算任务保留分数（越高越应该保留）"""
    age_factor = exp(-0.01 × task_age_hours)           # 年龄衰减
    priority_factor = task.priority                      # 优先级
    gap_factor = task.gap_value                          # 缺口值
    success_factor = mean(task.actual_rewards) if task.actual_rewards else 0.5
    
    return (priority_factor × 0.4 + 
            gap_factor × 0.3 + 
            success_factor × 0.2 + 
            age_factor × 0.1)

def evict_tasks(task_pool, target_size):
    """淘汰任务至目标大小"""
    if len(task_pool.tasks) <= target_size:
        return
    
    # 按保留分数排序，淘汰低分任务
    sorted_tasks = sorted(
        task_pool.tasks.values(),
        key=calculate_retention_score,
        reverse=True
    )
    
    keep_ids = {t.task_id for t in sorted_tasks[:target_size]}
    for task_id in list(task_pool.tasks.keys()):
        if task_id not in keep_ids:
            task_pool.tasks.pop(task_id)
```

## 6. 任务收益预估

### 6.1 历史收益统计

维护各任务类型的历史收益统计：

```python
class TaskTypeStats:
    def __init__(self):
        self.total_executions = 0
        self.success_count = 0
        self.total_reward = 0.0
        self.reward_history = deque(maxlen=100)
        self.avg_execution_time = 0.0
```

### 6.2 收益预估模型

```python
def estimate_reward(task, state_vector):
    """预估任务执行后的预期收益"""
    stats = get_task_type_stats(task.task_type)
    
    # 基于历史平均收益
    historical_reward = stats.total_reward / max(stats.total_executions, 1)
    
    # 基于缺口值的理论最大收益
    theoretical_max = task.gap_value * REWARD_MAX_PER_GAP
    
    # 基于环境状态的调整因子
    environment_factor = calculate_environment_factor(task, state_vector)
    
    # 综合预估
    expected_reward = (historical_reward × 0.4 + 
                      theoretical_max × 0.4 + 
                      environment_factor × 0.2)
    
    return clip(expected_reward, 0, 1)
```

### 6.3 环境适配因子

```python
def calculate_environment_factor(task, state_vector):
    """计算环境适配因子"""
    factor = 1.0
    
    # 资源充足度
    resource_availability = 1.0 - state_vector.system_resource_pressure
    factor *= (0.5 + 0.5 × resource_availability)
    
    # 任务-环境匹配度
    if task.drive_type == 'safe':
        factor *= (1.0 + state_vector.threat_level)
    elif task.drive_type == 'gain':
        factor *= (1.0 + state_vector.prediction_error)
    elif task.drive_type == 'eff':
        factor *= (1.0 + state_vector.resource_waste_ratio)
    
    return factor
```

## 7. 接口定义

### 7.1 对外接口

```python
class TaskGenerator:
    def __init__(self, config: TaskGenConfig):
        """初始化任务生成器"""
        pass
    
    def generate_tasks(self, drive_output: DriveOutput, 
                       state_vector: StateVector) -> List[Task]:
        """
        根据驱力输出生成候选任务
        
        Args:
            drive_output: 驱力引擎输出（含Gap值）
            state_vector: 当前环境状态
            
        Returns:
            List[Task]: 新生成的候选任务列表
        """
        pass
    
    def update_task_pool(self, new_tasks: List[Task]):
        """更新任务池（去重、合并、淘汰）"""
        pass
    
    def get_task_pool(self) -> TaskPool:
        """获取当前任务池"""
        pass
    
    def record_execution(self, task_id: str, result: ExecutionResult):
        """记录任务执行结果"""
        pass
    
    def get_task_stats(self, task_type: str) -> TaskTypeStats:
        """获取任务类型统计"""
        pass
```

### 7.2 配置参数

```python
@dataclass
class TaskGenConfig:
    # 任务池配置
    max_pool_size: int = 1000
    max_history_size: int = 10000
    task_max_age_hours: float = 24.0
    
    # 生成配置
    tasks_per_gap_level: int = 3           # 每个缺口级别生成的任务数
    max_tasks_per_cycle: int = 20          # 每轮最大生成任务数
    
    # 去重配置
    similarity_threshold: float = 0.75
    dimension_overlap_threshold: float = 0.8
    
    # 淘汰配置
    eviction_batch_size: int = 50
    retention_score_weights: Dict[str, float] = None
    
    # 收益预估配置
    reward_history_window: int = 100
    theoretical_reward_max: float = 1.0
    
    # 冻结配置
    freeze_after_failures: int = 5
    freeze_duration_hours: float = 1.0
```

## 8. 测试与验证

### 8.1 单元测试

1. 任务生成逻辑测试
2. 任务去重算法测试
3. 任务淘汰策略测试
4. 收益预估准确性测试

### 8.2 集成测试

1. 驱力输出到任务生成的端到端测试
2. 任务池容量压力测试
3. 长时间运行的任务池稳定性测试

### 8.3 效果验证

1. 任务覆盖率：各驱力类型任务的生成比例
2. 任务质量：生成任务的实际执行成功率
3. 任务时效性：从缺口产生到任务生成的延迟

---

自主目标生成模块作为Agent系统的"任务孵化器"，其设计质量直接决定了Agent能否将内生动机转化为可执行的行为。通过缺口-任务映射、动态任务池管理和智能去重合并机制，确保Agent始终拥有高质量、多样化的候选任务池。
