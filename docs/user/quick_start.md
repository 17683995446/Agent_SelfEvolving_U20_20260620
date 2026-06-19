# 快速开始指南

## 目录

- [安装依赖](#安装依赖)
- [运行测试](#运行测试)
- [启动Agent](#启动agent)
- [健康检查](#健康检查)

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行测试

```bash
bash scripts/run_tests.sh
```

## 启动Agent

```bash
bash scripts/start_agent.sh
```

## 健康检查

```bash
python3 -c "
import asyncio
from agent_core.memory.agent_main import SelfEvolvingAgent
agent = SelfEvolvingAgent()
asyncio.run(agent.initialize({}))
health = asyncio.run(agent.health_check())
print(health)
"
```
