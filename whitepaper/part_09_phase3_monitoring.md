# 第三阶段：永续进化闭环 —— 全维度进化指标监控模块详细技术方案

## 1. 模块概述

全维度进化指标监控模块是整个自驱永续进化Agent系统的"自我意识"层，负责实时监控和评估Agent在精度进化、广度进化、能效进化三个终极维度上的进展。本模块通过建立全面的指标体系、可视化看板和趋势分析，为Agent的自主进化提供量化的反馈信号，同时为人工观察Agent进化状态提供窗口。

## 2. 设计目标

1. 三维监控：同时监控精度、广度、能效三大进化维度
2. 趋势分析：识别长期趋势，预测进化方向
3. 异常告警：进化停滞或退化时自动告警
4. 可视化输出：提供人类可读的进化状态报告
5. 闭环反馈：监控结果反馈到驱力计算，形成进化闭环

## 3. 精度进化指标体系

### 3.1 预测误差趋势

#### 3.1.1 全局预测误差指数

```python
def calculate_global_error_index(prediction_history: List[PredictionRecord]) -> float:
    """计算全局预测误差指数"""
    # 加权平均各模型的误差
    model_errors = {}
    for record in prediction_history:
        model_id = record.model_id
        if model_id not in model_errors:
            model_errors[model_id] = []
        model_errors[model_id].append(record.mse)
    
    # 计算各模型的近期平均误差
    recent_errors = []
    for model_id, errors in model_errors.items():
        recent_avg = mean(errors[-ERROR_TREND_WINDOW:])
        model_weight = get_model_importance(model_id)
        recent_errors.append(recent_avg * model_weight)
    
    global_error = sum(recent_errors) / sum(get_model_importance(m) for m in model_errors)
    
    # 归一化到[0, 1]，0表示完美预测，1表示最差
    return min(global_error / BASELINE_ERROR, 1.0)
```

#### 3.1.2 误差下降速率

```python
def calculate_error_decline_rate(error_history: List[float]) -> float:
    """计算误差下降速率"""
    if len(error_history) < DECLINE_RATE_WINDOW * 2:
        return 0.0
    
    recent_avg = mean(error_history[-DECLINE_RATE_WINDOW:])
    previous_avg = mean(error_history[-DECLINE_RATE_WINDOW*2:-DECLINE_RATE_WINDOW])
    
    if previous_avg == 0:
        return 0.0
    
    decline_rate = (previous_avg - recent_avg) / previous_avg
    return decline_rate
```

#### 3.1.3 预测方向准确率

```python
def calculate_direction_accuracy(prediction_history: List[PredictionRecord]) -> float:
    """计算预测方向准确率"""
    correct_directions = 0
    total = 0
    
    for record in prediction_history:
        if record.actual_values is None:
            continue
        
        pred_diff = np.diff(record.prediction_values)
        actual_diff = np.diff(record.actual_values)
        
        correct = np.sum(np.sign(pred_diff) == np.sign(actual_diff))
        total += len(pred_diff)
        correct_directions += correct
    
    return correct_directions / total if total > 0 else 0.0
```

### 3.2 精度进化综合评分

```python
def calculate_precision_evolution_score(metrics: PrecisionMetrics) -> float:
    """计算精度进化综合评分"""
    # 误差指数（越低越好，需要反转）
    error_score = 1 - metrics.global_error_index
    
    # 下降速率（正值表示在进化）
    decline_score = max(0, metrics.error_decline_rate) * DECLINE_RATE_WEIGHT
    
    # 方向准确率
    direction_score = metrics.direction_accuracy
    
    # 综合评分
    precision_score = (
        error_score * 0.5 +
        decline_score * 0.3 +
        direction_score * 0.2
    )
    
    return precision_score
```

## 4. 广度进化指标体系

### 4.1 认知覆盖度

#### 4.1.1 维度覆盖度

```python
def calculate_dimension_coverage(monitored_dimensions: Set[str],
                                total_dimensions: Set[str]) -> float:
    """计算维度覆盖度"""
    if not total_dimensions:
        return 0.0
    
    return len(monitored_dimensions) / len(total_dimensions)
```

#### 4.1.2 模式识别覆盖度

```python
def calculate_pattern_coverage(recognized_patterns: Set[str],
                              total_patterns: Set[str]) -> float:
    """计算模式识别覆盖度"""
    if not total_patterns:
        return 0.0
    
    return len(recognized_patterns) / len(total_patterns)
```

#### 4.1.3 因果关联覆盖度

```python
def calculate_causal_coverage(known_relations: Set[Tuple],
                             total_possible_relations: int) -> float:
    """计算因果关联覆盖度"""
    if total_possible_relations == 0:
        return 0.0
    
    return len(known_relations) / total_possible_relations
```

### 4.2 新知发现率

```python
def calculate_discovery_rate(recent_history: List[Record],
                            time_window: timedelta) -> float:
    """计算新知发现率"""
    cutoff = datetime.now() - time_window
    
    new_dimensions = sum(1 for r in recent_history 
                        if r.timestamp > cutoff and r.is_new_dimension)
    new_patterns = sum(1 for r in recent_history 
                      if r.timestamp > cutoff and r.is_new_pattern)
    new_rules = sum(1 for r in recent_history 
                   if r.timestamp > cutoff and r.is_new_rule)
    
    # 归一化发现率
    discovery_rate = (new_dimensions + new_patterns + new_rules) / DISCOVERY_NORMALIZATION
    
    return min(discovery_rate, 1.0)
```

### 4.3 广度进化综合评分

```python
def calculate_breadth_evolution_score(metrics: BreadthMetrics) -> float:
    """计算广度进化综合评分"""
    # 覆盖度评分
    coverage_score = (
        metrics.dimension_coverage * 0.4 +
        metrics.pattern_coverage * 0.3 +
        metrics.causal_coverage * 0.3
    )
    
    # 发现率评分
    discovery_score = metrics.discovery_rate
    
    # 综合评分
    breadth_score = coverage_score * 0.6 + discovery_score * 0.4
    
    return breadth_score
```

## 5. 能效进化指标体系

### 5.1 资源效率

#### 5.1.1 CPU效率指数

```python
def calculate_cpu_efficiency(agent_cpu_usage: float,
                            useful_computation_ratio: float) -> float:
    """计算CPU效率指数"""
    # 理想状态：低CPU占用 + 高有效计算比例
    efficiency = useful_computation_ratio / max(agent_cpu_usage, 0.01)
    
    # 归一化
    return min(efficiency / CPU_EFFICIENCY_BASELINE, 1.0)
```

#### 5.1.2 内存效率指数

```python
def calculate_memory_efficiency(agent_memory_usage: float,
                               active_data_ratio: float) -> float:
    """计算内存效率指数"""
    efficiency = active_data_ratio / max(agent_memory_usage, 0.01)
    return min(efficiency / MEMORY_EFFICIENCY_BASELINE, 1.0)
```

#### 5.1.3 推理效率指数

```python
def calculate_inference_efficiency(prediction_accuracy: float,
                                  inference_time: float) -> float:
    """计算推理效率指数"""
    # 单位时间内的预测精度
    efficiency = prediction_accuracy / max(inference_time, 0.001)
    return min(efficiency / INFERENCE_EFFICIENCY_BASELINE, 1.0)
```

### 5.2 冗余度指标

```python
def calculate_redundancy_ratio(computation_history: List[ComputationRecord]) -> float:
    """计算冗余度比例"""
    total_computations = len(computation_history)
    redundant_computations = sum(1 for c in computation_history if c.is_redundant)
    
    return redundant_computations / total_computations if total_computations > 0 else 0.0
```

### 5.3 能效进化综合评分

```python
def calculate_efficiency_evolution_score(metrics: EfficiencyMetrics) -> float:
    """计算能效进化综合评分"""
    # 效率评分
    efficiency_score = (
        metrics.cpu_efficiency * 0.4 +
        metrics.memory_efficiency * 0.3 +
        metrics.inference_efficiency * 0.3
    )
    
    # 冗余度评分（冗余越低越好，需要反转）
    redundancy_score = 1 - metrics.redundancy_ratio
    
    # 综合评分
    efficiency_score = efficiency_score * 0.7 + redundancy_score * 0.3
    
    return efficiency_score
```

## 6. 综合进化仪表盘

### 6.1 三维进化雷达图

```python
def generate_evolution_radar(evolution_state: EvolutionState) -> Dict:
    """生成进化雷达图数据"""
    return {
        'dimensions': ['精度进化', '广度进化', '能效进化'],
        'current_scores': [
            evolution_state.precision_score,
            evolution_state.breadth_score,
            evolution_state.efficiency_score
        ],
        'historical_avg': [
            evolution_state.precision_history_avg,
            evolution_state.breadth_history_avg,
            evolution_state.efficiency_history_avg
        ],
        'targets': [1.0, 1.0, 1.0]  # 理论最优
    }
```

### 6.2 进化趋势图

```python
def generate_evolution_trends(history: List[EvolutionState]) -> Dict:
    """生成进化趋势数据"""
    return {
        'timestamps': [s.timestamp for s in history],
        'precision_trend': [s.precision_score for s in history],
        'breadth_trend': [s.breadth_score for s in history],
        'efficiency_trend': [s.efficiency_score for s in history],
        'overall_trend': [s.overall_score for s in history]
    }
```

### 6.3 进化状态报告

```python
def generate_evolution_report(current_state: EvolutionState,
                             history: List[EvolutionState]) -> str:
    """生成人类可读的进化状态报告"""
    report = []
    report.append("=" * 60)
    report.append("自驱永续进化Agent - 进化状态报告")
    report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("=" * 60)
    
    report.append("\n【三维进化评分】")
    report.append(f"  精度进化: {current_state.precision_score:.3f} / 1.000")
    report.append(f"  广度进化: {current_state.breadth_score:.3f} / 1.000")
    report.append(f"  能效进化: {current_state.efficiency_score:.3f} / 1.000")
    report.append(f"  综合评分: {current_state.overall_score:.3f} / 1.000")
    
    report.append("\n【进化趋势】")
    if len(history) >= 2:
        precision_trend = current_state.precision_score - history[-2].precision_score
        breadth_trend = current_state.breadth_score - history[-2].breadth_score
        efficiency_trend = current_state.efficiency_score - history[-2].efficiency_score
        
        report.append(f"  精度变化: {'+' if precision_trend >= 0 else ''}{precision_trend:.4f}")
        report.append(f"  广度变化: {'+' if breadth_trend >= 0 else ''}{breadth_trend:.4f}")
        report.append(f"  能效变化: {'+' if efficiency_trend >= 0 else ''}{efficiency_trend:.4f}")
    
    report.append("\n【关键指标】")
    report.append(f"  全局预测误差: {current_state.global_error:.4f}")
    report.append(f"  认知覆盖度: {current_state.coverage:.2%}")
    report.append(f"  资源使用效率: {current_state.resource_efficiency:.2%}")
    report.append(f"  探索-利用比例: {current_state.explore_exploit_ratio:.1%} / {1-current_state.explore_exploit_ratio:.1%}")
    
    report.append("\n【告警信息】")
    alerts = check_evolution_alerts(current_state, history)
    if alerts:
        for alert in alerts:
            report.append(f"  ⚠️  {alert}")
    else:
        report.append("  ✅ 无异常")
    
    report.append("\n" + "=" * 60)
    
    return "\n".join(report)
```

## 7. 进化异常检测

### 7.1 进化停滞检测

```python
def detect_evolution_stagnation(history: List[EvolutionState]) -> List[str]:
    """检测进化停滞"""
    alerts = []
    
    if len(history) < STAGNATION_DETECTION_WINDOW:
        return alerts
    
    recent = history[-STAGNATION_DETECTION_WINDOW:]
    
    # 精度停滞
    precision_values = [s.precision_score for s in recent]
    if max(precision_values) - min(precision_values) < STAGNATION_THRESHOLD:
        alerts.append("精度进化停滞：近期无显著提升")
    
    # 广度停滞
    breadth_values = [s.breadth_score for s in recent]
    if max(breadth_values) - min(breadth_values) < STAGNATION_THRESHOLD:
        alerts.append("广度进化停滞：近期无新发现")
    
    # 能效停滞
    efficiency_values = [s.efficiency_score for s in recent]
    if max(efficiency_values) - min(efficiency_values) < STAGNATION_THRESHOLD:
        alerts.append("能效进化停滞：资源优化无进展")
    
    return alerts
```

### 7.2 进化退化检测

```python
def detect_evolution_regression(history: List[EvolutionState]) -> List[str]:
    """检测进化退化"""
    alerts = []
    
    if len(history) < REGRESSION_DETECTION_WINDOW:
        return alerts
    
    recent = history[-REGRESSION_DETECTION_WINDOW:]
    baseline = history[-REGRESSION_DETECTION_WINDOW*2:-REGRESSION_DETECTION_WINDOW]
    
    # 精度退化
    recent_precision = mean([s.precision_score for s in recent])
    baseline_precision = mean([s.precision_score for s in baseline])
    if recent_precision < baseline_precision * (1 - REGRESSION_THRESHOLD):
        alerts.append(f"精度退化：近期{baseline_precision:.3f} → {recent_precision:.3f}")
    
    # 广度退化
    recent_breadth = mean([s.breadth_score for s in recent])
    baseline_breadth = mean([s.breadth_score for s in baseline])
    if recent_breadth < baseline_breadth * (1 - REGRESSION_THRESHOLD):
        alerts.append(f"广度退化：近期{baseline_breadth:.3f} → {recent_breadth:.3f}")
    
    # 能效退化
    recent_efficiency = mean([s.efficiency_score for s in recent])
    baseline_efficiency = mean([s.efficiency_score for s in baseline])
    if recent_efficiency < baseline_efficiency * (1 - REGRESSION_THRESHOLD):
        alerts.append(f"能效退化：近期{baseline_efficiency:.3f} → {recent_efficiency:.3f}")
    
    return alerts
```

### 7.3 自动响应机制

```python
def auto_respond_to_alerts(alerts: List[str], current_state: EvolutionState):
    """对进化异常自动响应"""
    for alert in alerts:
        if "精度退化" in alert:
            # 提升收益驱力权重，增加探索
            current_state.drive_weights['gain'] = min(
                current_state.drive_weights['gain'] * 1.2, 0.6
            )
            
        elif "广度停滞" in alert:
            # 增加维度探索任务生成
            current_state.exploration_boost = True
            
        elif "能效退化" in alert:
            # 提升能效驱力权重
            current_state.drive_weights['eff'] = min(
                current_state.drive_weights['eff'] * 1.3, 0.6
            )
            
        elif "精度停滞" in alert:
            # 触发结构性重构
            current_state.trigger_reconstruction = True
```

## 8. 接口定义

### 8.1 对外接口

```python
class EvolutionMonitor:
    def __init__(self, config: MonitorConfig):
        """初始化进化监控模块"""
        pass
    
    def update_metrics(self, state_vector: StateVector,
                      drive_output: DriveOutput,
                      prediction_results: List[PredictionRecord],
                      task_results: List[TaskExecutionRecord]):
        """更新进化指标"""
        pass
    
    def get_current_state(self) -> EvolutionState:
        """获取当前进化状态"""
        pass
    
    def get_evolution_history(self, duration: timedelta) -> List[EvolutionState]:
        """获取进化历史"""
        pass
    
    def generate_report(self) -> str:
        """生成进化报告"""
        pass
    
    def check_alerts(self) -> List[str]:
        """检查进化告警"""
        pass
    
    def get_radar_data(self) -> Dict:
        """获取雷达图数据"""
        pass
    
    def get_trend_data(self) -> Dict:
        """获取趋势数据"""
        pass
```

### 8.2 配置参数

```python
@dataclass
class MonitorConfig:
    # 误差配置
    error_trend_window: int = 100
    decline_rate_window: int = 50
    baseline_error: float = 1.0
    
    # 覆盖度配置
    discovery_normalization: int = 100
    
    # 效率基线
    cpu_efficiency_baseline: float = 10.0
    memory_efficiency_baseline: float = 10.0
    inference_efficiency_baseline: float = 1000.0
    
    # 停滞检测
    stagnation_detection_window: int = 500
    stagnation_threshold: float = 0.01
    
    # 退化检测
    regression_detection_window: int = 200
    regression_threshold: float = 0.05
    
    # 报告配置
    report_interval: timedelta = timedelta(hours=1)
    history_retention: timedelta = timedelta(days=30)
```

## 9. 测试与验证

### 9.1 单元测试

1. 各进化指标计算正确性测试
2. 停滞/退化检测逻辑测试
3. 报告生成格式测试

### 9.2 集成测试

1. 长时间运行的指标稳定性测试
2. 告警触发准确性测试
3. 自动响应机制测试

### 9.3 可视化测试

1. 雷达图数据完整性测试
2. 趋势图数据连续性测试
3. 报告可读性验证

---

全维度进化指标监控模块作为Agent系统的"自我意识"，其设计质量直接决定了Agent能否准确感知自身的进化状态、及时发现进化异常、自动调整进化策略。通过三维综合监控、趋势分析和异常响应，确保Agent的永续进化始终在正确的轨道上。
