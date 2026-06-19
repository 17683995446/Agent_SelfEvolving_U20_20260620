# 第三十七章：术语表与缩略语

## 37.1 核心术语

### 37.1.1 系统架构术语

**Agent（智能体）**
能够感知环境、自主决策并执行动作以实现目标的实体。在本系统中，Agent是持续自驱进化的认知系统。

**自驱（Self-Driven）**
系统不依赖外部任务输入，基于内生驱力自主产生动机和行为。

**永续进化（Perpetual Evolution）**
系统在无限时间范围内持续自我改进，不存在完成态或停滞态。

**预测修正（Prediction-Correction）**
系统持续生成环境预测，通过比对预测与实际值的误差来修正模型。

**双闭环（Dual-Loop）**
系统同时运行在线实时预测修正闭环和离线复盘模型进化闭环。

**原生驱力（Native Drive）**
系统内置的仿生本能，包括安全驱力、收益驱力和能效驱力。

**价值缺口（Value Gap）**
当前状态与终极目标之间的差距，是系统产生行为的根本动机。

**探索-利用平衡（Exploration-Exploitation Trade-off）**
在已知高收益任务（利用）和未知潜在收益任务（探索）之间的权衡。

### 37.1.2 模块术语

**感知模块（Perception Module）**
负责采集、处理和标准化环境状态数据的模块。

**驱力引擎（Drive Engine）**
计算原生驱力、动态权重和价值缺口的模块。

**任务生成器（Task Generator）**
根据价值缺口动态生成候选任务的模块。

**决策模块（Decision Maker）**
负责任务选择、探索-利用平衡和动态中断的模块。

**预测模型（Predictor）**
包含底层、中层、高层三层预测架构的认知核心模块。

**记忆系统（Memory System）**
管理在线短期记忆和离线长期记忆的模块。

**离线复盘（Offline Review）**
在系统空闲时进行的批量模型优化和知识压缩过程。

**安全守护（Safety Guard）**
实施刚性边界约束、防止系统失控的模块。

### 37.1.3 算法术语

**自适应指数平滑（Adaptive Exponential Smoothing, AES）**
动态调整平滑参数的指数平滑算法，用于高频微预测。

**在线LSTM增量学习（Online LSTM Incremental Learning）**
支持持续学习的LSTM实现，包含经验回放和弹性权重巩固。

**弹性权重巩固（Elastic Weight Consolidation, EWC）**
保护重要参数不被覆盖的持续学习技术。

**Granger因果检验（Granger Causality Test）**
检测时间序列之间预测因果关系的统计方法。

**PC算法（Peter-Clark Algorithm）**
基于条件独立性检验的因果发现算法。

**NSGA-II（Non-dominated Sorting Genetic Algorithm II）**
快速非支配排序遗传算法，用于多目标优化。

**隔离森林（Isolation Forest）**
基于随机划分的异常检测算法。

## 37.2 缩略语表

| 缩略语 | 英文全称 | 中文含义 |
|--------|---------|---------|
| AES | Adaptive Exponential Smoothing | 自适应指数平滑 |
| AGI | Artificial General Intelligence | 通用人工智能 |
| AI | Artificial Intelligence | 人工智能 |
| AIoT | Artificial Intelligence of Things | 智能物联网 |
| API | Application Programming Interface | 应用程序接口 |
| CPU | Central Processing Unit | 中央处理器 |
| EWC | Elastic Weight Consolidation | 弹性权重巩固 |
| GPU | Graphics Processing Unit | 图形处理器 |
| JSON | JavaScript Object Notation | JavaScript对象表示法 |
| KL | Kullback-Leibler | 库尔贝克-莱布勒散度 |
| LLM | Large Language Model | 大型语言模型 |
| LSTM | Long Short-Term Memory | 长短期记忆网络 |
| LTL | Linear Temporal Logic | 线性时序逻辑 |
| MAE | Mean Absolute Error | 平均绝对误差 |
| MAPE | Mean Absolute Percentage Error | 平均绝对百分比误差 |
| MSE | Mean Squared Error | 均方误差 |
| NSGA | Non-dominated Sorting Genetic Algorithm | 非支配排序遗传算法 |
| PC | Peter-Clark | 彼得-克拉克算法 |
| RAM | Random Access Memory | 随机存取存储器 |
| R² | R-squared | 决定系数 |
| RMSE | Root Mean Squared Error | 均方根误差 |
| SCM | Structural Causal Model | 结构性因果模型 |
| SOC | Self-Organized Criticality | 自组织临界性 |
| SQL | Structured Query Language | 结构化查询语言 |
| SSD | Solid State Drive | 固态硬盘 |
| UCB | Upper Confidence Bound | 上置信界 |
| YAML | YAML Ain't Markup Language | YAML标记语言 |

## 37.3 数学符号表

| 符号 | 含义 | 上下文 |
|------|------|--------|
| θ | 模型参数 | 预测模型 |
| η | 学习率 | 梯度下降 |
| α | 平滑参数 | 指数平滑 |
| ε | 探索比例 | 探索-利用平衡 |
| σ | 标准差 / Sigmoid函数 | 统计学 / 神经网络 |
| μ | 均值 | 统计学 |
| Σ | 求和 / 协方差矩阵 | 数学 / 统计学 |
| ∇ | 梯度 | 微积分 |
| ∂ | 偏导数 | 微积分 |
| E[·] | 期望 | 概率论 |
| P(·) | 概率 | 概率论 |
| D_KL | KL散度 | 信息论 |
| H(·) | 熵 | 信息论 |
| I(·;·) | 互信息 | 信息论 |
| f(·) | 函数 / 预测模型 | 通用 |
| g(·) | 真实环境函数 | 预测模型 |
| e_t | 时刻t的预测误差 | 预测模型 |
| s_t | 时刻t的平滑值 | 指数平滑 |
| h_t | 时刻t的隐藏状态 | LSTM |
| c_t | 时刻t的细胞状态 | LSTM |
| W | 权重矩阵 | 神经网络 |
| b | 偏置向量 | 神经网络 |
| λ | 正则化系数 | EWC |
| F | Fisher信息矩阵 | EWC |
| R | 奖励 / 收益 | 强化学习 |
| V | 价值函数 | 强化学习 |
| Q | 动作价值函数 | 强化学习 |
| π | 策略 | 强化学习 |
| γ | 折扣因子 | 强化学习 |
| τ | 阈值 | 通用 |
| Δ | 变化量 / 差距 | 通用 |
| ∞ | 无穷大 | 数学 |
| ∈ | 属于 | 集合论 |
| ∀ | 对于所有 | 逻辑 |
| ∃ | 存在 | 逻辑 |
| → | 趋向于 / 蕴含 | 数学 / 逻辑 |
| ⇔ | 当且仅当 | 逻辑 |
| ≈ | 约等于 | 数学 |
| ≤ | 小于等于 | 数学 |
| ≥ | 大于等于 | 数学 |

## 37.4 专业术语对照表

### 37.4.1 中英对照

| 中文 | 英文 |
|------|------|
| 自驱永续进化预测修正Agent | Self-Driven Perpetually Evolving Prediction-Correction Agent |
| 原生驱力 | Native Drive |
| 安全驱力 | Safety Drive |
| 收益驱力 | Gain Drive |
| 能效驱力 | Efficiency Drive |
| 价值缺口 | Value Gap |
| 动态任务池 | Dynamic Task Pool |
| 探索-利用平衡 | Exploration-Exploitation Balance |
| 多层预测模型 | Multi-Level Prediction Model |
| 微修正 | Micro-Adjustment |
| 结构性重构 | Structural Reconstruction |
| 离线复盘 | Offline Review |
| 刚性边界约束 | Rigid Boundary Constraint |
| 模型快照 | Model Snapshot |
| 回滚机制 | Rollback Mechanism |
| 弹性权重巩固 | Elastic Weight Consolidation |
| 经验回放 | Experience Replay |
| 因果发现 | Causal Discovery |
| 异常检测 | Anomaly Detection |
| 多目标优化 | Multi-Objective Optimization |
| 帕累托最优 | Pareto Optimality |
| 自由能原理 | Free Energy Principle |
| 主动推断 | Active Inference |
| 预测编码 | Predictive Coding |
| 内感受推理 | Interoceptive Inference |
| 自组织临界性 | Self-Organized Criticality |
| 耗散结构 | Dissipative Structure |
| 进化稳定策略 | Evolutionarily Stable Strategy |
| 红皇后效应 | Red Queen Effect |
| 全局工作空间 | Global Workspace |

### 37.4.2 跨学科术语

| 领域 | 术语 | 在本系统中的映射 |
|------|------|----------------|
| 神经科学 | 预测加工 | 多层预测模型 |
| 神经科学 | 神经可塑性 | 在线增量学习 |
| 神经科学 | 注意机制 | 动态任务优先级 |
| 心理学 | 驱力理论 | 三大原生驱力 |
| 心理学 | 认知失调 | 预测误差 |
| 控制论 | 反馈回路 | 预测-修正闭环 |
| 控制论 | 自适应控制 | 动态权重调整 |
| 信息论 | 熵 | 环境不确定性 |
| 信息论 | 互信息 | 预测质量 |
| 热力学 | 耗散结构 | 持续信息处理 |
| 热力学 | 负熵 | 模型有序度 |
| 演化生物学 | 自然选择 | 误差筛选 |
| 演化生物学 | 突变 | 随机探索 |
| 经济学 | 边际效用 | 任务收益递减 |
| 经济学 | 机会成本 | 任务选择权衡 |

## 37.5 本章小结

本章提供了自驱永续进化Agent系统的完整术语参考：

1. **核心术语**：系统架构、模块、算法相关术语定义
2. **缩略语表**：常用缩略语及其全称
3. **数学符号表**：文档中使用的数学符号及其含义
4. **专业术语对照表**：中英对照和跨学科映射

这些术语定义为理解和使用本技术方案提供了统一的语言基础。
