# 高级算法详解

## 1. 自适应指数平滑算法

### 1.1 算法原理

自适应指数平滑（Adaptive Exponential Smoothing, AES）是底层预测模型的核心算法。与传统指数平滑不同，AES能够根据预测误差动态调整平滑系数，使模型对突发变化更敏感，对稳态数据更稳定。

### 1.2 数学推导

#### 1.2.1 基础指数平滑

对于时间序列 {x_t}，简单指数平滑的递推公式为：

```
s_t = α × x_t + (1-α) × s_{t-1}
```

其中 s_t 为 t 时刻的平滑值，α ∈ (0,1) 为平滑系数。

#### 1.2.2 平滑系数自适应调整

定义预测误差 e_t = x_t - ŷ_t，其中 ŷ_t = s_{t-1}。

平滑系数的自适应调整基于误差的绝对值：

```
α_t = |e_t| / (|e_t| + |e_{t-1}|)
```

当当前误差远大于前次误差时，α_t → 1，模型快速响应变化；当误差稳定时，α_t → 0.5，模型保持稳定。

#### 1.2.3 边界约束

为防止极端值导致α越界，引入约束：

```
α_t = clip(α_t, α_min, α_max)
```

通常取 α_min = 0.05，α_max = 0.95。

### 1.3 多尺度自适应

#### 1.3.1 短期与长期自适应

维护两个平滑系数：

```
α_short：基于最近5个周期的误差调整
α_long：基于最近50个周期的误差调整

α_effective = w_short × α_short + w_long × α_long
```

#### 1.3.2 趋势检测自适应

当检测到趋势时，自动切换到Holt线性趋势法：

```
if |slope| > trend_threshold:
    use_holt_method()
else:
    use_simple_smoothing()
```

### 1.4 实现代码

```python
class AdaptiveExponentialSmoother:
    def __init__(self, alpha_min=0.05, alpha_max=0.95):
        self.alpha_min = alpha_min
        self.alpha_max = alpha_max
        self.s = None  # 平滑值
        self.prev_error = 0
        self.error_history = deque(maxlen=50)
    
    def update(self, x_t):
        if self.s is None:
            self.s = x_t
            return self.s
        
        # 计算预测误差
        prediction = self.s
        error = x_t - prediction
        
        # 自适应调整alpha
        if abs(self.prev_error) > 1e-10:
            alpha = abs(error) / (abs(error) + abs(self.prev_error))
            alpha = np.clip(alpha, self.alpha_min, self.alpha_max)
        else:
            alpha = 0.3  # 默认值
        
        # 更新平滑值
        self.s = alpha * x_t + (1 - alpha) * self.s
        
        # 更新误差历史
        self.prev_error = error
        self.error_history.append(error)
        
        return self.s
    
    def predict(self, h=1):
        return self.s if self.s is not None else 0
```

## 2. 在线LSTM增量学习算法

### 2.1 算法挑战

在线增量学习面临三个核心挑战：

1. **灾难性遗忘**：新数据训练导致旧知识丢失
2. **概念漂移**：数据分布随时间变化
3. **计算效率**：实时性要求限制训练时间

### 2.2 解决方案

#### 2.2.1 弹性权重巩固（EWC）简化版

为重要参数添加约束，防止其在新任务中大幅变化：

```
Loss_total = Loss_new + λ × Σ F_i × (θ_i - θ*_i)^2
```

其中 F_i 为Fisher信息矩阵的对角元素，表示参数的重要性。

#### 2.2.2 经验回放

维护一个经验缓冲区，训练时混合新数据和历史数据：

```python
class ExperienceReplay:
    def __init__(self, capacity=10000):
        self.buffer = deque(maxlen=capacity)
    
    def add(self, experience):
        self.buffer.append(experience)
    
    def sample(self, batch_size, new_data_ratio=0.5):
        n_new = int(batch_size * new_data_ratio)
        n_old = batch_size - n_new
        
        new_samples = self.buffer[-n_new:]
        old_indices = random.sample(range(len(self.buffer) - n_new), n_old)
        old_samples = [self.buffer[i] for i in old_indices]
        
        return new_samples + old_samples
```

#### 2.2.3 学习率调度

采用余弦退火学习率调度：

```
lr_t = lr_min + 0.5 × (lr_max - lr_min) × (1 + cos(π × t / T))
```

### 2.3 实现代码

```python
class OnlineLSTM:
    def __init__(self, input_size, hidden_size, output_size):
        self.model = LSTMModel(input_size, hidden_size, output_size)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
        self.replay_buffer = ExperienceReplay(capacity=10000)
        self.ewc_lambda = 1000
        self.fisher_dict = {}
        self.optimal_params = {}
    
    def update(self, new_data):
        # 添加到经验回放
        self.replay_buffer.add(new_data)
        
        # 采样训练数据
        batch = self.replay_buffer.sample(batch_size=32)
        
        # 计算损失
        loss = self.compute_loss(batch)
        
        # 添加EWC惩罚
        if self.fisher_dict:
            ewc_loss = self.compute_ewc_loss()
            loss += self.ewc_lambda * ewc_loss
        
        # 反向传播
        self.optimizer.zero_grad()
        loss.backward()
        
        # 梯度裁剪
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
        
        self.optimizer.step()
    
    def compute_ewc_loss(self):
        loss = 0
        for name, param in self.model.named_parameters():
            if name in self.fisher_dict:
                fisher = self.fisher_dict[name]
                optimal = self.optimal_params[name]
                loss += (fisher * (param - optimal) ** 2).sum()
        return loss
    
    def update_fisher(self, data_loader):
        """更新Fisher信息矩阵"""
        self.model.eval()
        fisher = {}
        
        for name, param in self.model.named_parameters():
            fisher[name] = torch.zeros_like(param)
        
        for batch in data_loader:
            self.model.zero_grad()
            output = self.model(batch)
            loss = F.mse_loss(output, batch.target)
            loss.backward()
            
            for name, param in self.model.named_parameters():
                if param.grad is not None:
                    fisher[name] += param.grad.data ** 2
        
        # 平均
        for name in fisher:
            fisher[name] /= len(data_loader)
        
        self.fisher_dict = fisher
        self.optimal_params = {name: param.data.clone() 
                              for name, param in self.model.named_parameters()}
```

## 3. 因果发现算法

### 3.1 格兰杰因果检验

#### 3.1.1 原理

如果X的过去值能够提高对Y的预测精度，则称X格兰杰导致Y。

#### 3.1.2 F检验

```
H0: X不格兰杰导致Y

F = ((RSS_r - RSS_u) / p) / (RSS_u / (n - 2p - 1))
```

其中：
- RSS_r：受限模型（不含X的滞后项）的残差平方和
- RSS_u：非受限模型的残差平方和
- p：滞后阶数
- n：样本量

#### 3.1.3 实现

```python
from statsmodels.tsa.stattools import grangercausalitytests

def granger_causality_matrix(time_series_dict, maxlag=5):
    """计算多变量间的格兰杰因果矩阵"""
    variables = list(time_series_dict.keys())
    n = len(variables)
    causality_matrix = np.zeros((n, n))
    pvalue_matrix = np.ones((n, n))
    
    for i, cause in enumerate(variables):
        for j, effect in enumerate(variables):
            if i == j:
                continue
            
            # 构建二元时间序列
            data = pd.DataFrame({
                'effect': time_series_dict[effect],
                'cause': time_series_dict[cause]
            })
            
            # 格兰杰因果检验
            try:
                results = grangercausalitytests(data, maxlag=maxlag, verbose=False)
                
                # 取最优滞后阶数的p值
                best_lag = min(results.keys(), 
                             key=lambda k: results[k][0]['ssr_ftest'][1])
                p_value = results[best_lag][0]['ssr_ftest'][1]
                f_stat = results[best_lag][0]['ssr_ftest'][0]
                
                pvalue_matrix[i][j] = p_value
                
                # p值小于阈值则认为存在因果关系
                if p_value < 0.05:
                    causality_matrix[i][j] = f_stat
            except:
                pass
    
    return causality_matrix, pvalue_matrix
```

### 3.2 基于约束的因果发现（PC算法）

#### 3.2.1 算法步骤

1. **骨架学习**：通过条件独立性检验确定因果骨架
2. **定向**：利用v-structure定向边
3. **传播**：传播定向约束

#### 3.2.2 条件独立性检验

```python
def conditional_independence_test(X, Y, Z, data, alpha=0.05):
    """偏相关检验"""
    if len(Z) == 0:
        # 无条件检验：Pearson相关
        corr, p_value = pearsonr(data[X], data[Y])
    else:
        # 条件检验：偏相关
        residuals_X = regress_out(data[X], data[Z])
        residuals_Y = regress_out(data[Y], data[Z])
        corr, p_value = pearsonr(residuals_X, residuals_Y)
    
    return p_value > alpha  # True表示独立
```

## 4. 异常检测算法

### 4.1 基于统计的异常检测

#### 4.1.1 改进Z-Score

```python
def modified_z_score(data):
    """基于MAD的改进Z-Score"""
    median = np.median(data)
    mad = np.median(np.abs(data - median))
    
    if mad == 0:
        return np.zeros_like(data)
    
    modified_z = 0.6745 * (data - median) / mad
    return modified_z
```

#### 4.1.2 孤立森林

```python
from sklearn.ensemble import IsolationForest

class AdaptiveIsolationForest:
    def __init__(self, contamination=0.1):
        self.model = IsolationForest(contamination=contamination, random_state=42)
        self.is_fitted = False
    
    def fit(self, data):
        self.model.fit(data)
        self.is_fitted = True
    
    def predict(self, data):
        if not self.is_fitted:
            return np.zeros(len(data))
        
        # -1表示异常，1表示正常
        predictions = self.model.predict(data)
        return predictions == -1
    
    def partial_fit(self, new_data):
        """增量更新模型"""
        # 孤立森林不支持增量学习，这里采用滑动窗口重训练
        pass
```

### 4.2 基于预测的异常检测

```python
class PredictionBasedAnomalyDetector:
    def __init__(self, predictor, threshold_sigma=3):
        self.predictor = predictor
        self.threshold_sigma = threshold_sigma
        self.error_history = deque(maxlen=1000)
    
    def detect(self, current_state):
        # 获取预测
        prediction = self.predictor.predict_recent()
        
        # 计算预测误差
        error = abs(current_state - prediction)
        self.error_history.append(error)
        
        # 基于历史误差分布判断异常
        if len(self.error_history) < 100:
            return False
        
        mean_error = np.mean(self.error_history)
        std_error = np.std(self.error_history)
        
        if std_error == 0:
            return error > mean_error * 2
        
        z_score = (error - mean_error) / std_error
        
        return z_score > self.threshold_sigma
```

## 5. 多目标优化算法

### 5.1 权重聚合法

```python
def weighted_aggregate(objectives, weights):
    """加权聚合多目标"""
    return sum(w * o for w, o in zip(weights, objectives))
```

### 5.2 帕累托最优

```python
def is_pareto_dominated(solution, other_solutions):
    """判断解是否被帕累托支配"""
    for other in other_solutions:
        if all(other[i] >= solution[i] for i in range(len(solution))) and \
           any(other[i] > solution[i] for i in range(len(solution))):
            return True
    return False

def find_pareto_front(solutions):
    """找到帕累托前沿"""
    pareto_front = []
    for solution in solutions:
        if not is_pareto_dominated(solution, solutions):
            pareto_front.append(solution)
    return pareto_front
```

## 6. 时间序列分解算法

### 6.1 STL分解

```python
from statsmodels.tsa.seasonal import STL

def decompose_time_series(series, period=24):
    """STL时间序列分解"""
    stl = STL(series, period=period, robust=True)
    result = stl.fit()
    
    return {
        'trend': result.trend,
        'seasonal': result.seasonal,
        'residual': result.resid
    }
```

### 6.2 变分模态分解（VMD）

```python
def vmd(signal, alpha=2000, tau=0, K=5, DC=0, init=1, tol=1e-7):
    """
    变分模态分解
    
    Parameters:
    -----------
    signal : 输入信号
    alpha : 平衡参数
    tau : 噪声容忍度
    K : 模态数
    DC : 是否包含直流分量
    init : 初始化方法
    tol : 收敛容差
    """
    # 实现省略，可使用外部库
    pass
```

## 7. 特征选择算法

### 7.1 递归特征消除（RFE）

```python
from sklearn.feature_selection import RFE
from sklearn.ensemble import RandomForestRegressor

def recursive_feature_elimination(X, y, n_features=10):
    """递归特征消除"""
    estimator = RandomForestRegressor(n_estimators=100)
    selector = RFE(estimator, n_features_to_select=n_features)
    selector = selector.fit(X, y)
    
    return {
        'selected_features': selector.support_,
        'feature_ranking': selector.ranking_,
        'transformed_X': selector.transform(X)
    }
```

### 7.2 基于互信息的特征选择

```python
from sklearn.feature_selection import mutual_info_regression

def select_features_by_mutual_info(X, y, k=10):
    """基于互信息选择特征"""
    mi_scores = mutual_info_regression(X, y)
    
    # 选择top-k特征
    top_indices = np.argsort(mi_scores)[-k:]
    
    return top_indices, mi_scores
```

## 8. 模型压缩算法

### 8.1 权重剪枝

```python
def prune_weights(model, sparsity=0.3):
    """基于幅度的权重剪枝"""
    for name, param in model.named_parameters():
        if 'weight' in name:
            # 计算阈值
            threshold = torch.quantile(torch.abs(param), sparsity)
            
            # 创建掩码
            mask = torch.abs(param) > threshold
            
            # 应用掩码
            param.data *= mask.float()
    
    return model
```

### 8.2 知识蒸馏

```python
class KnowledgeDistillation:
    def __init__(self, teacher_model, student_model, temperature=4):
        self.teacher = teacher_model
        self.student = student_model
        self.T = temperature
    
    def distillation_loss(self, student_logits, teacher_logits, labels, alpha=0.5):
        """蒸馏损失 = 软目标损失 + 硬目标损失"""
        # 软目标（使用温度参数）
        soft_targets = F.softmax(teacher_logits / self.T, dim=1)
        soft_prob = F.log_softmax(student_logits / self.T, dim=1)
        soft_loss = F.kl_div(soft_prob, soft_targets, reduction='batchmean') * (self.T ** 2)
        
        # 硬目标
        hard_loss = F.cross_entropy(student_logits, labels)
        
        return alpha * soft_loss + (1 - alpha) * hard_loss
```

---

高级算法详解提供了Agent系统核心算法的深入技术细节，包括数学推导、实现代码和优化技巧，为开发者提供可直接参考的工程实现指南。
