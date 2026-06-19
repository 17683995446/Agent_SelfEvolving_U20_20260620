# 第二阶段：完整自主闭环 —— 自主决策模块详细技术方案

## 1. 模块概述

自主决策模块是整个自驱永续进化Agent系统的决策中枢，负责基于驱力缺口、任务池状态和当前环境，自主决定"现在做什么"。本模块实现了完整的四阶段自主决策链路：状态感知 → 缺口评估 → 任务池生成 → 打分择优决策，并引入了探索-利用平衡机制和动态中断机制，确保Agent既能稳定执行高价值任务，又能主动探索未知领域以实现持续进化。

## 2. 设计目标

1. 全局最优：每一时刻的选择都是当前环境下的全局最优决策
2. 探索-利用平衡：70%利用现有知识，30%探索未知领域
3. 动态响应：高优先级缺口出现时能够立即中断当前任务
4. 可解释性：每个决策都有明确的评分依据和选择理由
5. 防僵化：强制探索机制避免模型陷入局部最优

## 3. 决策流程架构

### 3.1 四阶段决策链路

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  状态感知   │ → │  缺口评估   │ → │  任务生成   │ → │  打分择优   │
│  (输入)     │    │  (分析)     │    │  (候选)     │    │  (输出)     │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       ↑                                                    │
       └──────────────── 执行反馈 ←─────────────────────────┘
```

### 3.2 决策循环时序

```
T0: 接收环境状态向量 S(t)
T1: 计算驱力输出 D(t) = DriveEngine.compute(S(t))
T2: 生成候选任务池 T(t) = TaskGenerator.generate(D(t), S(t))
T3: 对候选任务进行评分 Score(t) = ScoreTask(T_i, S(t), D(t))
T4: 选择最优任务 T* = SelectTask(Score(t), exploration_rate)
T5: 执行任务 T* → 产生行为 A(t)
T6: 等待下一个周期 (默认1秒)
```

## 4. 任务评分体系

### 4.1 综合评分公式

每个候选任务的综合得分由以下因素加权计算：

```
Score_task = α × Expected_Reward + β × Urgency + γ × Resource_Fit + δ × Strategic_Value
```

其中：
- α + β + γ + δ = 1.0（默认 α=0.4, β=0.3, γ=0.2, δ=0.1）
- Expected_Reward：预期收益 [0, 1]
- Urgency：紧急度 [0, 1]
- Resource_Fit：资源适配度 [0, 1]
- Strategic_Value：战略价值 [0, 1]

### 4.2 预期收益评分

#### 4.2.1 直接收益

```
Direct_Reward = task.expected_reward × task.gap_value
```

任务预期收益与缺口值的乘积，表示填补该缺口能带来的直接价值。

#### 4.2.2 间接收益

```
Indirect_Reward = Σ(Related_Gap_j × Coupling_Strength_j)
```

考虑任务对其他相关缺口的间接影响。例如，执行能效优化任务可能间接提升安全稳定性。

#### 4.2.3 历史成功率调整

```
History_Adjustment = 2 / (1 + exp(-5 × (success_rate - 0.5)))
```

使用sigmoid函数将历史成功率映射到调整因子，成功率高的任务获得正向调整。

### 4.3 紧急度评分

#### 4.3.1 时间衰减紧急度

```
Time_Urgency = 1 - exp(-λ × (current_time - task.created_at).seconds)
```

任务创建后随时间推移紧急度增加。

#### 4.3.2 缺口紧急度

```
Gap_Urgency = task.gap_value × Emergency_Factor[task.drive_type]
```

安全缺口的紧急系数最高，收益次之，能效最低。

#### 4.3.3 综合紧急度

```
Urgency = 0.6 × Gap_Urgency + 0.4 × Time_Urgency
```

### 4.4 资源适配度评分

#### 4.4.1 资源充足度

```
Resource_Availability = min(
    (cpu_limit - current_cpu) / task.required_cpu,
    (mem_limit - current_mem) / task.required_mem,
    1.0
)
```

#### 4.4.2 资源竞争度

```
Resource_Competition = 1 - (active_tasks_using_similar_resources / max_concurrent_tasks)
```

#### 4.4.3 综合资源适配度

```
Resource_Fit = 0.7 × Resource_Availability + 0.3 × Resource_Competition
```

### 4.5 战略价值评分

#### 4.5.1 探索价值

```
Exploration_Value = 1 - task_type_familiarity
```

对该任务类型的熟悉度越低，探索价值越高。

#### 4.5.2 长期价值

```
Long_Term_Value = task.cognitive_expansion_potential × time_horizon_factor
```

能够拓展认知边界、建立新模型的任务具有更高的长期价值。

#### 4.5.3 综合战略价值

```
Strategic_Value = 0.6 × Exploration_Value + 0.4 × Long_Term_Value
```

## 5. 探索-利用平衡机制

### 5.1 核心原理

Agent采用ε-贪心策略的改进版本，实现70%利用 / 30%探索的固定比例：

```
if random() < exploration_rate:
    # 探索模式：选择非最优任务
    selected_task = explore_task_selection(candidate_tasks)
else:
    # 利用模式：选择评分最高的任务
    selected_task = argmax(Score_task_i)
```

### 5.2 探索模式详细设计

#### 5.2.1 探索任务选择策略

探索模式下不随机选择，而是采用以下策略：

1. **低分探索**：选择评分最低但非零的任务
   ```
   explore_candidate = argmin(Score_task_i | Score_task_i > 0)
   ```

2. **陌生类型探索**：选择历史执行次数最少的任务类型
   ```
   explore_candidate = argmin(execution_count[task_type_i])
   ```

3. **维度跳跃探索**：选择与当前关注维度不同的任务
   ```
   explore_candidate = task with max(dimension_distance from current_focus)
   ```

4. **随机混合**：以1/3概率分别采用上述三种策略

#### 5.2.2 探索保护机制

防止探索导致系统风险：

```python
def is_safe_to_explore(task, state_vector):
    """判断是否可以安全探索该任务"""
    # 安全缺口高时禁止探索非安全任务
    if state_vector.gap_safe > 0.5 and task.drive_type != 'safe':
        return False
    
    # 资源紧张时禁止探索高资源任务
    if state_vector.resource_pressure > 0.8 and task.required_resources > threshold:
        return False
    
    # 探索任务连续失败5次后冻结
    if task.explore_failure_count >= 5:
        return False
    
    return True
```

### 5.3 探索率动态调整

#### 5.3.1 基础探索率

基础探索率固定为30%：

```
base_exploration_rate = 0.3
```

#### 5.3.2 稳态上浮机制

当系统处于稳态（误差极低）时，自动上浮探索权重：

```
if prediction_error < error_threshold and stability_duration > stability_window:
    exploration_rate = min(base_exploration_rate × 1.5, 0.5)
```

#### 5.3.3 紧急下压机制

当安全缺口高时，下压探索率：

```
if gap_safe > 0.7:
    exploration_rate = base_exploration_rate × 0.3
```

## 6. 动态中断机制

### 6.1 中断触发条件

#### 6.1.1 高优先级缺口出现

```python
def should_interrupt(current_task, new_drive_output):
    """判断是否应该中断当前任务"""
    # 当前任务为低优先级且出现高安全缺口
    if current_task.drive_type != 'safe' and new_drive_output.gap_safe > 0.7:
        return True
    
    # 当前任务资源消耗高且出现高能效缺口
    if current_task.resource_cost > threshold and new_drive_output.gap_eff > 0.7:
        return True
    
    # 新任务的紧急度显著高于当前任务
    current_urgency = current_task.urgency
    max_new_urgency = max(task.urgency for task in new_tasks)
    if max_new_urgency > current_urgency × 2:
        return True
    
    return False
```

#### 6.1.2 当前任务失效

```python
def is_task_still_valid(task, current_state):
    """判断当前任务是否仍然有效"""
    # 任务关联的缺口已消除
    if task.gap_value < 0.05:
        return False
    
    # 任务依赖的环境条件已改变
    if not task.precondition(current_state):
        return False
    
    # 任务执行超时
    if task.execution_time > task.max_duration:
        return False
    
    return True
```

### 6.2 中断执行流程

```
1. 保存当前任务执行状态（如支持断点续行）
2. 记录中断原因和中断时刻
3. 将当前任务重新放入任务池（状态更新为pending）
4. 选择新的最优任务
5. 执行新任务
```

### 6.3 中断保护

防止频繁中断导致的抖动：

```python
MIN_TASK_DURATION = 5  # 最小任务执行时间（秒）
MAX_INTERRUPTS_PER_MINUTE = 3  # 每分钟最大中断次数

def can_interrupt_now(current_task_start_time, interrupt_count_recent):
    if time_since_start < MIN_TASK_DURATION:
        return False
    if interrupt_count_recent >= MAX_INTERRUPTS_PER_MINUTE:
        return False
    return True
```

## 7. 决策记录与学习

### 7.1 决策日志

记录每次决策的完整信息：

```python
@dataclass
class DecisionRecord:
    timestamp: datetime
    state_vector: StateVector
    drive_output: DriveOutput
    candidate_tasks: List[Task]
    task_scores: Dict[str, float]
    selected_task: Task
    selection_mode: str  # 'exploit' or 'explore'
    exploration_rate: float
    interrupt: bool
    interrupt_reason: str
```

### 7.2 决策效果评估

```python
def evaluate_decision(decision_record, outcome):
    """评估决策效果"""
    # 预期收益 vs 实际收益
    reward_accuracy = outcome.actual_reward / decision_record.selected_task.expected_reward
    
    # 决策时机评估
    timing_score = evaluate_timing(decision_record, outcome)
    
    # 综合决策质量
    decision_quality = 0.6 × reward_accuracy + 0.4 × timing_score
    
    return decision_quality
```

### 7.3 决策策略进化

基于历史决策效果，微调评分权重：

```python
def evolve_decision_weights(history):
    """基于历史数据进化决策权重"""
    # 分析不同权重配置下的决策效果
    weight_performance = analyze_weight_performance(history)
    
    # 向效果更好的权重方向微调
    best_weights = argmax(weight_performance)
    current_weights = get_current_weights()
    
    new_weights = current_weights + learning_rate × (best_weights - current_weights)
    return clip_weights(new_weights)
```

## 8. 接口定义

### 8.1 对外接口

```python
class DecisionEngine:
    def __init__(self, config: DecisionConfig):
        """初始化决策引擎"""
        pass
    
    def decide(self, state_vector: StateVector, 
               drive_output: DriveOutput,
               task_pool: TaskPool,
               current_task: Task = None) -> Decision:
        """
        执行决策
        
        Args:
            state_vector: 当前环境状态
            drive_output: 驱力引擎输出
            task_pool: 当前任务池
            current_task: 当前正在执行的任务（如有）
            
        Returns:
            Decision: 包含选择的任务、决策模式、评分详情
        """
        pass
    
    def score_task(self, task: Task, state_vector: StateVector, 
                   drive_output: DriveOutput) -> float:
        """对单个任务进行评分"""
        pass
    
    def should_interrupt(self, current_task: Task, 
                        new_drive_output: DriveOutput) -> bool:
        """判断是否应该中断当前任务"""
        pass
    
    def get_decision_history(self, duration: timedelta) -> List[DecisionRecord]:
        """获取历史决策记录"""
        pass
    
    def get_exploration_stats(self) -> ExplorationStats:
        """获取探索统计信息"""
        pass
```

### 8.2 配置参数

```python
@dataclass
class DecisionConfig:
    # 评分权重
    reward_weight: float = 0.4
    urgency_weight: float = 0.3
    resource_fit_weight: float = 0.2
    strategic_weight: float = 0.1
    
    # 探索-利用配置
    base_exploration_rate: float = 0.3
    max_exploration_rate: float = 0.5
    min_exploration_rate: float = 0.1
    stability_error_threshold: float = 0.05
    stability_window: int = 100
    
    # 中断配置
    min_task_duration: int = 5
    max_interrupts_per_minute: int = 3
    high_gap_interrupt_threshold: float = 0.7
    urgency_ratio_interrupt: float = 2.0
    
    # 决策记录配置
    decision_history_size: int = 10000
    decision_eval_window: int = 100
    weight_evolution_lr: float = 0.01
    
    # 探索保护
    explore_max_failures: int = 5
    explore_freeze_duration: timedelta = timedelta(hours=1)
```

## 9. 测试与验证

### 9.1 单元测试

1. 任务评分公式正确性测试
2. 探索-利用比例统计验证
3. 中断条件触发测试
4. 决策权重约束测试

### 9.2 场景测试

1. 高安全缺口场景：验证是否优先选择安全任务
2. 稳态场景：验证探索率是否上浮
3. 资源紧张场景：验证是否优先选择低资源任务
4. 任务中断场景：验证中断流程正确性

### 9.3 长期测试

1. 探索-利用比例长期统计（应趋近70:30）
2. 决策质量趋势分析
3. 任务中断频率监控

## 10. 性能优化

### 10.1 评分缓存

对未变化的候选任务缓存评分结果：

```python
task_score_cache = {}

def get_cached_score(task, state_hash):
    cache_key = (task.task_id, state_hash)
    if cache_key in task_score_cache:
        return task_score_cache[cache_key]
    score = compute_score(task, state)
    task_score_cache[cache_key] = score
    return score
```

### 10.2 并行评分

对大量候选任务采用并行评分：

```python
from concurrent.futures import ThreadPoolExecutor

def score_tasks_parallel(tasks, state_vector, drive_output):
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(score_task, t, state_vector, drive_output) 
                  for t in tasks]
        scores = [f.result() for f in futures]
    return scores
```

---

自主决策模块作为Agent系统的"大脑皮层"，其设计质量直接决定了Agent能否在每一时刻做出全局最优的自主选择。通过精细化的评分体系、严格的探索-利用平衡和灵敏的动态中断机制，确保Agent既能稳定运行又能持续进化。
