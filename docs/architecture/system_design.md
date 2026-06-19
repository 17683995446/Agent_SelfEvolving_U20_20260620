# 系统架构设计文档

## 目录

- [概述](#概述)
- [目录结构](#目录结构)
- [模块划分](#模块划分)
- [数据流](#数据流)
- [接口规范](#接口规范)

## 概述

自驱永续进化Agent系统基于预测编码理论和自由能原理构建，模拟生物大脑的分层预测机制，实现自主感知、决策与进化。

## 目录结构

项目采用满二叉树目录结构，顶层固定为src、tests、config、docs、scripts、assets六个目录。

```
workspace/
├── src/
│   └── agent_core/
│       ├── common/
│       ├── perception/
│       ├── drive/
│       ├── predictor/
│       ├── task/
│       └── memory/
├── tests/
│   └── agent_core/
│       ├── common/
│       ├── perception/
│       ├── drive/
│       ├── predictor/
│       ├── task/
│       └── memory/
├── config/
│   ├── dev.yaml
│   ├── test.yaml
│   └── prod.yaml
├── docs/
│   ├── architecture/
│   ├── api/
│   ├── deploy/
│   └── user/
├── scripts/
│   ├── start_agent.sh
│   ├── stop_agent.sh
│   ├── run_tests.sh
│   └── build_image.sh
└── assets/
```

## 模块划分

### common模块

提供全局共享的数据契约、接口定义与常量枚举。

### perception模块

负责环境状态采集与标准化，包含6类传感器。

### drive模块

计算内生动机信号，包含三大驱力计算器与动态权重调整器。

### predictor模块

多层预测模型，包含底层、中层、高层预测器与集成融合器。

### task模块

任务生成、决策选择与执行。

### memory模块

经验存储、离线复盘与资源守护。

## 数据流

感知 -> 驱力 -> 预测 -> 误差 -> 任务 -> 决策 -> 执行 -> 记忆

## 接口规范

所有模块必须实现ModuleInterface基类，包含initialize、health_check、shutdown三个抽象方法。
