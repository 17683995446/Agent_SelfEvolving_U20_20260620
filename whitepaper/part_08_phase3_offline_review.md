# 第三阶段：永续进化闭环 —— 离线批量复盘模块详细技术方案

## 1. 模块概述

离线批量复盘模块是整个自驱永续进化Agent系统的"睡眠进化"层，负责在系统空闲时段批量重放历史数据、批量优化模型、压缩冗余信息。本模块实现了Agent的"离线学习"能力，利用低算力时段进行深度认知加工，是在线实时循环的重要补充，确保Agent能够持续积累认知优势。

## 2. 设计目标

1. 空闲触发：系统空闲时自动触发离线复盘
2. 批量优化：批量重放历史样本，深度优化模型
3. 知识压缩：压缩冗余信息，提炼核心知识
4. 资源隔离：复盘过程不影响在线运行
5. 效果累积：每次复盘都能带来可量化的认知提升

## 3. 复盘触发机制

### 3.1 空闲状态检测

```python
def is_system_idle(state_vector: StateVector, 
                   history: List[StateVector]) -> bool:
    """检测系统是否处于空闲状态"""
    # 条件1：当前资源使用率低于阈值
    if state_vector.cpu_usage > IDLE_CPU_THRESHOLD:
        return False
    
    if state_vector.memory_usage > IDLE_MEM_THRESHOLD:
        return False
    
    # 条件2：近期无异常事件
    recent_anomalies = count_anomalies(history[-IDLE_CHECK_WINDOW:])
    if recent_anomalies > 0:
        return False
    
    # 条件3：近期驱力缺口平稳
    recent_gaps = [s.gap_total for s in history[-IDLE_CHECK_WINDOW:]]
    gap_variance = variance(recent_gaps)
    if gap_variance > IDLE_GAP_VARIANCE_THRESHOLD:
        return False
    
    # 条件4：距离上次复盘足够久
    if time_since_last_review < REVIEW_MIN_INTERVAL:
        return False
    
    return True
```

### 3.2 强制复盘触发

```python
def should_force_review(review_history: List[ReviewRecord]) -> bool:
    """判断是否应强制触发复盘（无论是否空闲）"""
    # 超过最大复盘间隔强制触发
    if time_since_last_review > REVIEW_MAX_INTERVAL:
        return True
    
    # 累积数据量达到阈值触发
    pending_data_count = count_unprocessed_data()
    if pending_data_count > REVIEW_DATA_THRESHOLD:
        return True
    
    # 模型性能持续下降触发
    recent_performance = get_recent_performance()
    if recent_performance < REVIEW_PERFORMANCE_THRESHOLD:
        return True
    
    return False
```

### 3.3 复盘窗口规划

```python
def plan_review_window() -> ReviewWindow:
    """规划复盘时间窗口"""
    window = ReviewWindow()
    
    # 预估复盘所需时间
    pending_data = count_unprocessed_data()
    estimated_duration = estimate_review_duration(pending_data)
    
    # 根据系统负载模式选择最佳复盘时段
    if has_predictable_idle_pattern():
        window.start_time = predict_next_idle_period()
    else:
        # 立即开始，但限制资源使用
        window.start_time = datetime.now()
        window.resource_limit = 0.1  # 限制10%资源
    
    window.max_duration = min(estimated_duration, REVIEW_MAX_DURATION)
    window.target_data_count = min(pending_data, REVIEW_BATCH_SIZE)
    
    return window
```

## 4. 批量数据重放

### 4.1 数据采样策略

```python
def sample_data_for_review(all_data: List[Record], 
                          target_size: int) -> List[Record]:
    """为复盘采样数据"""
    # 策略1：高误差样本优先（学习价值高）
    high_error_samples = sorted(
        all_data, 
        key=lambda r: r.prediction_error if hasattr(r, 'prediction_error') else 0,
        reverse=True
    )[:target_size // 3]
    
    # 策略2：探索任务结果优先（新知价值高）
    exploration_samples = [
        r for r in all_data 
        if hasattr(r, 'is_exploration') and r.is_exploration
    ]
    exploration_samples = random.sample(
        exploration_samples, 
        min(len(exploration_samples), target_size // 3)
    )
    
    # 策略3：时间分层采样（覆盖不同时期）
    time_strata = stratify_by_time(all_data, n_strata=5)
    time_samples = []
    for stratum in time_strata:
        n_from_stratum = target_size // (3 * len(time_strata))
        time_samples.extend(random.sample(stratum, min(n_from_stratum, len(stratum))))
    
    # 合并并去重
    combined = list(set(high_error_samples + exploration_samples + time_samples))
    
    # 补充至目标大小
    if len(combined) < target_size:
        remaining = [r for r in all_data if r not in combined]
        combined.extend(random.sample(remaining, target_size - len(combined)))
    
    return combined[:target_size]
```

### 4.2 批量预测验证

```python
def batch_prediction_review(data: List[PerceptionRecord], 
                           predictor: MultiLayerPredictor) -> ReviewResult:
    """批量验证历史预测"""
    results = ReviewResult()
    
    for record in data:
        # 获取历史预测
        historical_prediction = record.associated_prediction
        
        # 使用当前模型重新预测
        current_prediction = predictor.predict(
            state_history=record.state_history,
            horizon=historical_prediction.horizon,
            level=historical_prediction.level
        )
        
        # 比较预测改进
        old_error = calculate_error(historical_prediction, record.actual_values)
        new_error = calculate_error(current_prediction, record.actual_values)
        
        results.prediction_improvements.append({
            'timestamp': record.timestamp,
            'old_error': old_error,
            'new_error': new_error,
            'improvement': old_error - new_error
        })
    
    # 统计整体改进
    results.avg_improvement = mean([r['improvement'] for r in results.prediction_improvements])
    results.improvement_rate = sum(1 for r in results.prediction_improvements if r['improvement'] > 0) / len(results.prediction_improvements)
    
    return results
```

### 4.3 批量模型训练

```python
def batch_model_training(data: List[TrainingSample],
                        models: List[PredictionModel]) -> TrainingResult:
    """批量训练模型"""
    result = TrainingResult()
    
    for model in models:
        # 准备训练数据
        model_specific_data = filter_data_for_model(data, model)
        
        if len(model_specific_data) < MIN_TRAINING_SAMPLES:
            continue
        
        # 划分训练/验证集
        train_data, val_data = train_test_split(model_specific_data, test_size=0.2)
        
        # 训练前评估
        pre_error = evaluate_model(model, val_data)
        
        # 批量训练
        model.train(train_data, epochs=BATCH_TRAIN_EPOCHS, 
                   validation_data=val_data,
                   early_stopping_patience=BATCH_TRAIN_PATIENCE)
        
        # 训练后评估
        post_error = evaluate_model(model, val_data)
        
        result.model_results.append({
            'model_id': model.id,
            'pre_error': pre_error,
            'post_error': post_error,
            'improvement': pre_error - post_error,
            'training_samples': len(train_data)
        })
    
    return result
```

## 5. 知识压缩与提炼

### 5.1 冗余信息识别

```python
def identify_redundant_information(memory_system: MemorySystem) -> RedundancyReport:
    """识别冗余信息"""
    report = RedundancyReport()
    
    # 1. 识别重复状态记录
    duplicate_states = find_duplicate_states(memory_system.perception_buffer)
    report.duplicate_states = duplicate_states
    
    # 2. 识别低价值预测记录
    low_value_predictions = [
        p for p in memory_system.prediction_buffer
        if p.error < LOW_ERROR_THRESHOLD and p.is_exploration == False
    ]
    report.low_value_predictions = low_value_predictions
    
    # 3. 识别过期规则
    expired_rules = [
        r for r in memory_system.rule_base
        if r.current_confidence < RULE_EXPIRE_THRESHOLD or r.age > RULE_MAX_AGE
    ]
    report.expired_rules = expired_rules
    
    # 4. 识别休眠模型
    dormant_models = [
        m for m in memory_system.models
        if m.last_use > MODEL_DORMANT_THRESHOLD
    ]
    report.dormant_models = dormant_models
    
    return report
```

### 5.2 知识压缩执行

```python
def compress_knowledge(report: RedundancyReport, 
                      memory_system: MemorySystem) -> CompressionResult:
    """执行知识压缩"""
    result = CompressionResult()
    
    # 1. 删除重复状态（保留最新）
    for dup_group in report.duplicate_states:
        keep = max(dup_group, key=lambda r: r.timestamp)
        to_remove = [r for r in dup_group if r != keep]
        memory_system.remove_perceptions(to_remove)
        result.space_freed += sum(r.size for r in to_remove)
    
    # 2. 采样低价值预测（保留代表性样本）
    for pred in report.low_value_predictions:
        if should_keep_sample(pred, report.low_value_predictions):
            continue
        memory_system.remove_prediction(pred)
        result.space_freed += pred.size
    
    # 3. 淘汰过期规则
    for rule in report.expired_rules:
        memory_system.remove_rule(rule)
        result.rules_removed += 1
    
    # 4. 压缩休眠模型
    for model in report.dormant_models:
        compressed = compress_model(model)
        memory_system.replace_model(model, compressed)
        result.models_compressed += 1
    
    return result
```

### 5.3 核心知识提炼

```python
def distill_core_knowledge(memory_system: MemorySystem) -> KnowledgeDistillation:
    """提炼核心知识"""
    distillation = KnowledgeDistillation()
    
    # 1. 提炼关键状态模式
    all_states = memory_system.get_all_states()
    distillation.key_patterns = extract_recurring_patterns(all_states)
    
    # 2. 提炼因果知识
    causal_relations = discover_causal_relations(all_states)
    distillation.causal_graph = build_causal_graph(causal_relations)
    
    # 3. 提炼决策经验
    decision_history = memory_system.get_decision_history()
    distillation.decision_rules = extract_decision_rules(decision_history)
    
    # 4. 提炼预测知识
    prediction_history = memory_system.get_prediction_history()
    distillation.prediction_insights = extract_prediction_insights(prediction_history)
    
    return distillation
```

## 6. 复盘效果评估

### 6.1 效果指标定义

```python
@dataclass
class ReviewEffectiveness:
    # 预测精度提升
    prediction_improvement: float
    
    # 认知覆盖度提升
    coverage_improvement: float
    
    # 能效优化
    efficiency_improvement: float
    
    # 知识压缩率
    compression_ratio: float
    
    # 资源投入
    resource_cost: ResourceUsage
    
    # 投入产出比
    roi: float
```

### 6.2 效果评估方法

```python
def evaluate_review_effectiveness(pre_state: SystemState,
                                 post_state: SystemState,
                                 review_cost: ResourceUsage) -> ReviewEffectiveness:
    """评估复盘效果"""
    effectiveness = ReviewEffectiveness()
    
    # 预测精度提升
    effectiveness.prediction_improvement = (
        pre_state.avg_prediction_error - post_state.avg_prediction_error
    ) / pre_state.avg_prediction_error
    
    # 认知覆盖度提升
    effectiveness.coverage_improvement = (
        post_state.cognitive_coverage - pre_state.cognitive_coverage
    )
    
    # 能效优化
    effectiveness.efficiency_improvement = (
        pre_state.resource_efficiency - post_state.resource_efficiency
    ) / pre_state.resource_efficiency
    
    # 知识压缩率
    effectiveness.compression_ratio = (
        pre_state.storage_size - post_state.storage_size
    ) / pre_state.storage_size
    
    # 资源投入
    effectiveness.resource_cost = review_cost
    
    # 投入产出比
    total_improvement = (effectiveness.prediction_improvement + 
                        effectiveness.coverage_improvement + 
                        effectiveness.efficiency_improvement)
    effectiveness.roi = total_improvement / (review_cost.cpu + review_cost.memory)
    
    return effectiveness
```

### 6.3 复盘策略进化

```python
def evolve_review_strategy(review_history: List[ReviewRecord]) -> ReviewStrategy:
    """基于历史复盘效果进化复盘策略"""
    strategy = ReviewStrategy()
    
    # 分析哪种数据采样策略效果最好
    sampling_performance = {}
    for record in review_history:
        strategy_name = record.sampling_strategy
        if strategy_name not in sampling_performance:
            sampling_performance[strategy_name] = []
        sampling_performance[strategy_name].append(record.effectiveness.roi)
    
    best_sampling = max(sampling_performance, 
                       key=lambda s: mean(sampling_performance[s]))
    strategy.sampling_strategy = best_sampling
    
    # 分析最佳复盘频率
    frequency_performance = analyze_frequency_vs_performance(review_history)
    strategy.optimal_frequency = find_best_frequency(frequency_performance)
    
    # 分析最佳复盘数据量
    data_size_performance = analyze_data_size_vs_performance(review_history)
    strategy.optimal_batch_size = find_best_batch_size(data_size_performance)
    
    return strategy
```

## 7. 复盘执行流程

### 7.1 完整复盘流程

```python
class OfflineReview:
    def execute_review(self) -> ReviewResult:
        """执行完整复盘流程"""
        result = ReviewResult()
        result.start_time = datetime.now()
        
        # 1. 保存当前状态
        pre_state = self.capture_system_state()
        
        # 2. 数据准备
        unprocessed_data = self.memory.get_unprocessed_data()
        review_data = sample_data_for_review(unprocessed_data, REVIEW_BATCH_SIZE)
        
        # 3. 批量预测验证
        prediction_result = batch_prediction_review(review_data, self.predictor)
        result.prediction_review = prediction_result
        
        # 4. 批量模型训练
        training_result = batch_model_training(review_data, self.predictor.models)
        result.model_training = training_result
        
        # 5. 知识压缩
        redundancy_report = identify_redundant_information(self.memory)
        compression_result = compress_knowledge(redundancy_report, self.memory)
        result.compression = compression_result
        
        # 6. 核心知识提炼
        distilled_knowledge = distill_core_knowledge(self.memory)
        result.distilled_knowledge = distilled_knowledge
        
        # 7. 效果评估
        post_state = self.capture_system_state()
        review_cost = self.calculate_resource_cost(result.start_time)
        effectiveness = evaluate_review_effectiveness(pre_state, post_state, review_cost)
        result.effectiveness = effectiveness
        
        # 8. 记录复盘结果
        self.memory.record_review(result)
        
        # 9. 更新复盘策略
        review_history = self.memory.get_review_history()
        self.review_strategy = evolve_review_strategy(review_history)
        
        result.end_time = datetime.now()
        return result
```

### 7.2 资源隔离机制

```python
def execute_with_resource_limit(task: Callable, 
                               cpu_limit: float,
                               memory_limit: float) -> Any:
    """在资源限制下执行任务"""
    # 设置进程资源限制（Linux）
    if platform.system() == 'Linux':
        import resource
        
        # CPU时间限制（软限制）
        soft_cpu_limit = cpu_limit * 3600  # 转换为秒
        resource.setrlimit(resource.RLIMIT_CPU, (soft_cpu_limit, soft_cpu_limit + 60))
        
        # 内存限制
        mem_bytes = int(memory_limit * 1024 * 1024 * 1024)
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    
    # 使用nice降低优先级
    os.nice(10)
    
    try:
        return task()
    except resource.error as e:
        # 资源超限，优雅退出
        return None
```

## 8. 接口定义

### 8.1 对外接口

```python
class OfflineReviewModule:
    def __init__(self, config: ReviewConfig):
        """初始化离线复盘模块"""
        pass
    
    def check_review_needed(self, state_vector: StateVector) -> bool:
        """检查是否需要复盘"""
        pass
    
    def execute_review(self) -> ReviewResult:
        """执行复盘"""
        pass
    
    def get_review_history(self) -> List[ReviewRecord]:
        """获取复盘历史"""
        pass
    
    def get_review_strategy(self) -> ReviewStrategy:
        """获取当前复盘策略"""
        pass
    
    def get_effectiveness_trend(self) -> List[ReviewEffectiveness]:
        """获取效果趋势"""
        pass
```

### 8.2 配置参数

```python
@dataclass
class ReviewConfig:
    # 触发配置
    idle_cpu_threshold: float = 0.3
    idle_mem_threshold: float = 0.5
    idle_check_window: int = 60
    idle_gap_variance_threshold: float = 0.01
    review_min_interval: timedelta = timedelta(hours=4)
    review_max_interval: timedelta = timedelta(hours=24)
    review_data_threshold: int = 10000
    review_performance_threshold: float = 0.7
    
    # 窗口配置
    review_max_duration: timedelta = timedelta(hours=2)
    review_batch_size: int = 5000
    
    # 训练配置
    batch_train_epochs: int = 50
    batch_train_patience: int = 10
    min_training_samples: int = 100
    
    # 压缩配置
    low_error_threshold: float = 0.01
    rule_expire_threshold: float = 0.3
    rule_max_age: int = 1000
    model_dormant_threshold: timedelta = timedelta(days=7)
    
    # 资源限制
    review_cpu_limit: float = 0.5
    review_memory_limit: float = 2.0  # GB
```

## 9. 测试与验证

### 9.1 单元测试

1. 空闲检测逻辑测试
2. 数据采样策略测试
3. 知识压缩效果测试
4. 效果评估准确性测试

### 9.2 集成测试

1. 完整复盘流程测试
2. 资源隔离效果测试
3. 复盘后系统一致性测试
4. 长时间运行的复盘稳定性测试

### 9.3 效果验证

1. 复盘前后预测精度对比
2. 复盘策略进化效果验证
3. 知识压缩率统计

---

离线批量复盘模块作为Agent系统的"睡眠学习"机制，其设计质量直接决定了Agent能否在离线时段持续积累认知优势、压缩冗余信息、提炼核心知识。通过智能的触发机制、高效的批量处理和持续的策略进化，确保Agent的每一次"睡眠"都能带来可量化的认知提升。
