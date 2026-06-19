# 第三十章：工程实践与运维指南

## 30.1 开发环境搭建

### 30.1.1 系统要求

**最低配置：**
- CPU: 2核 x86_64
- 内存: 4GB RAM
- 存储: 20GB可用空间
- 操作系统: Linux (Ubuntu 20.04+) / Windows 10+ / macOS 11+
- Python: 3.9+

**推荐配置：**
- CPU: 4核+
- 内存: 8GB+ RAM
- 存储: 50GB+ SSD
- GPU: 可选（CUDA兼容，用于加速LSTM训练）

### 30.1.2 依赖安装

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 安装基础依赖
pip install numpy scipy pandas scikit-learn

# 深度学习框架（可选，用于LSTM）
pip install torch --index-url https://download.pytorch.org/whl/cpu

# 系统监控
pip install psutil

# 数据库
pip install sqlite3

# Web监控面板
pip install flask

# 配置管理
pip install pyyaml

# 日志处理
pip install loguru

# 开发工具
pip install pytest black mypy
```

### 30.1.3 项目结构

```
self-evolving-agent/
├── main.py                 # 主程序入口
├── config/
│   ├── __init__.py
│   ├── default.yaml        # 默认配置
│   └── schema.py           # 配置验证
├── modules/
│   ├── __init__.py
│   ├── perception.py       # 感知模块
│   ├── drive_engine.py     # 驱力引擎
│   ├── task_generator.py   # 任务生成器
│   ├── decision_maker.py   # 决策模块
│   ├── predictor.py        # 预测模型
│   ├── memory.py           # 记忆系统
│   ├── offline_review.py   # 离线复盘
│   └── safety_guard.py     # 安全守护
├── models/                 # 预训练模型存储
├── data/                   # 数据存储
│   ├── memory.db           # SQLite数据库
│   └── snapshots/          # 模型快照
├── logs/                   # 日志文件
├── tests/                  # 测试代码
├── docs/                   # 文档
└── requirements.txt        # 依赖列表
```

## 30.2 配置调优指南

### 30.2.1 驱力权重调优

**通用均衡版（默认）：**
```yaml
drive_weights:
  safe: 0.4
  gain: 0.4
  eff: 0.2
```
适用场景：通用环境，无特殊偏好

**系统运维偏向版：**
```yaml
drive_weights:
  safe: 0.6
  gain: 0.2
  eff: 0.2
```
适用场景：生产环境，稳定性优先

**智能学习进化版：**
```yaml
drive_weights:
  safe: 0.2
  gain: 0.6
  eff: 0.2
```
适用场景：实验环境，快速进化优先

### 30.2.2 资源限制调优

**低配机器（2核4G）：**
```yaml
resource_limits:
  max_cpu_percent: 15.0
  max_memory_percent: 15.0
  max_disk_usage_gb: 10.0
```

**高配机器（8核16G）：**
```yaml
resource_limits:
  max_cpu_percent: 25.0
  max_memory_percent: 25.0
  max_disk_usage_gb: 100.0
```

### 30.2.3 预测模型调优

**快速响应模式：**
```yaml
prediction:
  horizon: 5
  min_history: 20
  model_type: "aes"  # 轻量级模型
```

**高精度模式：**
```yaml
prediction:
  horizon: 20
  min_history: 100
  model_type: "lstm"  # 深度学习模型
  lstm_hidden_size: 128
  lstm_layers: 3
```

## 30.3 监控与告警

### 30.3.1 关键指标监控

```python
# 监控指标采集
class MetricsCollector:
    def collect(self):
        return {
            # 系统级
            'agent_cpu_percent': self.get_agent_cpu(),
            'agent_memory_mb': self.get_agent_memory(),
            'system_cpu_percent': psutil.cpu_percent(),
            'system_memory_percent': psutil.virtual_memory().percent,
            
            # Agent级
            'cycle_count': self.agent.cycle_count,
            'cycles_per_second': self.agent.get_stats()['cycles_per_second'],
            'average_prediction_error': np.mean(self.agent.error_history[-100:]),
            
            # 驱力级
            'safe_drive': self.agent.drive_engine.current_drive.safe,
            'gain_drive': self.agent.drive_engine.current_drive.gain,
            'eff_drive': self.agent.drive_engine.current_drive.eff,
            
            # 任务级
            'active_tasks': len(self.agent.task_generator.active_tasks),
            'completed_tasks': self.agent.task_generator.completed_count,
            'exploration_ratio': self.agent.decision_maker.exploration_ratio,
        }
```

### 30.3.2 告警规则

```yaml
alerts:
  - name: "高预测误差"
    condition: "average_prediction_error > 0.5"
    severity: "warning"
    action: "increase_exploration"
    
  - name: "资源超限"
    condition: "agent_cpu_percent > max_cpu_percent * 0.9"
    severity: "critical"
    action: "reduce_computation"
    
  - name: "长期无进化"
    condition: "error_trend > -0.01 for 1h"
    severity: "warning"
    action: "trigger_structural_rebuild"
    
  - name: "安全驱力过高"
    condition: "safe_drive > 0.8 for 10m"
    severity: "critical"
    action: "notify_admin"
```

### 30.3.3 日志分析

```bash
# 查看Agent状态
 tail -f logs/agent.log | grep "STATE"

# 查看预测误差趋势
grep "PREDICTION_ERROR" logs/agent.log | awk '{print $3}' | tail -100 > errors.txt
python -c "import numpy as np; d=np.loadtxt('errors.txt'); print(f'Mean: {np.mean(d):.4f}, Trend: {d[-1]-d[0]:.4f}')"

# 查看任务执行情况
grep "TASK_EXECUTED" logs/agent.log | sort | uniq -c | sort -rn
```

## 30.4 故障排查

### 30.4.1 常见问题诊断

**问题1：Agent启动后无响应**

排查步骤：
1. 检查配置文件路径：`ls -la config/default.yaml`
2. 检查日志文件权限：`ls -la logs/`
3. 检查数据库初始化：`sqlite3 data/memory.db ".tables"`
4. 检查端口占用：`netstat -tlnp | grep 8080`

**问题2：预测误差持续升高**

排查步骤：
1. 检查环境是否发生突变：`grep "ENV_CHANGE" logs/agent.log`
2. 检查模型是否过拟合：`grep "OVERFIT" logs/agent.log`
3. 检查探索比例是否过低：`grep "EXPLORATION_RATIO" logs/agent.log`
4. 手动触发模型重构：`curl -X POST http://localhost:8080/api/rebuild`

**问题3：内存持续增长**

排查步骤：
1. 检查历史数据积压：`du -sh data/`
2. 检查内存泄漏：`grep "MEMORY_GROWTH" logs/agent.log`
3. 手动触发清理：`curl -X POST http://localhost:8080/api/cleanup`
4. 调整存储清理策略：修改配置`storage_cleanup_keep_ratio`

### 30.4.2 调试模式

```python
# 启用调试模式
import logging
logging.basicConfig(level=logging.DEBUG)

# 单步执行
agent = SelfEvolvingAgent(config)
await agent.initialize()

# 手动执行循环
for i in range(10):
    result = await agent.step()
    print(f"Step {i}: error={result.prediction_error:.4f}, task={result.selected_task}")
    
# 检查内部状态
print(agent.drive_engine.current_drive)
print(agent.predictor.get_metrics())
```

### 30.4.3 性能分析

```python
import cProfile
import pstats

# 性能分析
profiler = cProfile.Profile()
profiler.enable()

# 运行100轮
for _ in range(100):
    await agent.step()
    
profiler.disable()

# 输出统计
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # 输出前20个热点
```

## 30.5 备份与恢复

### 30.5.1 自动备份策略

```python
class BackupManager:
    def __init__(self, config):
        self.backup_dir = config.backup_dir
        self.retention_days = config.backup_retention_days
        
    async def create_backup(self):
        """创建完整备份"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{self.backup_dir}/backup_{timestamp}"
        
        # 备份配置
        shutil.copytree("config", f"{backup_path}/config")
        
        # 备份数据
        shutil.copytree("data", f"{backup_path}/data")
        
        # 备份模型
        shutil.copytree("models", f"{backup_path}/models")
        
        # 备份日志（最近7天）
        os.makedirs(f"{backup_path}/logs", exist_ok=True)
        for log_file in glob("logs/*.log"):
            if os.path.getmtime(log_file) > time.time() - 7*86400:
                shutil.copy2(log_file, f"{backup_path}/logs/")
                
        self.logger.info(f"备份创建完成: {backup_path}")
        
    async def restore_backup(self, backup_path: str):
        """从备份恢复"""
        # 停止Agent
        await self.agent.shutdown()
        
        # 恢复数据
        shutil.copytree(f"{backup_path}/data", "data", dirs_exist_ok=True)
        
        # 恢复模型
        shutil.copytree(f"{backup_path}/models", "models", dirs_exist_ok=True)
        
        # 重启Agent
        await self.agent.initialize()
```

### 30.5.2 灾难恢复流程

```
1. 确认故障范围
   └─ 检查日志确定故障时间点和类型

2. 停止Agent
   └─ systemctl stop self-evolving-agent

3. 选择恢复点
   └─ ls -lt backups/ | head -10

4. 执行恢复
   └─ python -c "from backup import restore; restore('backups/backup_20240101_000000')"

5. 验证恢复
   └─ 检查数据完整性、模型可加载性

6. 启动Agent
   └─ systemctl start self-evolving-agent

7. 监控恢复后状态
   └─ tail -f logs/agent.log
```

## 30.6 升级与迁移

### 30.6.1 版本升级

**小版本升级（1.0.x → 1.0.y）：**
```bash
# 1. 备份当前版本
cp -r self-evolving-agent self-evolving-agent-backup

# 2. 拉取新版本
git pull origin main

# 3. 更新依赖
pip install -r requirements.txt --upgrade

# 4. 数据库迁移（如有）
python scripts/migrate_db.py

# 5. 重启服务
systemctl restart self-evolving-agent
```

**大版本升级（1.x → 2.x）：**
```bash
# 1. 完整备份
python scripts/backup.py --full

# 2. 并行部署新版本
python scripts/deploy.py --version 2.0.0 --parallel

# 3. 数据迁移
python scripts/migrate_v1_to_v2.py

# 4. A/B测试
python scripts/ab_test.py --old v1 --new v2 --duration 24h

# 5. 切换流量
python scripts/switch_traffic.py --version 2.0.0

# 6. 监控验证
python scripts/validate.py --duration 72h
```

### 30.6.2 跨平台迁移

**Linux → Windows：**
```powershell
# 1. 导出数据
sqlite3 data/memory.db ".dump" > backup.sql

# 2. 复制配置文件
Copy-Item config/default.yaml config/windows.yaml

# 3. 修改路径配置
# 将 /path/to/data 改为 C:\path\to\data

# 4. 安装Windows依赖
pip install -r requirements-windows.txt

# 5. 导入数据
sqlite3 data/memory.db < backup.sql
```

## 30.7 本章小结

本章提供了完整的工程实践指南，包括：

1. **开发环境**：系统要求、依赖安装、项目结构
2. **配置调优**：驱力权重、资源限制、预测模型调优
3. **监控告警**：关键指标、告警规则、日志分析
4. **故障排查**：常见问题、调试模式、性能分析
5. **备份恢复**：自动备份、灾难恢复流程
6. **升级迁移**：版本升级、跨平台迁移

这些实践指南确保系统在生产环境中的稳定运行和持续进化。
