# 第一阶段：基础自驱闭环 —— 驱力引擎模块详细技术方案

## 1. 模块概述

驱力引擎模块是整个自驱永续进化Agent系统的动机层，是全系统自驱的唯一来源。该模块负责基于环境感知模块提供的标准化状态向量，实时计算三大原生驱力（安全驱力、收益驱力、能效驱力）的量化值，动态调整权重分配，生成价值缺口信号，为后续的任务生成和自主决策提供核心依据。

## 2. 设计目标

1. 仿生真实性：三大驱力的计算逻辑必须真实反映生物本能的运作机制
2. 实时响应：驱力计算延迟不超过环境感知数据的采集周期
3. 动态自适应：权重分配能够根据环境状态自动调整
4. 缺口可量化：价值缺口必须能够精确量化为标量数值
5. 动机持续性：确保在任何状态下都能产生非零的驱力输出

## 3. 安全驱力 Reward_safe 计算体系

### 3.1 输入信号来源

安全驱力的输入来源于环境感知模块的系统层和日志层数据：

1. 系统异常信号
   - CPU使用率突增（超过历史基线2σ）
   - 内存使用率超过80%
   - 磁盘使用率超过90%
   - 僵尸进程数量异常
   - 系统负载突增

2. 日志异常信号
   - 错误日志频率突增
   - 异常日志模式首次出现
   - 安全相关日志（认证失败、权限异常）
   - 资源耗尽日志（OOM、磁盘满）

3. 未知状态信号
   - 新进程出现（未在基线中记录）
   - 新文件变更（未在监控列表中）
   - 新日志模式出现
   - 网络连接异常

4. 风险进程信号
   - CPU占用Top1%进程的行为异常
   - 内存泄漏模式进程
   - 高频I/O进程
   - 异常网络活动进程

5. 突变负载信号
   - 系统负载在短时间内的剧烈变化
   - 网络流量的异常波动
   - 磁盘I/O的突发峰值

### 3.2 安全威胁量化模型

#### 3.2.1 单威胁评分函数

对于每个检测到的威胁信号，计算其威胁评分：

```
Threat_Score_i = Severity_i × Urgency_i × Novelty_i
```

其中：
- Severity（严重性）：该威胁对系统稳定的潜在影响程度，[0, 1]
- Urgency（紧迫性）：该威胁需要响应的紧急程度，[0, 1]
- Novelty（新颖性）：该威胁的历史出现频率的倒数，[0, 1]

#### 3.2.2 严重性分级

| 威胁类型 | 严重性基准值 | 动态调整因子 |
|---------|------------|------------|
| 系统资源耗尽 | 0.95 | 根据当前使用率线性递增 |
| 安全入侵迹象 | 0.90 | 根据攻击特征加权 |
| 关键服务异常 | 0.85 | 根据服务重要性加权 |
| 性能严重下降 | 0.75 | 根据下降幅度加权 |
| 一般异常日志 | 0.50 | 根据频率加权 |
| 轻微状态偏离 | 0.25 | 根据偏离程度加权 |

#### 3.2.3 紧迫性计算

```
Urgency = 1 - exp(-λ × t_elapsed)
```

其中t_elapsed为威胁持续存在的时间，λ为衰减系数。威胁存在时间越长，紧迫性越高。

#### 3.2.4 新颖性计算

```
Novelty = 1 / (1 + frequency_history)
```

其中frequency_history为该威胁类型在历史记录中的出现次数。首次出现的威胁新颖性最高。

### 3.3 安全驱力综合计算

#### 3.3.1 多威胁聚合

当同时存在多个威胁时，采用非线性聚合公式：

```
Total_Threat = 1 - ∏(1 - Threat_Score_i)
```

该公式确保：
- 单个高威胁信号能够主导总威胁值
- 多个低威胁信号的累积效应存在上限
- 总威胁值始终保持在[0, 1]区间

#### 3.3.2 安全基线建立

系统运行初期建立安全基线：

1. 收集前N个时间周期的环境状态数据
2. 计算各指标的历史均值和标准差
3. 建立各指标的正常波动范围
4. 标记超出正常范围的异常事件

#### 3.3.3 安全驱力输出

```
Reward_safe = 1 - Total_Threat
```

安全驱力与总威胁值呈反比：
- 当没有任何威胁时，Reward_safe = 1（完全安全）
- 当威胁累积到最大时，Reward_safe → 0（极度危险）

### 3.4 安全驱力的行为倾向映射

高安全缺口（低Reward_safe）时，系统倾向生成以下类型任务：

1. 风险预测任务：预测潜在的资源耗尽、服务崩溃
2. 异常检测任务：深入分析异常日志、异常进程
3. 状态监控任务：加强对关键指标的监控频率
4. 维稳任务：释放缓存、清理临时文件、优化资源分配

## 4. 收益驱力 Reward_gain 计算体系

### 4.1 输入信号来源

收益驱力的输入来源于环境感知模块的自身层数据，反映Agent的认知进化状态：

1. 预测误差信号
   - 各预测模型的当前均方误差（MSE）
   - 各预测模型的平均绝对误差（MAE）
   - 预测误差的趋势变化（上升/下降/平稳）

2. 新增信息维度信号
   - 环境状态向量中新出现的非零特征数量
   - 日志中新发现的模式数量
   - 文件系统中新增的监控对象

3. 新规律发现数信号
   - 预测模型捕获的新相关性数量
   - 异常检测发现的新异常类型
   - 时序分析发现的新周期模式

4. 认知覆盖度信号
   - 已建立预测模型的环境维度占比
   - 已识别日志模式占全部日志的比例
   - 已监控文件/目录占总文件系统的比例

### 4.2 预测误差量化模型

#### 4.2.1 误差归一化

原始预测误差需要归一化处理，使其具有可比性：

```
Normalized_Error = Actual_Error / Baseline_Error
```

其中Baseline_Error为系统初始状态或随机猜测的基准误差。

#### 4.2.2 误差趋势计算

```
Error_Trend = (Error[t] - Error[t-window]) / window
```

误差趋势分为三类：
- Error_Trend < -threshold：误差下降（进化正向）
- |Error_Trend| ≤ threshold：误差平稳
- Error_Trend > threshold：误差上升（进化负向）

#### 4.2.3 多模型误差聚合

当存在多个预测模型时，采用加权聚合：

```
Total_Error = Σ(Error_i × Importance_i) / Σ(Importance_i)
```

其中Importance_i为第i个模型的重要性权重，根据该模型预测的环境维度重要性动态调整。

### 4.3 认知覆盖度量化模型

#### 4.3.1 维度覆盖度

```
Dimension_Coverage = Monitored_Dimensions / Total_Dimensions
```

Total_Dimensions为理论上可观测的全部环境维度数量。

#### 4.3.2 模式覆盖度

```
Pattern_Coverage = Recognized_Patterns / Total_Patterns
```

Total_Patterns为历史数据中出现的全部独特模式数量。

#### 4.3.3 综合认知覆盖度

```
Cognitive_Coverage = w1 × Dimension_Coverage + w2 × Pattern_Coverage + w3 × Model_Coverage
```

### 4.4 收益驱力综合计算

#### 4.4.1 收益缺口计算

```
Gain_Gap = (Target_Error - Current_Error) / Target_Error × w_error + 
           (1 - Cognitive_Coverage) × w_coverage +
           New_Discoveries_Rate × w_discovery
```

其中：
- Target_Error为理论最优误差（趋近于0但不等于0）
- Current_Error为当前综合预测误差
- New_Discoveries_Rate为单位时间内的新发现数量

#### 4.4.2 收益驱力输出

```
Reward_gain = sigmoid(Gain_Gap × scale_factor)
```

使用sigmoid函数将收益缺口映射到[0, 1]区间，确保：
- 当Gap为0时，Reward_gain = 0.5（中性状态）
- 当Gap为正（有进化空间）时，Reward_gain > 0.5
- 当Gap为负（退化）时，Reward_gain < 0.5

### 4.5 收益驱力的行为倾向映射

高收益缺口（Reward_gain偏低）时，系统倾向生成以下类型任务：

1. 未知探索任务：探索未监控的环境维度
2. 新特征测试任务：测试新特征对预测精度的提升
3. 规律挖掘任务：深入分析历史数据寻找隐藏模式
4. 认知拓展任务：建立新的预测模型、扩展监控范围

## 5. 能效驱力 Reward_eff 计算体系

### 5.1 输入信号来源

能效驱力的输入来源于环境感知模块的系统层和自身层数据：

1. CPU消耗信号
   - Agent进程的CPU使用率
   - 预测模型推理的CPU耗时
   - 各模块执行的CPU耗时分布

2. 内存消耗信号
   - Agent进程的内存占用
   - 缓存数据结构的内存占用
   - 模型参数的内存占用

3. 推理耗时信号
   - 单次预测推理的耗时
   - 批量预测推理的耗时
   - 各模型推理耗时的分布

4. 计算冗余度信号
   - 重复计算的比例
   - 无效预测的比例（预测了未发生变化的指标）
   - 过度采集的比例（采集了未使用的指标）

### 5.2 资源消耗量化模型

#### 5.2.1 CPU效率指数

```
CPU_Efficiency = Useful_Computation / Total_CPU_Usage
```

Useful_Computation为产生有效预测/决策的CPU耗时。

#### 5.2.2 内存效率指数

```
Memory_Efficiency = Active_Data_Size / Total_Memory_Usage
```

Active_Data_Size为近期被访问过的数据量。

#### 5.2.3 推理效率指数

```
Inference_Efficiency = Prediction_Accuracy / Inference_Time
```

单位时间产生的预测精度。

### 5.3 计算冗余度量化模型

#### 5.3.1 重复计算检测

```
Redundancy_Ratio = Redundant_Computations / Total_Computations
```

通过缓存机制检测重复计算：相同输入在短时间内的重复推理。

#### 5.3.2 无效预测检测

```
Invalid_Prediction_Ratio = Invalid_Predictions / Total_Predictions
```

无效预测定义为：预测值与实际值的偏差在可接受范围内，但该预测未对任何决策产生实质影响。

### 5.4 能效驱力综合计算

#### 5.4.1 资源压力指数

```
Resource_Pressure = w_cpu × CPU_Usage_Ratio + w_mem × Memory_Usage_Ratio
```

其中Usage_Ratio为当前使用量与上限的比值。

#### 5.4.2 能效缺口计算

```
Eff_Gap = Resource_Pressure × w_pressure + Redundancy_Ratio × w_redundancy + 
          (1 - Inference_Efficiency) × w_efficiency
```

#### 5.4.3 能效驱力输出

```
Reward_eff = 1 - Eff_Gap
```

能效驱力与资源压力和冗余度呈反比：
- 当资源使用最优、无冗余时，Reward_eff = 1
- 当资源压力最大、冗余最高时，Reward_eff → 0

### 5.5 能效驱力的行为倾向映射

高能效缺口（Reward_eff偏低）时，系统倾向生成以下类型任务：

1. 模型精简任务：压缩模型参数、剪枝冗余特征
2. 逻辑压缩任务：合并相似计算、优化算法复杂度
3. 冗余清除任务：清理过期缓存、删除无用数据
4. 降频优化任务：降低非关键模块的采集/计算频率

## 6. 动态权重调整机制

### 6.1 权重调整触发条件

三大驱力的权重W_safe、W_gain、W_eff不是固定值，而是根据环境状态动态调整：

#### 6.1.1 紧急风险场景

触发条件：
- Total_Threat > 0.7（高威胁）
- 或系统关键资源使用率 > 90%

权重调整：
```
W_safe = 0.7
W_gain = 0.15
W_eff = 0.15
```

#### 6.1.2 稳态空闲场景

触发条件：
- Total_Threat < 0.1（低威胁）
- 且系统资源使用率 < 50%
- 且预测误差趋势平稳

权重调整：
```
W_safe = 0.2
W_gain = 0.6
W_eff = 0.2
```

#### 6.1.3 资源紧张场景

触发条件：
- Agent自身资源使用率 > 80%上限
- 或系统整体资源紧张

权重调整：
```
W_safe = 0.2
W_gain = 0.2
W_eff = 0.6
```

### 6.2 平滑过渡机制

权重调整不是瞬间切换，而是采用平滑过渡：

```
W_new = W_current + α × (W_target - W_current)
```

其中α为过渡系数（0 < α < 1），确保权重变化不会引起系统行为的剧烈抖动。

### 6.3 权重约束

权重始终满足以下约束：

```
W_safe + W_gain + W_eff = 1.0
W_safe ≥ 0.1, W_gain ≥ 0.1, W_eff ≥ 0.1
```

确保任何驱力都不会被完全压制，维持系统的多目标平衡。

## 7. 全局总奖励计算

### 7.1 总奖励公式

```
Reward_total = W_safe × Reward_safe + W_gain × Reward_gain + W_eff × Reward_eff
```

### 7.2 缺口驱动信号输出

总奖励计算完成后，输出三个维度的缺口信号：

```
Gap_safe = 1 - Reward_safe
Gap_gain = 1 - Reward_gain
Gap_eff = 1 - Reward_eff
```

缺口信号用于驱动后续的任务生成模块：
- Gap值越大，表示该维度的进化需求越强烈
- 三个Gap值共同构成任务生成的输入条件

### 7.3 紧急度评估

综合三个缺口信号，评估系统的整体紧急度：

```
Urgency = max(Gap_safe × Emergency_Factor_safe, 
              Gap_gain × Emergency_Factor_gain, 
              Gap_eff × Emergency_Factor_eff)
```

Emergency_Factor为各维度的紧急系数，安全维度的紧急系数最高。

## 8. 驱力引擎的运行循环

### 8.1 循环流程

```
1. 接收环境状态向量（来自感知模块）
2. 更新安全基线（如处于基线建立期）
3. 计算各威胁信号的Threat_Score
4. 聚合计算Total_Threat和Reward_safe
5. 计算预测误差和认知覆盖度
6. 计算Reward_gain
7. 计算资源压力和冗余度
8. 计算Reward_eff
9. 评估当前场景类型
10. 动态调整权重W_safe/W_gain/W_eff
11. 计算Reward_total
12. 输出Gap_safe/Gap_gain/Gap_eff
13. 输出Urgency
14. 等待下一个周期
```

### 8.2 运行频率

驱力引擎的运行频率与环境感知模块保持一致，默认为每秒一次。在紧急场景下，可以提升至每秒多次。

### 8.3 状态持久化

驱力引擎的内部状态需要持久化：

1. 安全基线数据（历史均值、标准差）
2. 威胁历史记录
3. 误差历史趋势
4. 权重调整历史

持久化采用增量写入方式，每N个周期写入一次本地存储。

## 9. 接口定义

### 9.1 对外接口

```python
class DriveEngine:
    def __init__(self, config: DriveConfig):
        """初始化驱力引擎"""
        pass
    
    def compute(self, state_vector: StateVector) -> DriveOutput:
        """
        计算驱力输出
        
        Args:
            state_vector: 环境状态向量
            
        Returns:
            DriveOutput: 包含Reward_total、各Gap值、Urgency等
        """
        pass
    
    def update_baseline(self, state_vector: StateVector):
        """更新安全基线"""
        pass
    
    def get_drive_history(self, duration: timedelta) -> List[DriveOutput]:
        """获取历史驱力输出"""
        pass
    
    def set_weight_bias(self, safe: float, gain: float, eff: float):
        """设置人工柔性偏置权重"""
        pass
```

### 9.2 配置参数

```python
@dataclass
class DriveConfig:
    # 基线建立参数
    baseline_periods: int = 100  # 基线建立期数
    baseline_update_rate: float = 0.01  # 基线更新速率
    
    # 威胁检测参数
    threat_severity_weights: Dict[str, float] = None
    threat_urgency_lambda: float = 0.1
    
    # 收益计算参数
    target_error: float = 0.01
    error_weight: float = 0.5
    coverage_weight: float = 0.3
    discovery_weight: float = 0.2
    
    # 能效计算参数
    cpu_weight: float = 0.4
    mem_weight: float = 0.3
    redundancy_weight: float = 0.2
    efficiency_weight: float = 0.1
    
    # 权重调整参数
    weight_transition_alpha: float = 0.1
    min_weight: float = 0.1
    
    # 场景阈值
    high_threat_threshold: float = 0.7
    low_threat_threshold: float = 0.1
    resource_relaxed_threshold: float = 0.5
    resource_tight_threshold: float = 0.8
```

## 10. 测试与验证

### 10.1 单元测试

1. 各驱力计算公式的正确性验证
2. 威胁评分的边界条件测试
3. 权重调整的平滑性测试
4. 缺口输出的单调性测试

### 10.2 场景测试

1. 模拟高威胁场景，验证安全权重是否主导
2. 模拟稳态场景，验证收益权重是否主导
3. 模拟资源紧张场景，验证能效权重是否主导
4. 模拟场景切换，验证权重过渡是否平滑

### 10.3 长期测试

1. 长时间运行下的基线稳定性
2. 驱力输出的连续性验证
3. 资源消耗的稳定性验证

## 11. 性能优化

### 11.1 增量计算

对于变化缓慢的信号（如基线统计），采用增量更新而非全量重算。

### 11.2 缓存复用

中间计算结果（如威胁评分、误差趋势）进行缓存，避免重复计算。

### 11.3 异步处理

驱力计算与环境感知解耦，采用生产者-消费者模式异步处理。

---

驱力引擎模块作为Agent系统的"本能中枢"，其设计质量直接决定了Agent能否产生真实、持续、自适应的内生动机。通过精细化的驱力量化模型和动态权重调整机制，确保Agent在任何环境下都能产生合理的自驱行为。
