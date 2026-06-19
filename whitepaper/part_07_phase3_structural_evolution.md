# 第三阶段：永续进化闭环 —— 模型结构性重构详细技术方案

## 1. 模块概述

模型结构性重构模块是整个自驱永续进化Agent系统的进化执行层，负责在微修正无法有效降低预测误差时，对模型结构进行深度重构。本模块实现了特征增删、子模型重组、规则迭代、认知体系更新等进阶进化能力，使Agent能够突破旧模型局限，实现认知能力的跃迁式提升。

## 2. 设计目标

1. 自动触发：基于误差趋势自动判断是否需要结构性重构
2. 安全进化：重构前自动创建快照，支持回滚
3. 效果验证：重构后严格验证性能，防止退化
4. 资源可控：重构过程的资源消耗在约束范围内
5. 渐进迭代：单次重构只做有限改动，避免剧烈变化

## 3. 重构触发机制

### 3.1 触发条件

#### 3.1.1 持续高误差触发

```python
def should_trigger_reconstruction(error_history: List[float]) -> bool:
    """判断是否应触发结构性重构"""
    # 条件1：最近N个周期的平均误差超过阈值
    recent_avg_error = mean(error_history[-RECON_WINDOW:])
    if recent_avg_error < RECON_ERROR_THRESHOLD:
        return False
    
    # 条件2：误差趋势持续上升
    error_trend = linear_regression_slope(error_history[-RECON_WINDOW:])
    if error_trend < 0:  # 误差在下降，不需要重构
        return False
    
    # 条件3：微修正未能改善误差
    micro_adjust_effect = error_history[-RECON_WINDOW] - error_history[-1]
    if micro_adjust_effect > 0:  # 微修正有效
        return False
    
    # 条件4：距离上次重构足够久
    if time_since_last_reconstruction < RECON_COOLDOWN:
        return False
    
    return True
```

#### 3.1.2 长期稳态无提升触发

```python
def should_trigger_due_to_stagnation(performance_history: List[float]) -> bool:
    """因长期停滞触发重构"""
    # 检查最近STAGNATION_WINDOW个周期是否有显著提升
    best_recent = max(performance_history[-STAGNATION_WINDOW:])
    best_historical = max(performance_history[:-STAGNATION_WINDOW])
    
    improvement = (best_recent - best_historical) / abs(best_historical)
    
    return improvement < STAGNATION_IMPROVEMENT_THRESHOLD
```

#### 3.1.3 新环境探索触发

```python
def should_trigger_due_to_new_environment(state_vector: StateVector,
                                         baseline: StateVector) -> bool:
    """因发现新环境特征触发重构"""
    # 检测新维度
    new_dimensions = detect_new_dimensions(state_vector, baseline)
    
    # 检测新模式
    new_patterns = detect_new_patterns(state_vector)
    
    return len(new_dimensions) > 0 or len(new_patterns) > NEW_PATTERN_THRESHOLD
```

### 3.2 重构优先级评估

```python
def evaluate_reconstruction_priority(trigger_reason: str, 
                                    current_gaps: Dict[str, float]) -> int:
    """评估重构优先级（1-10，10最高）"""
    base_priority = {
        'high_error': 8,
        'stagnation': 6,
        'new_environment': 7
    }.get(trigger_reason, 5)
    
    # 安全缺口高时提升优先级
    if current_gaps['safe'] > 0.5:
        base_priority += 2
    
    return min(base_priority, 10)
```

## 4. 重构策略体系

### 4.1 特征工程重构

#### 4.1.1 特征增删

```python
def feature_engineering_reconstruction(model, state_history: List[StateVector]):
    """特征工程重构"""
    current_features = model.feature_names
    
    # 特征删除：移除低重要性特征
    feature_importance = calculate_feature_importance(model, state_history)
    features_to_remove = [
        f for f, imp in feature_importance.items() 
        if imp < FEATURE_REMOVE_THRESHOLD
    ]
    
    # 特征新增：基于因果发现添加新特征
    new_features = discover_new_features(state_history)
    features_to_add = [
        f for f in new_features 
        if f not in current_features and is_feature_valuable(f, state_history)
    ]
    
    # 特征变换：创建组合特征
    combined_features = create_combined_features(
        [f for f in current_features if f not in features_to_remove],
        state_history
    )
    
    return {
        'remove': features_to_remove,
        'add': features_to_add,
        'combine': combined_features
    }
```

#### 4.1.2 特征重要性计算

```python
def calculate_feature_importance(model, state_history) -> Dict[str, float]:
    """计算特征重要性（基于排列重要性）"""
    baseline_error = evaluate_model(model, state_history)
    importances = {}
    
    for feature in model.feature_names:
        # 打乱该特征的值
        shuffled_history = shuffle_feature(state_history, feature)
        shuffled_error = evaluate_model(model, shuffled_history)
        
        # 重要性 = 误差增加量
        importances[feature] = shuffled_error - baseline_error
    
    # 归一化
    max_importance = max(importances.values())
    return {k: v / max_importance for k, v in importances.items()}
```

### 4.2 子模型重组

#### 4.2.1 模型拆分

```python
def split_submodel(parent_model, state_history, performance_threshold):
    """将表现不佳的子模型拆分为更细的子模型"""
    submodels = parent_model.submodels
    
    for submodel in submodels:
        submodel_error = evaluate_submodel(submodel, state_history)
        
        if submodel_error > performance_threshold:
            # 拆分为两个更专门的子模型
            new_submodels = split_by_clustering(
                submodel, 
                state_history,
                n_clusters=2
            )
            
            # 替换原子模型
            replace_submodel(parent_model, submodel, new_submodels)
```

#### 4.2.2 模型合并

```python
def merge_submodels(parent_model, similarity_threshold):
    """合并相似的子模型以减少冗余"""
    submodels = parent_model.submodels
    
    # 计算子模型相似度矩阵
    similarity_matrix = compute_model_similarity_matrix(submodels)
    
    # 合并高相似度的子模型对
    merged = set()
    for i in range(len(submodels)):
        if i in merged:
            continue
        for j in range(i + 1, len(submodels)):
            if j in merged:
                continue
            if similarity_matrix[i][j] > similarity_threshold:
                merged_submodel = merge_two_submodels(submodels[i], submodels[j])
                replace_submodels(parent_model, [i, j], merged_submodel)
                merged.update([i, j])
                break
```

### 4.3 规则迭代

#### 4.3.1 规则发现

```python
def discover_rules(state_history: List[StateVector], 
                  min_support: float, 
                  min_confidence: float) -> List[Rule]:
    """从状态历史中发现关联规则"""
    # 将连续状态离散化
    discretized_states = discretize_states(state_history)
    
    # 使用Apriori算法发现频繁项集
    frequent_itemsets = apriori(discretized_states, min_support)
    
    # 生成关联规则
    rules = []
    for itemset in frequent_itemsets:
        for antecedent, consequent in generate_partitions(itemset):
            confidence = calculate_confidence(antecedent, consequent, discretized_states)
            if confidence >= min_confidence:
                rules.append(Rule(antecedent, consequent, confidence))
    
    return rules
```

#### 4.3.2 规则评估与更新

```python
def evaluate_and_update_rules(current_rules: List[Rule], 
                              new_rules: List[Rule],
                              state_history: List[StateVector]):
    """评估规则并更新规则库"""
    # 评估现有规则
    for rule in current_rules:
        rule.current_confidence = evaluate_rule(rule, state_history)
        rule.age += 1
    
    # 淘汰失效规则
    active_rules = [r for r in current_rules 
                   if r.current_confidence > RULE_MIN_CONFIDENCE]
    
    # 添加新发现的高置信度规则
    for new_rule in new_rules:
        if new_rule.confidence > RULE_ADD_THRESHOLD:
            # 检查是否与现有规则冲突
            if not has_conflict(new_rule, active_rules):
                active_rules.append(new_rule)
    
    return active_rules
```

### 4.4 认知体系更新

#### 4.4.1 维度关系图更新

```python
def update_cognitive_graph(state_history: List[StateVector],
                          current_graph: CognitiveGraph) -> CognitiveGraph:
    """更新认知维度关系图"""
    # 重新计算维度间相关性
    correlation_matrix = compute_correlation_matrix(state_history)
    
    # 更新图中的边权重
    for i, dim_i in enumerate(current_graph.dimensions):
        for j, dim_j in enumerate(current_graph.dimensions):
            if i != j:
                weight = abs(correlation_matrix[i][j])
                current_graph.update_edge(dim_i, dim_j, weight)
    
    # 发现新的强关联
    new_edges = []
    for i in range(len(current_graph.dimensions)):
        for j in range(i + 1, len(current_graph.dimensions)):
            if correlation_matrix[i][j] > NEW_EDGE_THRESHOLD:
                dim_i = current_graph.dimensions[i]
                dim_j = current_graph.dimensions[j]
                if not current_graph.has_edge(dim_i, dim_j):
                    new_edges.append((dim_i, dim_j, correlation_matrix[i][j]))
    
    for dim_i, dim_j, weight in new_edges:
        current_graph.add_edge(dim_i, dim_j, weight)
    
    return current_graph
```

#### 4.4.2 层次结构重组

```python
def restructure_hierarchy(current_hierarchy: ModelHierarchy,
                         performance_metrics: Dict) -> ModelHierarchy:
    """重组模型层次结构"""
    # 分析各层模型的性能
    layer_performance = {}
    for layer_name, layer in current_hierarchy.layers.items():
        layer_performance[layer_name] = evaluate_layer(layer, performance_metrics)
    
    # 如果底层模型性能不足，增加中间层
    if layer_performance['low'] < LAYER_PERFORMANCE_THRESHOLD:
        new_layer = create_intermediate_layer(
            current_hierarchy.layers['low'],
            current_hierarchy.layers['mid']
        )
        current_hierarchy.insert_layer('low_mid', new_layer)
    
    # 如果高层模型过于复杂，尝试简化
    if layer_performance['high'] > LAYER_PERFORMANCE_THRESHOLD:
        simplified = simplify_high_layer(current_hierarchy.layers['high'])
        current_hierarchy.layers['high'] = simplified
    
    return current_hierarchy
```

## 5. 重构执行流程

### 5.1 重构前准备

```python
class ReconstructionExecutor:
    def prepare_reconstruction(self) -> ReconstructionContext:
        """重构前准备"""
        context = ReconstructionContext()
        
        # 1. 创建系统快照
        context.snapshot_id = self.memory.create_snapshot(tag="pre_reconstruction")
        
        # 2. 收集重构所需数据
        context.training_data = self.memory.get_training_data(
            sample_size=RECON_TRAINING_SAMPLES
        )
        context.validation_data = self.memory.get_validation_data(
            sample_size=RECON_VALIDATION_SAMPLES
        )
        
        # 3. 评估当前模型性能
        context.baseline_performance = self.evaluate_current_model(
            context.validation_data
        )
        
        # 4. 确定重构策略
        context.strategy = self.select_reconstruction_strategy(
            context.baseline_performance
        )
        
        return context
```

### 5.2 重构执行

```python
    def execute_reconstruction(self, context: ReconstructionContext):
        """执行重构"""
        strategy = context.strategy
        
        if strategy == 'feature_engineering':
            self.execute_feature_reconstruction(context)
        elif strategy == 'submodel_reorganization':
            self.execute_submodel_reconstruction(context)
        elif strategy == 'rule_iteration':
            self.execute_rule_reconstruction(context)
        elif strategy == 'cognitive_update':
            self.execute_cognitive_reconstruction(context)
        elif strategy == 'combined':
            self.execute_combined_reconstruction(context)
        
        # 限制重构迭代次数
        context.iteration_count += 1
        if context.iteration_count >= MAX_RECON_ITERATIONS:
            context.status = 'max_iterations_reached'
```

### 5.3 重构后验证

```python
    def validate_reconstruction(self, context: ReconstructionContext) -> bool:
        """验证重构效果"""
        # 1. 性能验证
        new_performance = self.evaluate_current_model(context.validation_data)
        performance_improvement = (
            (context.baseline_performance['error'] - new_performance['error']) /
            context.baseline_performance['error']
        )
        
        if performance_improvement < RECON_MIN_IMPROVEMENT:
            # 性能未提升，回滚
            self.rollback_reconstruction(context)
            return False
        
        # 2. 稳定性验证
        stability_score = self.evaluate_stability(context.validation_data)
        if stability_score < RECON_MIN_STABILITY:
            self.rollback_reconstruction(context)
            return False
        
        # 3. 资源验证
        resource_usage = self.evaluate_resource_usage()
        if resource_usage > RECON_MAX_RESOURCE_USAGE:
            self.rollback_reconstruction(context)
            return False
        
        # 验证通过
        context.new_performance = new_performance
        return True
```

### 5.4 回滚机制

```python
    def rollback_reconstruction(self, context: ReconstructionContext):
        """回滚到重构前状态"""
        # 从快照恢复
        success = self.memory.rollback_to_snapshot(context.snapshot_id)
        
        if success:
            # 记录回滚事件
            self.memory.record_event(
                event_type='reconstruction_rollback',
                reason='validation_failed',
                snapshot_id=context.snapshot_id
            )
            
            # 标记该重构策略为近期不可使用
            self.mark_strategy_cooldown(context.strategy, RECON_STRATEGY_COOLDOWN)
        else:
            # 快照恢复失败，紧急处理
            self.emergency_recovery()
```

## 6. 重构策略选择

### 6.1 策略选择决策树

```
误差类型分析
    │
    ├── 特定维度误差高
    │       └── 选择：特征工程重构
    │
    ├── 多维度协同误差
    │       └── 选择：子模型重组
    │
    ├── 序列模式识别失败
    │       └── 选择：规则迭代
    │
    ├── 整体认知偏差
    │       └── 选择：认知体系更新
    │
    └── 多种误差并存
            └── 选择：组合重构（按优先级顺序执行）
```

### 6.2 策略效果跟踪

```python
class StrategyTracker:
    def __init__(self):
        self.strategy_history: Dict[str, List[StrategyResult]] = {}
    
    def record_result(self, strategy: str, result: StrategyResult):
        if strategy not in self.strategy_history:
            self.strategy_history[strategy] = []
        self.strategy_history[strategy].append(result)
    
    def get_best_strategy(self, error_pattern: str) -> str:
        """根据误差模式选择历史最佳策略"""
        strategy_scores = {}
        for strategy, results in self.strategy_history.items():
            relevant_results = [r for r in results if r.error_pattern == error_pattern]
            if relevant_results:
                avg_improvement = mean([r.improvement for r in relevant_results])
                success_rate = mean([1 if r.success else 0 for r in relevant_results])
                strategy_scores[strategy] = avg_improvement * success_rate
        
        return max(strategy_scores, key=strategy_scores.get)
```

## 7. 接口定义

### 7.1 对外接口

```python
class StructuralEvolution:
    def __init__(self, config: EvolutionConfig):
        """初始化结构性进化模块"""
        pass
    
    def check_reconstruction_needed(self, 
                                    error_history: List[float],
                                    current_gaps: Dict[str, float]) -> bool:
        """检查是否需要重构"""
        pass
    
    def execute_reconstruction(self, 
                              trigger_reason: str,
                              state_history: List[StateVector]) -> ReconstructionResult:
        """
        执行结构性重构
        
        Args:
            trigger_reason: 触发原因
            state_history: 状态历史
            
        Returns:
            ReconstructionResult: 重构结果
        """
        pass
    
    def get_reconstruction_history(self) -> List[ReconstructionRecord]:
        """获取重构历史"""
        pass
    
    def get_strategy_stats(self) -> Dict[str, StrategyStats]:
        """获取各策略的统计信息"""
        pass
```

### 7.2 配置参数

```python
@dataclass
class EvolutionConfig:
    # 触发配置
    recon_error_threshold: float = 0.3
    recon_window: int = 100
    recon_cooldown: timedelta = timedelta(hours=6)
    stagnation_window: int = 500
    stagnation_improvement_threshold: float = 0.01
    new_pattern_threshold: int = 5
    
    # 重构限制
    max_recon_iterations: int = 3
    recon_min_improvement: float = 0.05
    recon_min_stability: float = 0.8
    recon_max_resource_usage: float = 0.5  # 重构期间资源使用上限
    recon_training_samples: int = 5000
    recon_validation_samples: int = 1000
    
    # 特征工程配置
    feature_remove_threshold: float = 0.05
    feature_add_threshold: float = 0.1
    
    # 子模型配置
    submodel_merge_threshold: float = 0.9
    submodel_split_threshold: float = 0.3
    
    # 规则配置
    rule_min_support: float = 0.1
    rule_min_confidence: float = 0.7
    rule_min_confidence_active: float = 0.5
    rule_add_threshold: float = 0.8
    
    # 认知图配置
    new_edge_threshold: float = 0.7
    layer_performance_threshold: float = 0.6
    
    # 策略配置
    recon_strategy_cooldown: timedelta = timedelta(hours=12)
```

## 8. 测试与验证

### 8.1 单元测试

1. 重构触发条件测试
2. 各重构策略的独立测试
3. 回滚机制测试
4. 策略选择逻辑测试

### 8.2 集成测试

1. 端到端重构流程测试
2. 重构后系统一致性测试
3. 并发重构与正常运行的隔离测试

### 8.3 安全测试

1. 重构失败后的回滚测试
2. 资源超限保护测试
3. 迭代次数限制测试

---

模型结构性重构模块作为Agent系统的"进化引擎"，其设计质量直接决定了Agent能否突破认知瓶颈、实现能力跃迁。通过多策略重构体系、严格的效果验证和安全的回滚机制，确保Agent在持续进化的同时保持稳定运行。
