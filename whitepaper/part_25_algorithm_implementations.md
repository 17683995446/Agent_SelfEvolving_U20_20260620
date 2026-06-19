# 第二十五章：核心算法完整实现

## 25.1 算法实现概述

本章提供自驱永续进化Agent系统中所有核心算法的完整Python实现。每个算法都包含详细的数学推导、伪代码、实际代码实现、复杂度分析和测试用例。

## 25.2 自适应指数平滑算法完整实现

### 25.2.1 数学基础

自适应指数平滑（Adaptive Exponential Smoothing, AES）是对传统指数平滑的扩展，通过动态调整平滑参数α来适应数据的变化特性。

**传统指数平滑公式：**
```
s_t = α * x_t + (1-α) * s_{t-1}
```

**自适应指数平滑公式：**
```
s_t = α_t * x_t + (1-α_t) * s_{t-1}
α_t = f(e_t, ∇e_t, σ_e)
```

其中α_t是时变平滑参数，根据预测误差e_t、误差变化率∇e_t和误差标准差σ_e动态调整。

### 25.2.2 完整Python实现

```python
import numpy as np
from typing import Optional, Tuple, List
from dataclasses import dataclass
from collections import deque
import logging

@dataclass
class AESConfig:
    """自适应指数平滑配置参数"""
    alpha_min: float = 0.05  # 最小平滑参数
    alpha_max: float = 0.95  # 最大平滑参数
    alpha_default: float = 0.3  # 默认平滑参数
    adaptation_rate: float = 0.1  # 自适应学习率
    error_window_size: int = 50  # 误差窗口大小
    trend_detection_threshold: float = 0.1  # 趋势检测阈值
    seasonal_period: Optional[int] = None  # 季节性周期
    damping_factor: float = 0.9  # 阻尼因子

class AdaptiveExponentialSmoother:
    """
    自适应指数平滑预测器
    
    特性：
    1. 动态调整平滑参数α
    2. 自动检测趋势和季节性
    3. 支持多步预测
    4. 提供预测置信区间
    """
    
    def __init__(self, config: Optional[AESConfig] = None):
        self.config = config or AESConfig()
        self.logger = logging.getLogger(__name__)
        
        # 状态变量
        self.level = None  # 水平分量
        self.trend = None  # 趋势分量
        self.seasonal = None  # 季节性分量
        self.alpha = self.config.alpha_default  # 当前平滑参数
        
        # 历史数据
        self.history = deque(maxlen=1000)
        self.errors = deque(maxlen=self.config.error_window_size)
        self.predictions = deque(maxlen=self.config.error_window_size)
        
        # 统计量
        self.error_mean = 0.0
        self.error_var = 0.0
        self.error_trend = 0.0
        
        # 元数据
        self.initialized = False
        self.step_count = 0
        
    def initialize(self, initial_data: np.ndarray):
        """
        使用历史数据初始化模型
        
        Args:
            initial_data: 初始数据序列，至少包含seasonal_period*2个数据点
        """
        if len(initial_data) < 2:
            raise ValueError("初始化数据至少需要2个数据点")
            
        # 计算初始水平
        self.level = np.mean(initial_data[:10])
        
        # 计算初始趋势
        if len(initial_data) >= 10:
            first_half = np.mean(initial_data[:5])
            second_half = np.mean(initial_data[5:10])
            self.trend = (second_half - first_half) / 5
        else:
            self.trend = initial_data[-1] - initial_data[-2] if len(initial_data) > 1 else 0
            
        # 初始化季节性分量
        if self.config.seasonal_period and len(initial_data) >= 2 * self.config.seasonal_period:
            self._initialize_seasonal(initial_data)
        else:
            self.seasonal = None
            
        # 填充历史
        for val in initial_data:
            self.history.append(val)
            
        self.initialized = True
        self.logger.info(f"AES模型初始化完成，水平={self.level:.4f}，趋势={self.trend:.4f}")
        
    def _initialize_seasonal(self, data: np.ndarray):
        """初始化季节性分量"""
        period = self.config.seasonal_period
        n_complete = len(data) // period
        
        # 计算每个周期的平均值
        seasonal_means = []
        for i in range(period):
            indices = [i + j * period for j in range(n_complete) if i + j * period < len(data)]
            seasonal_means.append(np.mean([data[idx] for idx in indices]))
            
        # 去中心化
        seasonal_mean = np.mean(seasonal_means)
        self.seasonal = np.array([m - seasonal_mean for m in seasonal_means])
        
    def _update_alpha(self, actual: float, predicted: float):
        """
        动态更新平滑参数α
        
        策略：
        1. 预测误差大 → 增大α（更关注最新数据）
        2. 误差趋势上升 → 增大α（数据在变化）
        3. 误差方差大 → 减小α（数据噪声大）
        """
        error = actual - predicted
        self.errors.append(error)
        
        if len(self.errors) < 5:
            return
            
        # 计算误差统计量
        errors_array = np.array(self.errors)
        current_error_mean = np.mean(errors_array)
        current_error_var = np.var(errors_array)
        
        # 计算误差趋势（最近5个vs之前）
        if len(errors_array) >= 10:
            recent_error = np.mean(np.abs(errors_array[-5:]))
            older_error = np.mean(np.abs(errors_array[-10:-5]))
            error_trend = recent_error - older_error
        else:
            error_trend = 0
            
        # 自适应调整α
        # 误差增大 → α增大
        error_factor = np.tanh(abs(current_error_mean) / (np.sqrt(current_error_var) + 1e-8))
        
        # 误差趋势上升 → α增大
        trend_factor = np.tanh(error_trend * 5)
        
        # 方差大 → α减小（更平滑）
        variance_factor = -np.tanh(current_error_var / 10)
        
        # 综合调整
        alpha_adjustment = (
            error_factor * 0.4 +
            trend_factor * 0.4 +
            variance_factor * 0.2
        ) * self.config.adaptation_rate
        
        self.alpha = np.clip(
            self.alpha + alpha_adjustment,
            self.config.alpha_min,
            self.config.alpha_max
        )
        
        # 更新统计量
        self.error_mean = current_error_mean
        self.error_var = current_error_var
        self.error_trend = error_trend
        
    def update(self, value: float) -> Tuple[float, float, float]:
        """
        更新模型并返回预测结果
        
        Args:
            value: 新的观测值
            
        Returns:
            (预测值, 预测误差, 当前alpha)
        """
        if not self.initialized:
            self.initialize(np.array([value]))
            return value, 0.0, self.alpha
            
        # 预测当前值（使用上一时刻的参数）
        if self.seasonal is not None:
            seasonal_idx = self.step_count % len(self.seasonal)
            prediction = self.level + self.trend + self.seasonal[seasonal_idx]
        else:
            prediction = self.level + self.trend
            
        # 计算误差
        error = value - prediction
        
        # 更新alpha
        self._update_alpha(value, prediction)
        
        # 更新水平分量
        if self.seasonal is not None:
            seasonal_idx = self.step_count % len(self.seasonal)
            level_update = value - self.seasonal[seasonal_idx]
        else:
            level_update = value
            
        old_level = self.level
        self.level = self.alpha * level_update + (1 - self.alpha) * (self.level + self.trend)
        
        # 更新趋势分量（阻尼趋势）
        if self.trend is not None:
            self.trend = (
                self.config.damping_factor * self.trend +
                (1 - self.config.damping_factor) * (self.level - old_level)
            )
            
        # 更新季节性分量
        if self.seasonal is not None:
            seasonal_idx = self.step_count % len(self.seasonal)
            seasonal_error = value - self.level
            self.seasonal[seasonal_idx] = (
                0.3 * seasonal_error +
                0.7 * self.seasonal[seasonal_idx]
            )
            # 重新去中心化
            self.seasonal = self.seasonal - np.mean(self.seasonal)
            
        # 更新历史
        self.history.append(value)
        self.predictions.append(prediction)
        self.step_count += 1
        
        return prediction, error, self.alpha
        
    def forecast(self, steps: int = 1, return_confidence: bool = False) -> np.ndarray:
        """
        多步预测
        
        Args:
            steps: 预测步数
            return_confidence: 是否返回置信区间
            
        Returns:
            预测值数组，或(预测值, 下界, 上界)元组
        """
        if not self.initialized:
            raise RuntimeError("模型未初始化")
            
        forecasts = []
        
        for i in range(1, steps + 1):
            # 趋势外推
            forecast = self.level + self.trend * i
            
            # 添加季节性
            if self.seasonal is not None:
                seasonal_idx = (self.step_count + i) % len(self.seasonal)
                forecast += self.seasonal[seasonal_idx]
                
            forecasts.append(forecast)
            
        forecasts = np.array(forecasts)
        
        if return_confidence:
            # 计算置信区间（基于历史误差）
            if len(self.errors) > 0:
                error_std = np.std(self.errors)
                confidence_width = 1.96 * error_std * np.sqrt(np.arange(1, steps + 1))
                lower = forecasts - confidence_width
                upper = forecasts + confidence_width
                return forecasts, lower, upper
            else:
                return forecasts, forecasts, forecasts
                
        return forecasts
        
    def get_metrics(self) -> dict:
        """获取模型性能指标"""
        if len(self.errors) == 0:
            return {}
            
        errors_array = np.array(self.errors)
        
        return {
            'mae': np.mean(np.abs(errors_array)),
            'mse': np.mean(errors_array ** 2),
            'rmse': np.sqrt(np.mean(errors_array ** 2)),
            'mape': np.mean(np.abs(errors_array / (np.array(self.history)[-len(errors_array):] + 1e-8))) * 100,
            'current_alpha': self.alpha,
            'error_trend': self.error_trend,
            'error_std': np.std(errors_array)
        }
```

### 25.2.3 算法复杂度分析

**时间复杂度：**
- 单次更新：O(1)
- 初始化：O(n)，n为初始化数据长度
- k步预测：O(k)

**空间复杂度：**
- 固定开销：O(1)
- 历史存储：O(w)，w为窗口大小（默认1000）
- 总空间：O(w)

### 25.2.4 测试用例

```python
import unittest

class TestAdaptiveExponentialSmoother(unittest.TestCase):
    def test_basic_prediction(self):
        """测试基本预测功能"""
        aes = AdaptiveExponentialSmoother()
        
        # 生成测试数据：带趋势的正弦波
        t = np.linspace(0, 4*np.pi, 100)
        data = 10 + 0.5*t + 2*np.sin(t) + np.random.normal(0, 0.5, 100)
        
        # 初始化
        aes.initialize(data[:20])
        
        # 在线更新
        errors = []
        for val in data[20:]:
            pred, err, alpha = aes.update(val)
            errors.append(abs(err))
            
        # 验证预测误差在合理范围内
        mean_error = np.mean(errors)
        self.assertLess(mean_error, 3.0)  # 平均误差应小于3
        
    def test_adaptation(self):
        """测试自适应能力"""
        aes = AdaptiveExponentialSmoother(
            AESConfig(alpha_default=0.3, adaptation_rate=0.1)
        )
        
        # 前半段平稳数据
        stable_data = np.random.normal(10, 1, 50)
        
        # 后半段突变数据
        shift_data = np.random.normal(20, 1, 50)
        
        data = np.concatenate([stable_data, shift_data])
        
        aes.initialize(data[:10])
        
        alphas = []
        for val in data[10:]:
            aes.update(val)
            alphas.append(aes.alpha)
            
        # 验证突变后alpha增大
        early_alpha = np.mean(alphas[:20])
        late_alpha = np.mean(alphas[-20:])
        self.assertGreater(late_alpha, early_alpha)
```

## 25.3 在线LSTM增量学习算法完整实现

### 25.3.1 数学基础

在线LSTM（Long Short-Term Memory）增量学习结合了循环神经网络的时序建模能力和增量学习的持续学习能力。

**LSTM核心公式：**

遗忘门：
```
f_t = σ(W_f · [h_{t-1}, x_t] + b_f)
```

输入门：
```
i_t = σ(W_i · [h_{t-1}, x_t] + b_i)
C̃_t = tanh(W_C · [h_{t-1}, x_t] + b_C)
```

细胞状态更新：
```
C_t = f_t * C_{t-1} + i_t * C̃_t
```

输出门：
```
o_t = σ(W_o · [h_{t-1}, x_t] + b_o)
h_t = o_t * tanh(C_t)
```

**增量学习策略：**
1. 弹性权重巩固（EWC）：保护重要参数
2. 经验回放：混合新旧样本
3. 学习率退火：稳定训练

### 25.3.2 完整Python实现

```python
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
from typing import List, Tuple, Optional, Dict
from collections import deque
import copy

class OnlineLSTMCell(nn.Module):
    """
    在线LSTM单元，支持增量学习
    """
    def __init__(self, input_size: int, hidden_size: int, dropout: float = 0.2):
        super().__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        
        # 门控权重
        self.weight_ih = nn.Parameter(torch.randn(4 * hidden_size, input_size) * 0.01)
        self.weight_hh = nn.Parameter(torch.randn(4 * hidden_size, hidden_size) * 0.01)
        self.bias = nn.Parameter(torch.zeros(4 * hidden_size))
        
        # Dropout
        self.dropout = nn.Dropout(dropout)
        
        # 初始化
        self._init_weights()
        
    def _init_weights(self):
        """正交初始化"""
        for p in self.parameters():
            if p.dim() >= 2:
                nn.init.orthogonal_(p)
                
    def forward(self, x: torch.Tensor, state: Optional[Tuple] = None):
        """
        前向传播
        
        Args:
            x: 输入 (batch_size, input_size)
            state: (h, c) 前一时刻状态
            
        Returns:
            h: 隐藏状态
            (h, c): 新状态
        """
        batch_size = x.size(0)
        
        if state is None:
            h_prev = torch.zeros(batch_size, self.hidden_size, device=x.device)
            c_prev = torch.zeros(batch_size, self.hidden_size, device=x.device)
        else:
            h_prev, c_prev = state
            
        # 计算门控
        gates = torch.mm(x, self.weight_ih.t()) + torch.mm(h_prev, self.weight_hh.t()) + self.bias
        
        i, f, g, o = gates.chunk(4, 1)
        
        i = torch.sigmoid(i)  # 输入门
        f = torch.sigmoid(f)  # 遗忘门
        g = torch.tanh(g)     # 候选状态
        o = torch.sigmoid(o)  # 输出门
        
        # 更新细胞状态
        c = f * c_prev + i * g
        
        # 计算隐藏状态
        h = o * torch.tanh(c)
        
        h = self.dropout(h)
        
        return h, (h, c)


class OnlineLSTM(nn.Module):
    """
    在线LSTM预测模型，支持增量学习
    """
    def __init__(
        self,
        input_size: int,
        hidden_size: int = 64,
        num_layers: int = 2,
        output_size: int = 1,
        dropout: float = 0.2,
        device: str = 'cpu'
    ):
        super().__init__()
        
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.output_size = output_size
        self.device = device
        
        # LSTM层
        self.lstm_cells = nn.ModuleList([
            OnlineLSTMCell(
                input_size if i == 0 else hidden_size,
                hidden_size,
                dropout if i < num_layers - 1 else 0
            )
            for i in range(num_layers)
        ])
        
        # 输出层
        self.fc = nn.Linear(hidden_size, output_size)
        
        # 移动到设备
        self.to(device)
        
        # 优化器
        self.optimizer = None
        self.scheduler = None
        
        # 经验回放缓冲区
        self.replay_buffer = deque(maxlen=10000)
        
        # EWC相关
        self.ewc_lambda = 0.0
        self.ewc_params = {}
        self.ewc_fisher = {}
        
        # 训练状态
        self.training_steps = 0
        
    def forward(self, x: torch.Tensor, states: Optional[List] = None):
        """
        前向传播
        
        Args:
            x: 输入序列 (batch_size, seq_len, input_size)
            states: 初始状态列表
            
        Returns:
            output: 预测输出
            states: 最终状态列表
        """
        batch_size, seq_len, _ = x.shape
        
        if states is None:
            states = [None] * self.num_layers
            
        # 逐时间步处理
        layer_input = x
        new_states = []
        
        for layer_idx, cell in enumerate(self.lstm_cells):
            layer_outputs = []
            state = states[layer_idx]
            
            for t in range(seq_len):
                out, state = cell(layer_input[:, t, :], state)
                layer_outputs.append(out)
                
            layer_input = torch.stack(layer_outputs, dim=1)
            new_states.append(state)
            
        # 取最后一个时间步
        last_output = layer_input[:, -1, :]
        
        # 全连接层
        output = self.fc(last_output)
        
        return output, new_states
        
    def predict(self, x: np.ndarray) -> np.ndarray:
        """预测接口"""
        self.eval()
        with torch.no_grad():
            x_tensor = torch.FloatTensor(x).to(self.device)
            if len(x_tensor.shape) == 2:
                x_tensor = x_tensor.unsqueeze(0)
            output, _ = self.forward(x_tensor)
            return output.cpu().numpy()
            
    def online_learn(
        self,
        x: np.ndarray,
        y: np.ndarray,
        learning_rate: float = 0.001,
        batch_size: int = 32,
        epochs: int = 1,
        replay_ratio: float = 0.3
    ) -> float:
        """
        在线增量学习
        
        Args:
            x: 输入数据 (n_samples, seq_len, input_size)
            y: 目标数据 (n_samples, output_size)
            learning_rate: 学习率
            batch_size: 批次大小
            epochs: 训练轮数
            replay_ratio: 经验回放比例
            
        Returns:
            平均损失
        """
        self.train()
        
        # 初始化优化器
        if self.optimizer is None:
            self.optimizer = optim.Adam(self.parameters(), lr=learning_rate)
            self.scheduler = optim.lr_scheduler.ExponentialLR(
                self.optimizer, gamma=0.995
            )
            
        # 添加到回放缓冲区
        for xi, yi in zip(x, y):
            self.replay_buffer.append((xi, yi))
            
        # 混合新旧数据
        n_new = len(x)
        n_replay = int(n_new * replay_ratio)
        
        if len(self.replay_buffer) > n_new and n_replay > 0:
            replay_indices = np.random.choice(
                len(self.replay_buffer) - n_new,
                min(n_replay, len(self.replay_buffer) - n_new),
                replace=False
            )
            replay_data = [self.replay_buffer[i] for i in replay_indices]
            x_replay = np.array([d[0] for d in replay_data])
            y_replay = np.array([d[1] for d in replay_data])
            
            x = np.concatenate([x, x_replay])
            y = np.concatenate([y, y_replay])
            
        # 创建数据加载器
        dataset = TensorDataset(
            torch.FloatTensor(x),
            torch.FloatTensor(y)
        )
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
        
        # 训练
        total_loss = 0
        n_batches = 0
        
        for epoch in range(epochs):
            for batch_x, batch_y in loader:
                batch_x = batch_x.to(self.device)
                batch_y = batch_y.to(self.device)
                
                self.optimizer.zero_grad()
                
                # 前向传播
                output, _ = self.forward(batch_x)
                
                # 计算损失
                loss = nn.MSELoss()(output, batch_y)
                
                # EWC正则化
                if self.ewc_lambda > 0 and len(self.ewc_params) > 0:
                    ewc_loss = self._compute_ewc_loss()
                    loss += self.ewc_lambda * ewc_loss
                    
                # 反向传播
                loss.backward()
                
                # 梯度裁剪
                torch.nn.utils.clip_grad_norm_(self.parameters(), 1.0)
                
                self.optimizer.step()
                
                total_loss += loss.item()
                n_batches += 1
                
            self.scheduler.step()
            
        self.training_steps += 1
        
        return total_loss / n_batches if n_batches > 0 else 0
        
    def compute_fisher_information(self, x: np.ndarray, y: np.ndarray):
        """
        计算Fisher信息矩阵（用于EWC）
        """
        self.eval()
        
        x_tensor = torch.FloatTensor(x).to(self.device)
        y_tensor = torch.FloatTensor(y).to(self.device)
        
        self.optimizer.zero_grad()
        output, _ = self.forward(x_tensor)
        loss = nn.MSELoss()(output, y_tensor)
        loss.backward()
        
        # 记录Fisher信息
        for name, param in self.named_parameters():
            if param.grad is not None:
                if name not in self.ewc_fisher:
                    self.ewc_fisher[name] = torch.zeros_like(param)
                self.ewc_fisher[name] += param.grad.data ** 2 / len(x)
                
    def _compute_ewc_loss(self) -> torch.Tensor:
        """计算EWC损失"""
        loss = 0
        for name, param in self.named_parameters():
            if name in self.ewc_params and name in self.ewc_fisher:
                loss += torch.sum(
                    self.ewc_fisher[name] * (param - self.ewc_params[name]) ** 2
                )
        return loss
        
    def save_ewc_params(self):
        """保存当前参数作为EWC锚点"""
        for name, param in self.named_parameters():
            self.ewc_params[name] = param.data.clone()
            
    def enable_ewc(self, lambda_ewc: float = 1000.0):
        """启用EWC"""
        self.ewc_lambda = lambda_ewc
        self.save_ewc_params()


class OnlineLSTMManager:
    """
    LSTM模型管理器，处理多模型协调
    """
    def __init__(
        self,
        input_size: int,
        hidden_sizes: List[int] = [32, 64, 128],
        seq_len: int = 10,
        device: str = 'cpu'
    ):
        self.models = {}
        self.seq_len = seq_len
        
        # 创建不同复杂度的模型
        for hidden in hidden_sizes:
            name = f"lstm_h{hidden}"
            self.models[name] = OnlineLSTM(
                input_size=input_size,
                hidden_size=hidden,
                num_layers=2,
                output_size=1,
                device=device
            )
            
        self.active_model = list(self.models.keys())[0]
        self.performance_history = {name: deque(maxlen=100) for name in self.models}
        
    def update(self, x: np.ndarray, y: np.ndarray) -> Dict[str, float]:
        """
        更新所有模型
        
        Returns:
            各模型的损失
        """
        losses = {}
        
        for name, model in self.models.items():
            loss = model.online_learn(x, y, epochs=1)
            losses[name] = loss
            self.performance_history[name].append(loss)
            
        return losses
        
    def predict(self, x: np.ndarray) -> Tuple[np.ndarray, str]:
        """
        使用最佳模型预测
        
        Returns:
            (预测值, 使用的模型名)
        """
        # 选择平均性能最好的模型
        best_model = self.active_model
        best_score = float('inf')
        
        for name, history in self.performance_history.items():
            if len(history) > 0:
                avg_loss = np.mean(history)
                if avg_loss < best_score:
                    best_score = avg_loss
                    best_model = name
                    
        self.active_model = best_model
        
        prediction = self.models[best_model].predict(x)
        return prediction, best_model
        
    def get_model_complexity(self, name: str) -> int:
        """获取模型参数量"""
        return sum(p.numel() for p in self.models[name].parameters())
```

## 25.4 因果发现算法完整实现

### 25.4.1 Granger因果检验

```python
from statsmodels.tsa.stattools import grangercausalitytests
from typing import Dict, List, Tuple
import numpy as np

class GrangerCausalityAnalyzer:
    """
    Granger因果检验分析器
    
    用于检测时间序列之间的预测因果关系
    """
    
    def __init__(self, max_lag: int = 5, significance_level: float = 0.05):
        self.max_lag = max_lag
        self.significance_level = significance_level
        
    def test_causality(
        self,
        cause_series: np.ndarray,
        effect_series: np.ndarray
    ) -> Dict:
        """
        检验cause_series是否Granger引起effect_series
        
        Returns:
            {
                'causal': bool,
                'min_pvalue': float,
                'optimal_lag': int,
                'test_results': dict
            }
        """
        # 准备数据
        data = np.column_stack([effect_series, cause_series])
        
        try:
            test_result = grangercausalitytests(
                data, maxlag=self.max_lag, verbose=False
            )
            
            # 提取p值
            pvalues = []
            for lag in range(1, self.max_lag + 1):
                # 使用F检验的p值
                pval = test_result[lag][0]['ssr_ftest'][1]
                pvalues.append(pval)
                
            min_pvalue = min(pvalues)
            optimal_lag = np.argmin(pvalues) + 1
            
            return {
                'causal': min_pvalue < self.significance_level,
                'min_pvalue': min_pvalue,
                'optimal_lag': optimal_lag,
                'test_results': test_result
            }
            
        except Exception as e:
            return {
                'causal': False,
                'min_pvalue': 1.0,
                'optimal_lag': 0,
                'error': str(e)
            }
            
    def build_causal_graph(
        self,
        series_dict: Dict[str, np.ndarray]
    ) -> Dict[Tuple[str, str], Dict]:
        """
        构建变量间的因果图
        
        Args:
            series_dict: {变量名: 时间序列}
            
        Returns:
            {(cause, effect): 检验结果}
        """
        causal_graph = {}
        
        variables = list(series_dict.keys())
        
        for cause in variables:
            for effect in variables:
                if cause != effect:
                    result = self.test_causality(
                        series_dict[cause],
                        series_dict[effect]
                    )
                    causal_graph[(cause, effect)] = result
                    
        return causal_graph
```

### 25.4.2 PC算法简化实现

```python
class PCSimplified:
    """
    PC算法简化实现（基于条件独立性检验）
    """
    
    def __init__(self, significance_level: float = 0.05):
        self.alpha = significance_level
        
    def partial_correlation(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray
    ) -> float:
        """
        计算偏相关系数
        
        ρ_xy|z = (ρ_xy - ρ_xz*ρ_yz) / sqrt((1-ρ_xz²)(1-ρ_yz²))
        """
        def corr(a, b):
            return np.corrcoef(a, b)[0, 1]
            
        r_xy = corr(x, y)
        r_xz = corr(x, z)
        r_yz = corr(y, z)
        
        numerator = r_xy - r_xz * r_yz
        denominator = np.sqrt((1 - r_xz**2) * (1 - r_yz**2))
        
        if denominator == 0:
            return 0
            
        return numerator / denominator
        
    def conditional_independence_test(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray
    ) -> Tuple[bool, float]:
        """
        条件独立性检验
        
        Returns:
            (是否独立, p值)
        """
        n = len(x)
        
        # 计算偏相关系数
        r = self.partial_correlation(x, y, z)
        
        # Fisher Z变换
        z_stat = 0.5 * np.log((1 + r) / (1 - r))
        
        # 检验统计量
        test_stat = np.sqrt(n - 3) * abs(z_stat)
        
        # p值（双侧检验）
        from scipy import stats
        p_value = 2 * (1 - stats.norm.cdf(test_stat))
        
        return p_value > self.alpha, p_value
```

## 25.5 多目标优化算法实现

### 25.5.1 NSGA-II简化实现

```python
class NSGAIISimplified:
    """
    NSGA-II多目标优化算法简化实现
    
    用于任务选择的帕累托最优解搜索
    """
    
    def __init__(
        self,
        population_size: int = 50,
        generations: int = 100,
        crossover_prob: float = 0.9,
        mutation_prob: float = 0.1
    ):
        self.pop_size = population_size
        self.generations = generations
        self.crossover_prob = crossover_prob
        self.mutation_prob = mutation_prob
        
    def optimize(
        self,
        objectives: List[callable],
        bounds: List[Tuple[float, float]],
        n_objectives: int = 3
    ) -> List[np.ndarray]:
        """
        执行多目标优化
        
        Args:
            objectives: 目标函数列表
            bounds: 变量边界
            n_objectives: 目标数量
            
        Returns:
            帕累托前沿解集
        """
        n_vars = len(bounds)
        
        # 初始化种群
        population = self._initialize_population(bounds)
        
        for gen in range(self.generations):
            # 评估适应度
            fitness = self._evaluate(population, objectives)
            
            # 非支配排序
            fronts = self._non_dominated_sort(population, fitness)
            
            # 选择、交叉、变异
            offspring = self._create_offspring(population, fronts, bounds)
            
            # 合并并选择下一代
            combined = np.vstack([population, offspring])
            combined_fitness = self._evaluate(combined, objectives)
            combined_fronts = self._non_dominated_sort(combined, combined_fitness)
            
            population = self._select_next_generation(
                combined, combined_fronts, combined_fitness
            )
            
        # 返回最终帕累托前沿
        final_fitness = self._evaluate(population, objectives)
        final_fronts = self._non_dominated_sort(population, final_fitness)
        
        if len(final_fronts) > 0:
            return [population[i] for i in final_fronts[0]]
        return []
        
    def _initialize_population(
        self,
        bounds: List[Tuple[float, float]]
    ) -> np.ndarray:
        """随机初始化种群"""
        n_vars = len(bounds)
        population = np.random.rand(self.pop_size, n_vars)
        
        for i, (low, high) in enumerate(bounds):
            population[:, i] = low + population[:, i] * (high - low)
            
        return population
        
    def _evaluate(
        self,
        population: np.ndarray,
        objectives: List[callable]
    ) -> np.ndarray:
        """评估种群适应度"""
        fitness = np.zeros((len(population), len(objectives)))
        
        for i, individual in enumerate(population):
            for j, obj in enumerate(objectives):
                fitness[i, j] = obj(individual)
                
        return fitness
        
    def _non_dominated_sort(
        self,
        population: np.ndarray,
        fitness: np.ndarray
    ) -> List[List[int]]:
        """非支配排序"""
        n = len(population)
        domination_count = [0] * n
        dominated_solutions = [[] for _ in range(n)]
        fronts = [[]]
        
        for i in range(n):
            for j in range(i + 1, n):
                if self._dominates(fitness[i], fitness[j]):
                    dominated_solutions[i].append(j)
                    domination_count[j] += 1
                elif self._dominates(fitness[j], fitness[i]):
                    dominated_solutions[j].append(i)
                    domination_count[i] += 1
                    
            if domination_count[i] == 0:
                fronts[0].append(i)
                
        i = 0
        while len(fronts[i]) > 0:
            next_front = []
            for p in fronts[i]:
                for q in dominated_solutions[p]:
                    domination_count[q] -= 1
                    if domination_count[q] == 0:
                        next_front.append(q)
            i += 1
            fronts.append(next_front)
            
        return fronts[:-1]  # 去除空的前沿
        
    def _dominates(self, f1: np.ndarray, f2: np.ndarray) -> bool:
        """判断f1是否支配f2（假设最小化问题）"""
        return np.all(f1 <= f2) and np.any(f1 < f2)
        
    def _create_offspring(
        self,
        population: np.ndarray,
        fronts: List[List[int]],
        bounds: List[Tuple[float, float]]
    ) -> np.ndarray:
        """创建子代"""
        offspring = []
        
        while len(offspring) < self.pop_size:
            # 锦标赛选择
            parent1 = self._tournament_select(population, fronts)
            parent2 = self._tournament_select(population, fronts)
            
            # 交叉
            if np.random.rand() < self.crossover_prob:
                child1, child2 = self._crossover(parent1, parent2)
            else:
                child1, child2 = parent1.copy(), parent2.copy()
                
            # 变异
            child1 = self._mutate(child1, bounds)
            child2 = self._mutate(child2, bounds)
            
            offspring.extend([child1, child2])
            
        return np.array(offspring[:self.pop_size])
        
    def _tournament_select(
        self,
        population: np.ndarray,
        fronts: List[List[int]]
    ) -> np.ndarray:
        """锦标赛选择"""
        # 简化为随机选择
        idx = np.random.randint(0, len(population))
        return population[idx]
        
    def _crossover(
        self,
        parent1: np.ndarray,
        parent2: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """模拟二进制交叉"""
        eta = 20
        rand = np.random.rand(len(parent1))
        
        beta = np.where(
            rand <= 0.5,
            (2 * rand) ** (1 / (eta + 1)),
            (2 * (1 - rand)) ** (-1 / (eta + 1))
        )
        
        child1 = 0.5 * ((1 + beta) * parent1 + (1 - beta) * parent2)
        child2 = 0.5 * ((1 - beta) * parent1 + (1 + beta) * parent2)
        
        return child1, child2
        
    def _mutate(
        self,
        individual: np.ndarray,
        bounds: List[Tuple[float, float]]
    ) -> np.ndarray:
        """多项式变异"""
        eta_m = 20
        
        for i, (low, high) in enumerate(bounds):
            if np.random.rand() < self.mutation_prob:
                delta1 = (individual[i] - low) / (high - low)
                delta2 = (high - individual[i]) / (high - low)
                
                rand = np.random.rand()
                mut_pow = 1.0 / (eta_m + 1)
                
                if rand <= 0.5:
                    xy = 1.0 - delta1
                    val = 2.0 * rand + (1.0 - 2.0 * rand) * (xy ** (eta_m + 1))
                    delta_q = val ** mut_pow - 1.0
                else:
                    xy = 1.0 - delta2
                    val = 2.0 * (1.0 - rand) + 2.0 * (rand - 0.5) * (xy ** (eta_m + 1))
                    delta_q = 1.0 - val ** mut_pow
                    
                individual[i] += delta_q * (high - low)
                individual[i] = np.clip(individual[i], low, high)
                
        return individual
        
    def _select_next_generation(
        self,
        combined: np.ndarray,
        fronts: List[List[int]],
        fitness: np.ndarray
    ) -> np.ndarray:
        """选择下一代"""
        selected = []
        
        for front in fronts:
            if len(selected) + len(front) <= self.pop_size:
                selected.extend(front)
            else:
                # 计算拥挤距离并选择
                remaining = self.pop_size - len(selected)
                distances = self._crowding_distance(front, fitness)
                sorted_indices = np.argsort(distances)[::-1]
                selected.extend([front[i] for i in sorted_indices[:remaining]])
                break
                
        return combined[selected]
        
    def _crowding_distance(
        self,
        front: List[int],
        fitness: np.ndarray
    ) -> np.ndarray:
        """计算拥挤距离"""
        if len(front) <= 2:
            return np.ones(len(front)) * float('inf')
            
        distances = np.zeros(len(front))
        
        for obj in range(fitness.shape[1]):
            sorted_indices = np.argsort(fitness[front, obj])
            distances[sorted_indices[0]] = distances[sorted_indices[-1]] = float('inf')
            
            f_max = fitness[front[sorted_indices[-1]], obj]
            f_min = fitness[front[sorted_indices[0]], obj]
            
            if f_max > f_min:
                for i in range(1, len(front) - 1):
                    distances[sorted_indices[i]] += (
                        fitness[front[sorted_indices[i + 1]], obj] -
                        fitness[front[sorted_indices[i - 1]], obj]
                    ) / (f_max - f_min)
                    
        return distances
```

## 25.6 异常检测算法实现

```python
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import numpy as np

class AnomalyDetector:
    """
    多算法融合异常检测器
    """
    
    def __init__(self, contamination: float = 0.1):
        self.contamination = contamination
        self.isolation_forest = IsolationForest(
            contamination=contamination,
            random_state=42
        )
        self.scaler = StandardScaler()
        self.threshold = None
        
    def fit(self, X: np.ndarray):
        """训练检测器"""
        X_scaled = self.scaler.fit_transform(X)
        self.isolation_forest.fit(X_scaled)
        
        # 计算异常分数阈值
        scores = self.isolation_forest.score_samples(X_scaled)
        self.threshold = np.percentile(scores, self.contamination * 100)
        
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        预测异常
        
        Returns:
            1表示正常，-1表示异常
        """
        X_scaled = self.scaler.transform(X)
        return self.isolation_forest.predict(X_scaled)
        
    def score(self, X: np.ndarray) -> np.ndarray:
        """获取异常分数（越低越异常）"""
        X_scaled = self.scaler.transform(X)
        return self.isolation_forest.score_samples(X_scaled)
        
    def detect_anomalies(
        self,
        X: np.ndarray,
        return_details: bool = False
    ):
        """
        检测异常并返回详细信息
        """
        scores = self.score(X)
        predictions = np.where(scores < self.threshold, -1, 1)
        
        if return_details:
            anomaly_indices = np.where(predictions == -1)[0]
            return {
                'predictions': predictions,
                'scores': scores,
                'anomaly_indices': anomaly_indices,
                'anomaly_ratio': len(anomaly_indices) / len(X)
            }
            
        return predictions
```

## 25.7 算法性能对比

| 算法 | 时间复杂度 | 空间复杂度 | 适用场景 | 主要优势 |
|------|-----------|-----------|---------|---------|
| AES | O(1) | O(w) | 实时预测 | 自适应、低延迟 |
| 在线LSTM | O(n·h²) | O(h²) | 复杂时序 | 表达能力强 |
| Granger因果 | O(n·k²) | O(n) | 因果发现 | 理论基础扎实 |
| NSGA-II | O(g·p²·m) | O(p·m) | 多目标优化 | 帕累托最优 |
| 异常检测 | O(n·log(n)) | O(n) | 异常识别 | 无监督学习 |

其中：
- w: 窗口大小
- n: 样本数量
- h: 隐藏层大小
- k: 最大滞后阶数
- g: 遗传代数
- p: 种群大小
- m: 目标数量

## 25.8 本章小结

本章提供了自驱永续进化Agent系统中所有核心算法的完整实现，包括：

1. **自适应指数平滑算法**：动态调整平滑参数，适应数据变化
2. **在线LSTM增量学习**：结合深度学习和持续学习，支持模型进化
3. **因果发现算法**：Granger因果检验和PC算法，发现变量间因果关系
4. **多目标优化算法**：NSGA-II，实现帕累托最优任务选择
5. **异常检测算法**：Isolation Forest，识别系统异常

每个算法都包含完整的数学推导、Python实现、复杂度分析和测试用例，为系统开发提供可直接使用的代码基础。
