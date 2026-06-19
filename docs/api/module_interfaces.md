# 模块接口文档

## 目录

- [ModuleInterface](#moduleinterface)
- [IEnvironmentPerception](#ienvironmentperception)
- [IDriveEngine](#idriveengine)
- [IPredictionModel](#ipredictionmodel)
- [IMultiLayerPredictor](#imultilayerpredictor)
- [IErrorEvaluator](#ierrorevaluator)
- [ITaskGenerator](#itaskgenerator)
- [IDecisionEngine](#idecisionengine)
- [IMemorySystem](#imemorysystem)
- [IResourceGuardian](#iresourceguardian)

## ModuleInterface

所有模块的基类接口。

### 属性

- version: 模块版本号
- module_name: 模块标识名

### 方法

- initialize(config): 初始化模块
- health_check(): 健康检查
- shutdown(): 优雅关闭

## IEnvironmentPerception

环境感知模块接口。

### 方法

- perceive(): 执行环境感知
- get_state_history(history_size): 获取历史状态

## IDriveEngine

驱力引擎模块接口。

### 方法

- compute(env_state): 计算驱力信号
- set_base_weights(weights): 设置基础权重

## IPredictionModel

预测模型接口。

### 方法

- predict(state): 预测下一个状态
- update(state, actual): 在线更新
- get_error(): 获取预测误差

## IMultiLayerPredictor

多层预测器接口。

### 方法

- predict_all(state): 生成多层预测
- update_all(state, actual): 更新所有层级

## IErrorEvaluator

误差评估接口。

### 方法

- evaluate(prediction, actual): 评估预测误差

## ITaskGenerator

任务生成接口。

### 方法

- generate(drive_signals, errors): 生成候选任务

## IDecisionEngine

决策引擎接口。

### 方法

- select(tasks, drive_signals): 选择最优任务
- should_interrupt(current_task, new_drives): 中断判断

## IMemorySystem

记忆系统接口。

### 方法

- store(experience): 存储经验
- sample_experiences(sample_size): 采样经验
- offline_review(predictor): 离线复盘

## IResourceGuardian

资源守护接口。

### 方法

- check(): 检查资源状态
- enforce(): 强制执行限制
