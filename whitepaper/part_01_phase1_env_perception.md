# 第一阶段：基础自驱闭环 —— 环境感知模块详细技术方案

## 1. 模块概述

环境感知模块是整个自驱永续进化Agent系统的感官层，负责实时采集本机全维度状态信息，将其标准化为结构化环境状态向量，为后续的驱力计算和自主决策提供数据基础。本模块采用高频轮询与事件触发相结合的混合运行模式，确保既能捕获突发状态变化，又能持续监控稳态趋势。

## 2. 设计目标

1. 全维度覆盖：采集系统层、日志层、文件层、自身层四大维度的状态信息
2. 实时性保障：关键指标采集延迟不超过1秒
3. 资源可控：感知模块自身CPU占用不超过系统总CPU占用的10%
4. 标准化输出：所有采集数据统一转换为标准化环境状态向量
5. 降噪处理：过滤瞬时抖动，保留有效趋势信号

## 3. 系统层感知子模块

### 3.1 CPU状态采集

#### 3.1.1 采集指标

- 整体CPU使用率（百分比）
- 单核CPU使用率分布（各核心分别采集）
- CPU负载平均值（1分钟、5分钟、15分钟）
- CPU频率状态（当前频率/基准频率）
- CPU温度（如传感器可用）
- CPU上下文切换频率
- CPU中断频率

#### 3.1.2 采集方法

Linux平台使用psutil库读取/proc/stat文件，Windows平台使用WMI或pdh接口。采集频率设定为每秒一次，采用滑动窗口平均法进行降噪处理。

#### 3.1.3 标准化处理

原始CPU使用率数据经过以下标准化流程：

1. 异常值检测：使用3σ原则识别并标记异常跳变点
2. 滑动平均：采用5秒滑动窗口计算移动平均值
3. 归一化：将百分比数据映射到[0, 1]区间
4. 趋势提取：计算当前值与前一时刻值的一阶差分

### 3.2 内存状态采集

#### 3.2.1 采集指标

- 物理内存总量
- 物理内存可用量
- 物理内存使用率
- 交换空间总量
- 交换空间使用量
- 内存分页频率
- 内存缓存/缓冲区占用
- 进程级内存占用Top10

#### 3.2.2 采集方法

Linux平台读取/proc/meminfo和/proc/[pid]/status，Windows平台使用GlobalMemoryStatusEx API。

#### 3.2.3 标准化处理

内存数据标准化流程：

1. 使用率计算：used / total × 100%
2. 可用比例映射：available / total → [0, 1]
3. 交换压力指数：swap_used / swap_total（若无交换空间则标记为0）
4. 内存紧张度：综合使用率、可用量、交换压力的三维指标

### 3.3 磁盘状态采集

#### 3.3.1 采集指标

- 各分区总容量
- 各分区已用容量
- 各分区使用率
- 磁盘I/O读取速率
- 磁盘I/O写入速率
- 磁盘I/O等待时间
- 磁盘队列深度
- inode使用率

#### 3.3.2 采集方法

使用psutil.disk_usage()获取容量信息，读取/proc/diskstats获取I/O统计。

#### 3.3.3 标准化处理

磁盘数据标准化：

1. 容量使用率归一化
2. I/O速率标准化（基于历史峰值进行相对化）
3. I/O等待时间分级（低/中/高/严重）
4. 磁盘健康度综合评分

### 3.4 网络状态采集

#### 3.4.1 采集指标

- 各网卡接收速率
- 各网卡发送速率
- 网络连接数（TCP/UDP分别统计）
- 网络错误包计数
- 网络丢包计数
- 网络延迟（本地环回测试）
- DNS解析状态

#### 3.4.2 采集方法

读取/proc/net/dev获取流量统计，使用socket连接测试网络连通性。

#### 3.4.3 标准化处理

网络数据标准化：

1. 流量速率相对化（相对于网卡带宽上限）
2. 连接数分级（正常/偏高/过高）
3. 错误率计算：error_packets / total_packets
4. 网络健康度评分

### 3.5 进程状态采集

#### 3.5.1 采集指标

- 总进程数
- 活跃进程数
- 僵尸进程数
- 各进程CPU占用Top20
- 各进程内存占用Top20
- 进程启动/终止事件
- 异常进程行为（CPU突增、内存泄漏模式）

#### 3.5.2 采集方法

遍历/proc目录获取进程列表，读取各进程的stat和status文件。

#### 3.5.3 标准化处理

进程数据标准化：

1. 进程密度指数：进程数 / 历史平均进程数
2. 僵尸进程风险等级
3. 进程行为异常度评分
4. 新进程发现标记

## 4. 日志层感知子模块

### 4.1 系统日志采集

#### 4.1.1 采集范围

- /var/log/syslog（或messages）
- /var/log/auth.log
- /var/log/kern.log
- dmesg输出
- 应用程序自定义日志

#### 4.1.2 采集方法

采用增量读取方式，记录上次读取位置，仅采集新增日志内容。使用正则表达式匹配关键日志模式。

#### 4.1.3 关键模式识别

预定义关键日志模式库：

1. 错误模式：包含"error"、"failed"、"fatal"等关键词
2. 警告模式：包含"warning"、"warn"等关键词
3. 异常模式：包含"exception"、"panic"、"crash"等关键词
4. 安全模式：包含"unauthorized"、"attack"、"breach"等关键词
5. 资源模式：包含"out of memory"、"disk full"、"timeout"等关键词

#### 4.1.4 标准化处理

日志数据标准化：

1. 日志频率统计：单位时间内各类日志出现次数
2. 日志趋势分析：与历史同期对比的增减趋势
3. 日志严重性评分：综合错误类型、频率、持续时间的加权评分
4. 新增异常模式标记：首次出现的日志模式

### 4.2 日志序列分析

#### 4.2.1 序列建模

将日志事件视为时间序列，建立以下模型：

1. 日志频率时间序列：每分钟各类日志的数量变化
2. 日志严重性时间序列：每分钟加权严重性评分的变化
3. 日志模式序列：日志模式的出现顺序和间隔

#### 4.2.2 异常检测

基于历史统计建立基线，检测以下异常：

1. 日志频率突增：当前频率超过历史均值+3σ
2. 日志模式突变：出现历史未见的日志模式
3. 日志序列异常：正常日志序列中出现异常插入
4. 日志静默异常：应该出现的日志未出现

## 5. 文件层感知子模块

### 5.1 文件变更监控

#### 5.1.1 监控范围

- 系统关键配置文件（/etc目录）
- 用户工作目录
- 临时文件目录
- Agent自身工作目录

#### 5.1.2 监控方法

使用inotify（Linux）或ReadDirectoryChangesW（Windows）实现事件驱动监控，结合定时全量扫描确保不遗漏。

#### 5.1.3 采集指标

- 文件创建事件
- 文件删除事件
- 文件修改事件
- 文件重命名事件
- 文件属性变更事件
- 目录结构变更

#### 5.1.4 标准化处理

文件变更数据标准化：

1. 变更频率统计：单位时间内各类变更事件数量
2. 变更热点识别：变更最频繁的文件/目录
3. 异常变更检测：非预期位置的文件变更
4. 文件规模变化：新增/删除文件的总大小

### 5.2 目录状态采集

#### 5.2.1 采集指标

- 各目录文件数量
- 各目录总大小
- 目录深度分布
- 文件类型分布
- 文件年龄分布

#### 5.2.2 标准化处理

1. 目录规模指数：相对于历史规模的相对值
2. 文件活跃度：近期修改文件占比
3. 存储压力指数：综合容量使用率和增长趋势

## 6. 自身层感知子模块

### 6.1 Agent自身状态采集

#### 6.1.1 采集指标

- Agent进程CPU占用
- Agent进程内存占用
- Agent线程数量
- Agent运行时长
- Agent各模块执行耗时
- Agent任务队列长度
- Agent当前执行的任务类型

#### 6.1.2 标准化处理

1. 自身资源占用率：相对于系统总量的占比
2. 模块执行效率：单位时间处理的任务数
3. 任务队列压力：队列长度相对于处理能力的比值

### 6.2 模型状态采集

#### 6.2.1 采集指标

- 各预测模型当前误差
- 各预测模型历史误差趋势
- 模型参数规模
- 模型推理耗时
- 模型预测置信度分布

#### 6.2.2 标准化处理

1. 模型精度指数：1 - 归一化误差
2. 模型效率指数：预测精度 / 推理耗时
3. 模型稳定性：误差的标准差

## 7. 数据标准化与输出

### 7.1 环境状态向量定义

环境状态向量是一个多维浮点数组，包含所有标准化后的感知数据：

```
State_Vector = [
  # 系统层（32维）
  cpu_overall, cpu_core_1, ..., cpu_core_n,
  cpu_load_1m, cpu_load_5m, cpu_load_15m,
  cpu_freq_ratio, cpu_temp, cpu_ctx_switch,
  mem_usage, mem_available_ratio, mem_swap_pressure,
  disk_usage_root, disk_usage_home, disk_io_read, disk_io_write,
  net_rx_rate, net_tx_rate, net_conn_count, net_error_rate,
  process_count, process_zombie_ratio, process_top_cpu, process_top_mem,
  
  # 日志层（16维）
  log_error_freq, log_warn_freq, log_exception_freq,
  log_security_freq, log_resource_freq,
  log_error_trend, log_severity_score,
  log_new_pattern_flag, log_frequency_anomaly,
  log_sequence_anomaly, log_silence_anomaly,
  
  # 文件层（12维）
  file_create_freq, file_delete_freq, file_modify_freq,
  file_rename_freq, file_hotspot_index,
  dir_size_change, file_age_activity,
  
  # 自身层（16维）
  self_cpu_usage, self_mem_usage, self_thread_count,
  self_runtime, self_module_efficiency, self_queue_pressure,
  model_error_overall, model_error_trend, model_param_size,
  model_inference_time, model_confidence_mean,
  model_precision_index, model_efficiency_index, model_stability,
  
  # 时间特征（8维）
  hour_of_day, day_of_week, is_weekend,
  time_since_start, cycle_phase
]
```

### 7.2 数据流架构

```
原始采集 → 清洗过滤 → 标准化转换 → 特征工程 → 状态向量输出
    ↓           ↓            ↓            ↓
  多源异构   异常值处理   归一化映射   趋势特征提取
```

### 7.3 降噪处理算法

#### 7.3.1 滑动窗口平均

对高频抖动指标使用滑动窗口平均：

```
smoothed_value[t] = α × raw_value[t] + (1-α) × smoothed_value[t-1]
```

其中α为平滑系数，根据指标特性动态调整。

#### 7.3.2 异常值检测

使用改进的Z-score方法：

```
MAD = median(|x_i - median(x)|)
MZi = 0.6745 × (x_i - median(x)) / MAD
```

当|MZi| > 3.5时标记为异常值。

#### 7.3.3 趋势提取

使用一阶差分和二阶差分提取趋势：

```
first_order[t] = value[t] - value[t-1]
second_order[t] = first_order[t] - first_order[t-1]
```

## 8. 性能优化策略

### 8.1 分级采集策略

根据指标重要性和变化频率，采用分级采集：

- 高频采集（每秒）：CPU、内存、Agent自身状态
- 中频采集（每5秒）：磁盘I/O、网络流量、进程状态
- 低频采集（每30秒）：磁盘容量、目录结构、文件统计
- 事件驱动：文件变更、日志新增、进程启停

### 8.2 增量更新机制

对于变化缓慢的指标，采用增量更新策略：

1. 记录上次采集值
2. 仅当变化超过阈值时才更新
3. 超过最大间隔强制全量更新

### 8.3 缓存与复用

建立多级缓存体系：

- L1缓存：最近1秒的数据，内存驻留
- L2缓存：最近1分钟的数据，内存驻留
- L3缓存：历史统计数据，本地存储

## 9. 接口定义

### 9.1 对外接口

```python
class EnvironmentPerception:
    def __init__(self, config: PerceptionConfig):
        """初始化感知模块"""
        pass
    
    def start(self):
        """启动感知循环"""
        pass
    
    def stop(self):
        """停止感知循环"""
        pass
    
    def get_current_state(self) -> StateVector:
        """获取当前环境状态向量"""
        pass
    
    def get_state_history(self, duration: timedelta) -> List[StateVector]:
        """获取历史状态序列"""
        pass
    
    def register_callback(self, event_type: str, callback: Callable):
        """注册状态变更回调"""
        pass
```

### 9.2 配置参数

```python
@dataclass
class PerceptionConfig:
    # 采集频率配置
    cpu_sample_interval: float = 1.0
    memory_sample_interval: float = 1.0
    disk_sample_interval: float = 5.0
    network_sample_interval: float = 5.0
    process_sample_interval: float = 5.0
    log_scan_interval: float = 1.0
    file_scan_interval: float = 30.0
    
    # 降噪参数
    smoothing_alpha: float = 0.3
    anomaly_threshold: float = 3.5
    
    # 资源限制
    max_cpu_usage_percent: float = 2.0  # 感知模块自身CPU上限
    max_memory_usage_mb: float = 100.0
    
    # 监控范围
    monitored_directories: List[str] = None
    monitored_logs: List[str] = None
```

## 10. 测试与验证

### 10.1 单元测试

1. 各采集子模块独立测试
2. 标准化算法正确性验证
3. 异常值检测准确率测试

### 10.2 集成测试

1. 全模块协同运行测试
2. 高负载场景下的性能测试
3. 长时间运行的稳定性测试

### 10.3 验证指标

1. 采集延迟：99%的采集操作在1秒内完成
2. 数据完整性：关键指标丢包率低于0.1%
3. 资源占用：感知模块CPU占用不超过2%
4. 准确性：标准化后的数据与原始数据误差小于1%

## 11. 部署与运行

### 11.1 依赖要求

- Python 3.8+
- psutil库
- 平台特定库（pyinotify for Linux, pywin32 for Windows）

### 11.2 启动流程

1. 加载配置文件
2. 初始化各感知子模块
3. 建立数据缓存
4. 启动采集循环
5. 注册系统信号处理

### 11.3 监控与运维

1. 感知模块自身状态监控
2. 采集质量指标统计
3. 异常自动告警

---

本模块作为整个Agent系统的数据入口，其设计质量直接影响后续所有模块的决策准确性。通过全维度、标准化、低延迟的环境状态采集，为Agent的自主决策和持续进化提供坚实的数据基础。
