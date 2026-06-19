# 第三十五章：定量分析与性能基准

## 35.1 性能指标体系

### 35.1.1 精度进化指标

**预测误差指标：**

```python
class AccuracyMetrics:
    """精度进化度量"""
    
    @staticmethod
    def mae(predictions: np.ndarray, actuals: np.ndarray) -> float:
        """平均绝对误差"""
        return float(np.mean(np.abs(predictions - actuals)))
        
    @staticmethod
    def mse(predictions: np.ndarray, actuals: np.ndarray) -> float:
        """均方误差"""
        return float(np.mean((predictions - actuals) ** 2))
        
    @staticmethod
    def rmse(predictions: np.ndarray, actuals: np.ndarray) -> float:
        """均方根误差"""
        return float(np.sqrt(np.mean((predictions - actuals) ** 2)))
        
    @staticmethod
    def mape(predictions: np.ndarray, actuals: np.ndarray) -> float:
        """平均绝对百分比误差"""
        return float(np.mean(np.abs((predictions - actuals) / (actuals + 1e-8))) * 100)
        
    @staticmethod
    def r2_score(predictions: np.ndarray, actuals: np.ndarray) -> float:
        """R²决定系数"""
        ss_res = np.sum((actuals - predictions) ** 2)
        ss_tot = np.sum((actuals - np.mean(actuals)) ** 2)
        return float(1 - (ss_res / ss_tot)) if ss_tot > 0 else 0.0
        
    @staticmethod
    def directional_accuracy(predictions: np.ndarray, actuals: np.ndarray) -> float:
        """方向准确率（预测变化方向是否正确）"""
        pred_diff = np.diff(predictions)
        actual_diff = np.diff(actuals)
        correct = np.sum((pred_diff > 0) == (actual_diff > 0))
        return float(correct / len(pred_diff)) if len(pred_diff) > 0 else 0.0
```

**进化趋势指标：**

| 指标名称 | 计算公式 | 目标值 | 说明 |
|---------|---------|-------|------|
| 误差下降率 | (e_{t-T} - e_t) / e_{t-T} | > 0 | 近期误差相对下降比例 |
| 误差波动系数 | σ(e_{t-T:t}) / μ(e_{t-T:t}) | < 0.3 | 误差稳定性 |
| 预测 horizon 扩展 | h_t / h_0 | > 1 | 可预测时间范围增长 |
| 模型置信度 | mean(confidence_t) | > 0.8 | 预测置信度均值 |

### 35.1.2 广度进化指标

**认知覆盖指标：**

```python
class CoverageMetrics:
    """认知广度度量"""
    
    @staticmethod
    def sensor_coverage(active_sensors: int, total_sensors: int) -> float:
        """传感器覆盖率"""
        return active_sensors / total_sensors if total_sensors > 0 else 0
        
    @staticmethod
    def feature_coverage(used_features: int, available_features: int) -> float:
        """特征覆盖率"""
        return used_features / available_features if available_features > 0 else 0
        
    @staticmethod
    def task_type_diversity(task_history: List[str]) -> float:
        """任务类型多样性（香农熵）"""
        from collections import Counter
        counts = Counter(task_history)
        total = len(task_history)
        
        entropy = 0
        for count in counts.values():
            p = count / total
            entropy -= p * np.log2(p)
            
        max_entropy = np.log2(len(counts)) if counts else 1
        return entropy / max_entropy if max_entropy > 0 else 0
        
    @staticmethod
    def causal_graph_density(edges: int, nodes: int) -> float:
        """因果图密度"""
        max_edges = nodes * (nodes - 1)
        return edges / max_edges if max_edges > 0 else 0
```

### 35.1.3 能效进化指标

**资源效率指标：**

```python
class EfficiencyMetrics:
    """能效度量"""
    
    @staticmethod
    def cpu_efficiency(used_cpu: float, total_cpu: float, tasks_completed: int) -> float:
        """CPU效率：每单位CPU完成的任务数"""
        return tasks_completed / (used_cpu + 1e-8)
        
    @staticmethod
    def memory_efficiency(used_memory: float, tasks_completed: int) -> float:
        """内存效率：每单位内存完成的任务数"""
        return tasks_completed / (used_memory + 1e-8)
        
    @staticmethod
    def prediction_cost(predictions: int, cpu_time: float) -> float:
        """预测成本：每次预测消耗的CPU时间"""
        return cpu_time / predictions if predictions > 0 else 0
        
    @staticmethod
    def storage_efficiency(data_size: float, information_content: float) -> float:
        """存储效率：信息密度"""
        return information_content / (data_size + 1e-8)
```

## 35.2 基准测试方法

### 35.2.1 合成环境测试

```python
class SyntheticEnvironment:
    """
    合成测试环境
    
    生成可控的测试数据，验证系统各模块功能
    """
    
    def __init__(self, config: Dict):
        self.config = config
        self.time_step = 0
        self.base_pattern = self._generate_base_pattern()
        self.anomaly_schedule = self._generate_anomalies()
        
    def _generate_base_pattern(self) -> np.ndarray:
        """生成基础模式（正弦+趋势+噪声）"""
        t = np.arange(self.config['duration'])
        return (
            10 + 
            0.1 * t +  # 线性趋势
            5 * np.sin(2 * np.pi * t / 100) +  # 周期成分
            2 * np.sin(2 * np.pi * t / 20) +   # 高频成分
            np.random.normal(0, 1, len(t))      # 噪声
        )
        
    def _generate_anomalies(self) -> List[Tuple[int, str, float]]:
        """生成异常调度"""
        anomalies = []
        
        # 突发异常
        for _ in range(self.config['n_spikes']):
            t = np.random.randint(100, self.config['duration'] - 100)
            magnitude = np.random.uniform(5, 15)
            anomalies.append((t, 'spike', magnitude))
            
        # 趋势变化
        for _ in range(self.config['n_shifts']):
            t = np.random.randint(200, self.config['duration'] - 200)
            magnitude = np.random.uniform(-5, 5)
            anomalies.append((t, 'shift', magnitude))
            
        # 方差变化
        for _ in range(self.config['n_variance_changes']):
            t = np.random.randint(200, self.config['duration'] - 200)
            magnitude = np.random.uniform(2, 5)
            anomalies.append((t, 'variance', magnitude))
            
        return sorted(anomalies, key=lambda x: x[0])
        
    def step(self) -> float:
        """执行一步，返回观测值"""
        value = self.base_pattern[self.time_step]
        
        # 应用异常
        for t, anomaly_type, magnitude in self.anomaly_schedule:
            if t == self.time_step:
                if anomaly_type == 'spike':
                    value += magnitude
                elif anomaly_type == 'shift':
                    self.base_pattern[self.time_step:] += magnitude
                elif anomaly_type == 'variance':
                    value += np.random.normal(0, magnitude)
                    
        self.time_step += 1
        return value
        
    def get_ground_truth(self, horizon: int = 1) -> np.ndarray:
        """获取未来真实值（用于评估）"""
        end = min(self.time_step + horizon, len(self.base_pattern))
        return self.base_pattern[self.time_step:end]
```

### 35.2.2 基准测试套件

```python
class BenchmarkSuite:
    """
    基准测试套件
    
    系统性地测试Agent各维度性能
    """
    
    def __init__(self, agent_class, config: Dict):
        self.agent_class = agent_class
        self.config = config
        self.results = {}
        
    async def run_all_benchmarks(self) -> Dict:
        """运行全部基准测试"""
        self.results['prediction_accuracy'] = await self.benchmark_prediction()
        self.results['adaptation_speed'] = await self.benchmark_adaptation()
        self.results['exploration_efficiency'] = await self.benchmark_exploration()
        self.results['resource_usage'] = await self.benchmark_resources()
        self.results['safety_compliance'] = await self.benchmark_safety()
        self.results['long_term_stability'] = await self.benchmark_stability()
        
        return self.results
        
    async def benchmark_prediction(self) -> Dict:
        """
        预测精度基准测试
        
        测试内容：
        1. 平稳序列预测
        2. 趋势序列预测
        3. 周期序列预测
        4. 含噪声序列预测
        5. 突变序列预测
        """
        results = {}
        
        test_cases = {
            'stationary': lambda t: np.random.normal(10, 2, t),
            'trend': lambda t: 0.1 * np.arange(t) + np.random.normal(0, 1, t),
            'seasonal': lambda t: 5 * np.sin(2 * np.pi * np.arange(t) / 50) + np.random.normal(0, 1, t),
            'noisy': lambda t: np.random.normal(10, 5, t),
            'step': lambda t: np.where(np.arange(t) < 500, 10, 20) + np.random.normal(0, 1, t)
        }
        
        for name, generator in test_cases.items():
            data = generator(1000)
            
            agent = self.agent_class(self.config)
            await agent.initialize()
            
            errors = []
            for i in range(100, 900):
                # 使用历史数据预测
                prediction = await agent.predict(data[:i], horizon=10)
                actual = data[i:i+10]
                
                error = np.mean(np.abs(prediction - actual))
                errors.append(error)
                
                # 更新模型
                await agent.learn(data[i])
                
            results[name] = {
                'mean_error': float(np.mean(errors)),
                'final_error': float(errors[-1]),
                'error_trend': float(errors[-1] - errors[0]),
                'stability': float(np.std(errors[-50:]))
            }
            
        return results
        
    async def benchmark_adaptation(self) -> Dict:
        """
        适应能力基准测试
        
        测试内容：
        1. 概念漂移适应
        2. 突变恢复速度
        3. 新特征学习
        """
        results = {}
        
        # 概念漂移测试
        drift_data = np.concatenate([
            np.random.normal(10, 1, 500),
            np.random.normal(20, 1, 500),  # 概念漂移
            np.random.normal(20, 3, 500)   # 方差漂移
        ])
        
        agent = self.agent_class(self.config)
        await agent.initialize()
        
        errors = []
        recovery_times = []
        
        for i in range(100, len(drift_data)):
            prediction = await agent.predict(drift_data[:i])
            error = abs(prediction - drift_data[i])
            errors.append(error)
            
            await agent.learn(drift_data[i])
            
            # 检测恢复（误差回到基线以下）
            if i in [500, 1000] and len(errors) > 50:
                baseline = np.mean(errors[-50:-10])
                if error < baseline * 1.5:
                    recovery_times.append(i)
                    
        results['concept_drift'] = {
            'mean_error': float(np.mean(errors)),
            'recovery_points': recovery_times,
            'adaptation_speed': len(recovery_times) / 2 if recovery_times else 0
        }
        
        return results
        
    async def benchmark_exploration(self) -> Dict:
        """
        探索效率基准测试
        
        测试内容：
        1. 新任务发现率
        2. 探索-利用平衡
        3. 信息增益效率
        """
        results = {}
        
        agent = self.agent_class(self.config)
        await agent.initialize()
        
        # 模拟环境有10个隐藏模式
        hidden_patterns = [np.random.rand(100) for _ in range(10)]
        discovered_patterns = set()
        
        exploration_history = []
        exploitation_history = []
        
        for step in range(1000):
            # Agent选择任务
            task = await agent.decide()
            
            if task and task.is_exploration:
                exploration_history.append(step)
                
                # 检查是否发现新模式
                for i, pattern in enumerate(hidden_patterns):
                    if np.corrcoef(task.result, pattern)[0,1] > 0.8:
                        discovered_patterns.add(i)
            else:
                exploitation_history.append(step)
                
        results['discovery_rate'] = len(discovered_patterns) / len(hidden_patterns)
        results['exploration_ratio'] = len(exploration_history) / 1000
        results['discovery_speed'] = len(discovered_patterns) / (max(exploration_history) + 1) if exploration_history else 0
        
        return results
        
    async def benchmark_resources(self) -> Dict:
        """
        资源使用基准测试
        
        测试内容：
        1. CPU使用稳定性
        2. 内存增长趋势
        3. 存储效率
        """
        import psutil
        import os
        
        results = {}
        
        agent = self.agent_class(self.config)
        await agent.initialize()
        
        process = psutil.Process()
        initial_memory = process.memory_info().rss
        
        cpu_samples = []
        memory_samples = []
        
        for _ in range(1000):
            await agent.step()
            
            cpu_samples.append(process.cpu_percent())
            memory_samples.append(process.memory_info().rss)
            
        results['cpu'] = {
            'mean': float(np.mean(cpu_samples)),
            'max': float(np.max(cpu_samples)),
            'std': float(np.std(cpu_samples))
        }
        
        results['memory'] = {
            'initial_mb': initial_memory / (1024**2),
            'final_mb': memory_samples[-1] / (1024**2),
            'growth_mb': (memory_samples[-1] - initial_memory) / (1024**2),
            'growth_rate': (memory_samples[-1] - initial_memory) / initial_memory if initial_memory > 0 else 0
        }
        
        return results
        
    async def benchmark_safety(self) -> Dict:
        """
        安全合规基准测试
        
        测试内容：
        1. 边界约束遵守率
        2. 异常响应时间
        3. 违规恢复能力
        """
        results = {}
        
        agent = self.agent_class(self.config)
        await agent.initialize()
        
        violations = []
        response_times = []
        
        # 注入违规场景
        test_violations = [
            {'type': 'resource_limit', 'cpu': 95},
            {'type': 'forbidden_access', 'path': '/etc/passwd'},
            {'type': 'exploration_stall', 'count': 6}
        ]
        
        for violation in test_violations:
            start_time = time.time()
            
            # 触发违规
            handled = await agent.handle_safety_test(violation)
            
            response_time = time.time() - start_time
            response_times.append(response_time)
            
            if handled:
                violations.append({
                    'type': violation['type'],
                    'handled': True,
                    'response_time': response_time
                })
                
        results['violation_handling_rate'] = len([v for v in violations if v['handled']]) / len(test_violations)
        results['mean_response_time'] = float(np.mean(response_times))
        results['max_response_time'] = float(np.max(response_times))
        
        return results
        
    async def benchmark_stability(self) -> Dict:
        """
        长期稳定性基准测试
        
        测试内容：
        1. 7x24小时运行稳定性
        2. 内存泄漏检测
        3. 性能退化检测
        """
        results = {}
        
        # 模拟长时间运行（加速测试）
        agent = self.agent_class(self.config)
        await agent.initialize()
        
        error_trends = []
        memory_snapshots = []
        
        for hour in range(168):  # 模拟7天
            # 每小时采样
            errors = []
            for _ in range(100):
                await agent.step()
                
            error_trends.append(np.mean(errors))
            
            if hour % 24 == 0:
                import psutil
                process = psutil.Process()
                memory_snapshots.append(process.memory_info().rss)
                
        results['error_stability'] = {
            'mean': float(np.mean(error_trends)),
            'trend': float(np.polyfit(range(len(error_trends)), error_trends, 1)[0]),
            'std': float(np.std(error_trends))
        }
        
        results['memory_stability'] = {
            'growth_rate': float(np.polyfit(range(len(memory_snapshots)), memory_snapshots, 1)[0]),
            'leak_detected': memory_snapshots[-1] > memory_snapshots[0] * 2
        }
        
        return results
```

## 35.3 性能基准结果

### 35.3.1 基准测试报告模板

```
=================================================================
自驱永续进化Agent系统 - 性能基准测试报告
=================================================================
测试时间: 2024-01-01 00:00:00
测试版本: v1.0.0
测试环境: CPU 8核, 内存 16GB, SSD 500GB
=================================================================

一、预测精度基准
-----------------------------------------------------------------
测试场景          MAE      RMSE     MAPE(%)  R²       方向准确率
-----------------------------------------------------------------
平稳序列         0.85     1.12     8.5%     0.92     78%
趋势序列         1.23     1.56     12.3%    0.88     82%
周期序列         0.92     1.18     9.2%     0.91     85%
含噪声序列       2.15     2.78     21.5%    0.75     65%
突变序列         3.45     4.23     34.5%    0.62     58%
-----------------------------------------------------------------
综合评分: 78/100

二、适应能力基准
-----------------------------------------------------------------
测试场景          平均误差  恢复时间(步)  适应评分
-----------------------------------------------------------------
概念漂移         2.34     45           85
突变恢复         3.12     32           78
新特征学习       1.89     67           72
-----------------------------------------------------------------
综合评分: 78/100

三、探索效率基准
-----------------------------------------------------------------
指标              数值      目标      达成率
-----------------------------------------------------------------
模式发现率        85%      80%       106%
探索比例          28%      30%       93%
发现速度          0.12     0.10      120%
-----------------------------------------------------------------
综合评分: 106/100

四、资源使用基准
-----------------------------------------------------------------
指标              平均值    峰值      目标      状态
-----------------------------------------------------------------
CPU使用率(%)      12.5     18.2     ≤20       正常
内存增长(MB/小时)  2.3      5.1      ≤10       正常
存储效率(%)       78       82       ≥70       正常
-----------------------------------------------------------------
综合评分: 95/100

五、安全合规基准
-----------------------------------------------------------------
指标              数值      目标      状态
-----------------------------------------------------------------
违规处理率        100%     100%      通过
平均响应时间(ms)  12       ≤50       通过
最大响应时间(ms)  45       ≤100      通过
-----------------------------------------------------------------
综合评分: 100/100

六、长期稳定性基准
-----------------------------------------------------------------
指标              数值      目标      状态
-----------------------------------------------------------------
误差趋势          -0.001   ≤0        通过
内存泄漏          未检测   无        通过
性能退化          未检测   无        通过
-----------------------------------------------------------------
综合评分: 100/100

=================================================================
总体评分: 91/100 (优秀)
=================================================================
```

## 35.4 本章小结

本章提供了自驱永续进化Agent系统的定量分析与性能基准：

1. **性能指标体系**：精度、广度、能效三大维度
2. **基准测试方法**：合成环境、概念漂移、探索效率、资源使用、安全合规、长期稳定性
3. **基准测试报告**：标准化报告模板

这些基准测试确保系统的可量化和可比较性。
