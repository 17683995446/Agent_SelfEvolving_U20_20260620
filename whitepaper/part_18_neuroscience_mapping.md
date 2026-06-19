# 神经科学映射与仿生机制

## 1. 大脑皮层层次映射

### 1.1 感觉皮层与Agent感知层

人类大脑的感觉皮层（Sensory Cortex）负责接收和处理来自感官的信息。初级感觉皮层（V1、S1、A1）处理原始感官特征，而高级感觉联合区则整合多模态信息。

在Agent系统中，这一映射关系如下：

| 大脑结构 | Agent模块 | 功能对应 |
|---------|----------|---------|
| 初级视觉皮层V1 | CPU/内存原始采样 | 原始数值特征提取 |
| 初级体感皮层S1 | 磁盘/网络采样 | 物理状态感知 |
| 听觉联合区 | 日志模式识别 | 时间序列模式检测 |
| 多模态联合区 | 状态向量融合 | 多源信息整合 |

#### 1.1.1 感受野机制

大脑神经元的感受野（Receptive Field）决定了其对特定刺激的响应。Agent系统中的对应机制：

```python
class ReceptiveField:
    """感受野模型"""
    
    def __init__(self, center, size, sensitivity):
        self.center = center  # 感受野中心（关注的指标）
        self.size = size      # 感受野大小（关注范围）
        self.sensitivity = sensitivity  # 敏感度
    
    def respond(self, stimulus):
        """对刺激产生响应"""
        distance = abs(stimulus - self.center)
        if distance > self.size:
            return 0
        
        # 高斯响应函数
        response = self.sensitivity * exp(-distance**2 / (2 * self.size**2))
        return response
```

#### 1.1.2 侧向抑制

大脑中的侧向抑制（Lateral Inhibition）增强了边缘检测和对比度。Agent系统中的实现：

```python
def lateral_inhibition(activations, inhibition_strength=0.3):
    """侧向抑制增强对比度"""
    n = len(activations)
    enhanced = activations.copy()
    
    for i in range(n):
        # 邻近神经元的抑制
        neighbors = []
        if i > 0:
            neighbors.append(activations[i-1])
        if i < n - 1:
            neighbors.append(activations[i+1])
        
        inhibition = inhibition_strength * mean(neighbors)
        enhanced[i] = max(0, activations[i] - inhibition)
    
    return enhanced
```

### 1.2 前额叶皮层与Agent决策层

前额叶皮层（Prefrontal Cortex, PFC）负责执行功能、工作记忆和决策。Agent的决策引擎对应PFC的功能：

#### 1.2.1 工作记忆

PFC的工作记忆维持当前任务相关信息。Agent的短期记忆对应：

```python
class WorkingMemory:
    """工作记忆模型"""
    
    def __init__(self, capacity=7):
        """
        容量默认为7，对应Miller定律
        人类短期记忆容量为7±2个组块
        """
        self.capacity = capacity
        self.items = []
        self.focus = None
    
    def hold(self, item, priority=0):
        """保持信息"""
        if len(self.items) >= self.capacity:
            # 淘汰优先级最低的项目
            self.items.sort(key=lambda x: x['priority'])
            self.items.pop(0)
        
        self.items.append({
            'data': item,
            'priority': priority,
            'timestamp': time.time()
        })
    
    def focus_on(self, item_id):
        """聚焦注意力"""
        for item in self.items:
            if item['data'].id == item_id:
                self.focus = item
                item['priority'] += 1  # 提升优先级
                return True
        return False
    
    def decay(self):
        """记忆衰减"""
        current_time = time.time()
        for item in self.items:
            age = current_time - item['timestamp']
            item['priority'] *= exp(-age / 10)  # 指数衰减
```

#### 1.2.2 执行控制

PFC的执行控制功能对应Agent的任务调度和中断机制：

```python
class ExecutiveControl:
    """执行控制模型"""
    
    def __init__(self):
        self.current_task = None
        self.inhibition_level = 0  # 抑制水平
        self.conflict_monitor = ConflictMonitor()
    
    def switch_task(self, new_task, reason):
        """任务切换"""
        # 冲突检测
        conflict = self.conflict_monitor.detect(
            self.current_task, new_task
        )
        
        if conflict > CONFLICT_THRESHOLD:
            # 增加认知控制
            self.inhibition_level += 0.1
            
            # 如果冲突过大，延迟切换
            if self.inhibition_level > 0.5:
                return False
        
        # 执行任务切换
        self._inhibit_current_task()
        self.current_task = new_task
        self.inhibition_level *= 0.8  # 衰减
        
        return True
    
    def _inhibit_current_task(self):
        """抑制当前任务"""
        if self.current_task:
            self.current_task.suspend()
```

### 1.3 边缘系统与Agent驱力层

边缘系统（Limbic System）负责情绪和动机。Agent的驱力引擎对应边缘系统的功能：

#### 1.3.1 杏仁核与安全驱力

杏仁核（Amygdala）负责恐惧和威胁检测。对应Agent的安全驱力：

```python
class AmygdalaAnalog:
    """杏仁核类比模型"""
    
    def __init__(self):
        self.threat_threshold = 0.3
        self.fear_response = 0
        self.habituation_rate = 0.1
    
    def process_threat(self, threat_signal):
        """处理威胁信号"""
        if threat_signal > self.threat_threshold:
            # 恐惧反应
            self.fear_response = min(1.0, 
                self.fear_response + (threat_signal - self.threat_threshold))
            
            # 触发战斗或逃跑反应
            return self._fight_or_flight()
        else:
            # 习惯化
            self.fear_response *= (1 - self.habituation_rate)
            return 'calm'
    
    def _fight_or_flight(self):
        """战斗或逃跑决策"""
        if self.fear_response > 0.7:
            return 'flight'  # 逃避：降低活动，保存资源
        else:
            return 'fight'   # 战斗：增加监控，消除威胁
```

#### 1.3.2 多巴胺系统与收益驱力

多巴胺系统负责奖励预测和动机。对应Agent的收益驱力：

```python
class DopamineSystem:
    """多巴胺系统类比模型"""
    
    def __init__(self):
        self.baseline_dopamine = 0.5
        self.prediction_error_history = []
    
    def compute_reward_prediction_error(self, expected_reward, actual_reward):
        """
        计算奖励预测误差（RPE）
        
        δ = R_actual - R_expected
        
        正RPE → 多巴胺释放 → 学习
        负RPE → 多巴胺抑制 → 修正
        """
        rpe = actual_reward - expected_reward
        self.prediction_error_history.append(rpe)
        
        # 多巴胺释放量
        if rpe > 0:
            dopamine = self.baseline_dopamine + rpe * 0.5
        else:
            dopamine = self.baseline_dopamine + rpe * 0.3
        
        return {
            'rpe': rpe,
            'dopamine': dopamine,
            'learning_signal': rpe * dopamine
        }
    
    def update_baseline(self, recent_rewards):
        """更新多巴胺基线"""
        # 基线适应：长期奖励期望的调整
        self.baseline_dopamine = 0.9 * self.baseline_dopamine + 0.1 * mean(recent_rewards)
```

## 2. 神经可塑性与Agent学习机制

### 2.1 赫布学习

赫布理论（Hebbian Learning）："一起激发的神经元连在一起"（Neurons that fire together wire together）。

Agent中的实现：

```python
class HebbianLearning:
    """赫布学习规则"""
    
    def __init__(self, learning_rate=0.01):
        self.lr = learning_rate
    
    def update_weights(self, pre_synaptic, post_synaptic, weights):
        """
        Δw = η × pre × post
        
        如果前神经元和后神经元同时激活，
        则它们之间的连接权重增强
        """
        for i, pre in enumerate(pre_synaptic):
            for j, post in enumerate(post_synaptic):
                # 赫布更新
                delta_w = self.lr * pre * post
                
                # 衰减防止无限增长
                decay = 0.001 * weights[i][j]
                
                weights[i][j] += delta_w - decay
        
        return weights
```

### 2.2 长时程增强/抑制（LTP/LTD）

LTP和LTD是突触可塑性的两种形式，对应Agent的模型强化和弱化：

```python
class SynapticPlasticity:
    """突触可塑性模型"""
    
    def __init__(self):
        self.ltp_threshold = 0.7
        self.ltd_threshold = 0.3
        self.calcium_trace = 0
    
    def update_synapse(self, pre_activity, post_activity, weight):
        """
        基于活动的突触可塑性
        
        高钙 → LTP（权重增加）
        低钙 → LTD（权重减少）
        中间 → 无变化
        """
        # 钙浓度模拟
        calcium = pre_activity * post_activity
        self.calcium_trace = 0.9 * self.calcium_trace + 0.1 * calcium
        
        if self.calcium_trace > self.ltp_threshold:
            # LTP：长时程增强
            weight *= (1 + 0.1 * (self.calcium_trace - self.ltp_threshold))
        elif self.calcium_trace < self.ltd_threshold:
            # LTD：长时程抑制
            weight *= (1 - 0.1 * (self.ltd_threshold - self.calcium_trace))
        
        return clip(weight, 0, 1)
```

### 2.3 睡眠与记忆巩固

睡眠期间，大脑重放白天的经历，巩固记忆。对应Agent的离线复盘：

```python
class SleepConsolidation:
    """睡眠记忆巩固模型"""
    
    def __init__(self):
        self.replay_buffer = []
        self.consolidation_rate = 0.1
    
    def add_experience(self, experience):
        """添加日间经历"""
        self.replay_buffer.append(experience)
    
    def consolidate(self, model):
        """
        睡眠期间的记忆巩固
        
        1. 重放（Replay）：重放重要经历
        2. 系统巩固：从短期记忆转移到长期记忆
        3. 泛化：提取一般规律
        """
        # 选择重要经历重放
        important_experiences = self._select_important()
        
        for exp in important_experiences:
            # 重放学习
            model.replay_learn(exp)
            
            # 干扰消除：减少新旧记忆的冲突
            model.resolve_interference()
        
        # 突触稳态：全局缩放防止饱和
        model.synaptic_homeostasis()
    
    def _select_important(self):
        """选择重要经历"""
        # 基于惊讶度选择
        surprising = [e for e in self.replay_buffer 
                     if e.prediction_error > 0.5]
        
        # 基于奖励选择
        rewarding = [e for e in self.replay_buffer 
                    if e.reward > 0.7]
        
        return list(set(surprising + rewarding))
```

## 3. 预测编码与Agent预测机制

### 3.1 大脑预测编码

预测编码理论认为，大脑不是被动接收信息，而是主动预测感官输入，只传递预测误差。

### 3.2 层级预测架构

```python
class HierarchicalPredictiveCoding:
    """层级预测编码模型"""
    
    def __init__(self, n_levels):
        self.levels = [PredictiveLevel(i) for i in range(n_levels)]
    
    def predict(self, bottom_up_input):
        """
        层级预测过程
        
        1. 底层接收感官输入
        2. 每层生成预测并向上传递
        3. 预测误差向下传递
        4. 各层更新预测模型
        """
        prediction_errors = []
        
        for level in self.levels:
            # 生成预测
            prediction = level.generate_prediction()
            
            # 计算预测误差
            if level.level == 0:
                error = bottom_up_input - prediction
            else:
                error = self.levels[level.level-1].prediction_error
            
            # 传递误差
            level.update_prediction(error)
            prediction_errors.append(error)
        
        return prediction_errors
    
    def learn(self, prediction_errors):
        """基于预测误差学习"""
        for level, error in zip(self.levels, prediction_errors):
            # 精度加权学习
            precision = level.compute_precision(error)
            level.update_weights(error, precision)


class PredictiveLevel:
    """预测层级"""
    
    def __init__(self, level):
        self.level = level
        self.weights = None
        self.precision = 1.0
    
    def generate_prediction(self):
        """生成预测"""
        pass
    
    def compute_precision(self, error):
        """
        计算预测精度
        
        精度 = 1 / 方差
        高精度预测 → 大权重更新
        低精度预测 → 小权重更新
        """
        variance = np.var(error)
        self.precision = 1.0 / (variance + 1e-6)
        return self.precision
```

## 4. 注意机制与Agent资源分配

### 4.1 选择性注意

大脑的选择性注意机制对应Agent的资源分配：

```python
class AttentionMechanism:
    """注意机制模型"""
    
    def __init__(self, capacity):
        self.capacity = capacity
        self.attention_map = {}
        self.saliency_map = {}
    
    def compute_saliency(self, stimuli):
        """
        计算显著性
        
        显著性 = 新奇性 + 重要性 + 紧急性
        """
        for stimulus in stimuli:
            novelty = stimulus.unexpectedness
            importance = stimulus.relevance_to_goals
            urgency = stimulus.time_pressure
            
            self.saliency_map[stimulus.id] = (
                0.4 * novelty + 
                0.4 * importance + 
                0.2 * urgency
            )
    
    def allocate_attention(self):
        """分配注意资源"""
        # 按显著性排序
        sorted_stimuli = sorted(
            self.saliency_map.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # 分配注意容量
        total_attention = 0
        for stimulus_id, saliency in sorted_stimuli:
            if total_attention >= self.capacity:
                self.attention_map[stimulus_id] = 0
            else:
                attention = min(saliency, self.capacity - total_attention)
                self.attention_map[stimulus_id] = attention
                total_attention += attention
```

### 4.2 注意瞬脱

注意瞬脱（Attentional Blink）是指快速连续呈现刺激时，对第二个刺激的检测能力下降。Agent中的对应现象：

```python
class AttentionalBlink:
    """注意瞬脱模型"""
    
    def __init__(self):
        self.refractory_period = 0.5  # 不应期（秒）
        self.last_attention_shift = 0
    
    def can_attend(self, stimulus):
        """判断是否能注意新刺激"""
        time_since_last = time.time() - self.last_attention_shift
        
        if time_since_last < self.refractory_period:
            # 注意瞬脱期间
            blink_probability = 1 - (time_since_last / self.refractory_period)
            
            if random() < blink_probability:
                return False  # 错过刺激
        
        self.last_attention_shift = time.time()
        return True
```

## 5. 神经振荡与Agent节律

### 5.1 脑电节律

不同频率的脑电波对应不同的认知状态：

| 节律 | 频率 | 认知状态 | Agent对应 |
|-----|------|---------|----------|
| Delta | 0.5-4Hz | 深度睡眠 | 离线复盘 |
| Theta | 4-8Hz | 冥想、记忆 | 模式识别 |
| Alpha | 8-13Hz | 放松、抑制 | 稳态监控 |
| Beta | 13-30Hz | 活跃思考 | 任务执行 |
| Gamma | 30-100Hz | 注意、绑定 | 多模态整合 |

### 5.2 Agent节律控制

```python
class NeuralOscillation:
    """神经振荡模型"""
    
    def __init__(self):
        self.phase = 0
        self.frequency = 1.0  # Hz
        self.amplitude = 1.0
    
    def oscillate(self, dt):
        """振荡更新"""
        self.phase += 2 * pi * self.frequency * dt
        self.phase %= 2 * pi
        
        return self.amplitude * sin(self.phase)
    
    def set_frequency(self, state):
        """根据状态调整频率"""
        if state == 'sleep':
            self.frequency = 0.5  # Delta
        elif state == 'relaxed':
            self.frequency = 10   # Alpha
        elif state == 'active':
            self.frequency = 20   # Beta
        elif state == 'focused':
            self.frequency = 40   # Gamma


class AgentRhythmController:
    """Agent节律控制器"""
    
    def __init__(self):
        self.oscillations = {
            'delta': NeuralOscillation(),
            'theta': NeuralOscillation(),
            'alpha': NeuralOscillation(),
            'beta': NeuralOscillation(),
            'gamma': NeuralOscillation(),
        }
        
        self.current_state = 'active'
    
    def update_rhythms(self, system_state):
        """更新节律"""
        # 根据系统状态调整各节律
        if system_state.cpu_usage < 0.2:
            self.current_state = 'relaxed'
            self.oscillations['alpha'].amplitude = 1.0
            self.oscillations['beta'].amplitude = 0.3
        else:
            self.current_state = 'active'
            self.oscillations['alpha'].amplitude = 0.3
            self.oscillations['beta'].amplitude = 1.0
    
    def get_sampling_phase(self):
        """获取采样相位"""
        # 在Alpha波峰值时采样（抑制期）
        alpha_phase = self.oscillations['alpha'].phase
        return alpha_phase
```

## 6. 神经调质与Agent全局状态

### 6.1 乙酰胆碱与预测精度

乙酰胆碱（ACh）调节感觉皮层的预测精度。高ACh → 高感觉权重 → 更多关注感官证据。

```python
class AcetylcholineSystem:
    """乙酰胆碱系统类比"""
    
    def __init__(self):
        self.level = 0.5
    
    def modulate_precision(self, base_precision, uncertainty):
        """
        调节预测精度
        
        不确定性高 → ACh升高 → 感觉精度升高
        不确定性低 → ACh降低 → 感觉精度降低
        """
        self.level = 0.3 + 0.7 * uncertainty
        
        # ACh增强感觉精度
        modulated_precision = base_precision * (1 + self.level)
        
        return modulated_precision
```

### 6.2 去甲肾上腺素与意外性

去甲肾上腺素（NE）响应意外性（Surprise）。高NE → 重置内部模型 → 探索新策略。

```python
class NorepinephrineSystem:
    """去甲肾上腺素系统类比"""
    
    def __init__(self):
        self.level = 0.5
        self.tonic_level = 0.5
    
    def respond_to_surprise(self, surprise):
        """
        响应意外性
        
        意外性高 → NE爆发 → 重置注意力
        意外性低 → NE维持 → 持续利用
        """
        if surprise > 0.7:
            # 相位性NE释放
            self.level = min(1.0, self.tonic_level + surprise * 0.5)
            
            # 触发重置
            return 'reset'
        else:
            # 紧张性NE维持
            self.level = self.tonic_level
            return 'maintain'
```

### 6.3 血清素与长期价值

血清素（5-HT）调节时间折扣和耐心。高5-HT → 长期价值权重增加 → 延迟满足。

```python
class SerotoninSystem:
    """血清素系统类比"""
    
    def __init__(self):
        self.level = 0.5
    
    def discount_rewards(self, rewards, time_horizon):
        """
        时间折扣
        
        血清素水平影响折扣率
        高5-HT → 低折扣率 → 重视长期
        低5-HT → 高折扣率 → 重视短期
        """
        # 折扣率与血清素水平负相关
        discount_rate = 0.9 - 0.4 * self.level
        
        discounted = []
        for t, reward in enumerate(rewards):
            discounted.append(reward * (discount_rate ** t))
        
        return discounted
```

---

神经科学映射与仿生机制部分深入探讨了Agent系统与大脑神经机制的对应关系，从感觉皮层到前额叶，从多巴胺系统到神经振荡，为Agent的设计提供了坚实的生物学基础。
