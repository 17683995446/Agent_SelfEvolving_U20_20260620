# 第四十三章：故障排查与诊断指南

## 43.1 故障分类体系

### 43.1.1 故障严重程度分级

| 级别 | 名称 | 定义 | 响应时间 | 示例 |
|------|------|------|---------|------|
| P0 | 致命 | 系统完全不可用 | 立即 | 系统崩溃、数据丢失 |
| P1 | 严重 | 核心功能受损 | 1小时 | 预测完全失效、安全突破 |
| P2 | 中等 | 非核心功能异常 | 4小时 | 监控面板无法访问、日志丢失 |
| P3 | 轻微 | 性能下降或警告 | 24小时 | 响应延迟增加、偶发错误 |
| P4 | 提示 | 优化建议 | 下次迭代 | 配置可优化、资源可释放 |

### 43.1.2 故障类型分类

**按模块分类：**
- 感知模块故障
- 驱力引擎故障
- 任务系统故障
- 预测模型故障
- 记忆系统故障
- 安全守护故障
- API服务故障

**按性质分类：**
- 配置错误
- 资源不足
- 逻辑错误
- 数据异常
- 外部依赖故障
- 并发问题

## 43.2 常见故障诊断

### 43.2.1 系统无法启动

**症状：**
- 执行启动命令后无响应
- 进程立即退出
- 日志文件未生成

**诊断流程：**

```
1. 检查日志
   └─ tail -n 100 logs/agent.log
   └─ 如果日志不存在，检查日志目录权限

2. 检查配置
   └─ python scripts/validate_config.py config/default.yaml
   └─ 检查YAML语法是否正确

3. 检查依赖
   └─ pip check
   └─ python -c "import psutil, numpy, torch"
   └─ 检查Python版本 >= 3.9

4. 检查资源
   └─ df -h  # 磁盘空间
   └─ free -h  # 内存
   └─ ulimit -a  # 系统限制

5. 检查端口
   └─ netstat -tlnp | grep 8080
   └─ lsof -i :8080

6. 最小化测试
   └─ python main.py --config config/minimal.yaml
   └─ 如果最小化配置可以启动，逐步添加配置项
```

**常见原因及解决方案：**

| 原因 | 诊断方法 | 解决方案 |
|------|---------|---------|
| 配置错误 | validate_config报错 | 修正配置文件 |
| 依赖缺失 | import报错 | pip install -r requirements.txt |
| 权限不足 | Permission denied | chmod/chown修正权限 |
| 端口占用 | netstat显示占用 | 停止占用进程或更换端口 |
| 数据库锁定 | .lock文件存在 | 删除data/*.lock |
| 磁盘已满 | df显示100% | 清理磁盘空间 |

### 43.2.2 预测误差异常增大

**症状：**
- 预测误差从历史均值0.05突增至0.5+
- 误差持续上升不收敛
- 预测值与实际值完全偏离

**诊断流程：**

```
1. 检查环境变化
   └─ 查看系统是否有更新、配置变更
   └─ 检查是否有新应用部署
   └─ 查看网络是否有变化

2. 检查数据质量
   └─ 查看感知数据是否有异常值
   └─ 检查传感器是否正常工作
   └─ 验证数据标准化是否正确

3. 检查模型状态
   └─ 查看模型版本是否变化
   └─ 检查模型参数是否正常
   └─ 验证模型是否损坏

4. 检查训练过程
   └─ 查看最近的学习记录
   └─ 检查是否有梯度爆炸
   └─ 验证学习率是否合适

5. 触发诊断任务
   └─ 手动触发模型评估
   └─ 对比新旧模型性能
   └─ 分析误差分布变化
```

**可能原因：**

| 原因 | 特征 | 解决方案 |
|------|------|---------|
| 概念漂移 | 误差持续上升 | 触发模型重构 |
| 数据异常 | 单点极大误差 | 检查并清理数据源 |
| 模型过拟合 | 训练误差低测试高 | 增加正则化 |
| 学习率过大 | 误差震荡 | 降低学习率 |
| 特征失效 | 特定特征误差大 | 更新特征工程 |
| 外部干扰 | 特定时段误差高 | 识别干扰源 |

### 43.2.3 内存泄漏

**症状：**
- 系统内存持续增长
- 最终触发OOM Killer
- 重启后恢复正常但再次泄漏

**诊断方法：**

```python
# 内存诊断脚本
import psutil
import tracemalloc
import gc

def diagnose_memory():
    process = psutil.Process()
    
    # 基础信息
    print(f"当前内存: {process.memory_info().rss / 1024 / 1024:.2f} MB")
    print(f"内存增长: {process.memory_info().rss / 1024 / 1024 - baseline:.2f} MB")
    
    # 对象统计
    gc.collect()
    objects = gc.get_objects()
    print(f"存活对象数: {len(objects)}")
    
    # 最大的对象
    import sys
    largest = sorted(objects, key=sys.getsizeof, reverse=True)[:10]
    for obj in largest:
        print(f"{type(obj).__name__}: {sys.getsizeof(obj) / 1024:.2f} KB")
    
    # 跟踪内存分配
    tracemalloc.start()
    # ... 运行一段时间 ...
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics('lineno')
    
    for stat in top_stats[:10]:
        print(f"{stat.traceback.format()[-1]}")
        print(f"  Size: {stat.size / 1024:.2f} KiB, Count: {stat.count}")
```

**常见泄漏点：**

| 位置 | 原因 | 解决方案 |
|------|------|---------|
| 历史缓存 | 无限制增长 | 设置容量上限 |
| 任务池 | 已完成任务未清理 | 定期清理过期任务 |
| 数据库连接 | 未正确关闭 | 使用连接池 |
| 事件监听器 | 未注销 | 及时移除监听器 |
| 循环引用 | 对象无法回收 | 使用弱引用 |

### 43.2.4 任务执行失败

**症状：**
- 任务状态显示failed
- 任务执行超时
- 任务执行后系统异常

**诊断流程：**

```
1. 查看任务日志
   └─ 获取任务ID
   └─ 查看任务执行日志
   └─ 分析错误堆栈

2. 检查任务参数
   └─ 验证输入参数合法性
   └─ 检查资源是否充足
   └─ 确认依赖是否满足

3. 复现问题
   └─ 手动执行相同任务
   └─ 在隔离环境测试
   └─ 逐步简化任务定位问题

4. 检查安全限制
   └─ 确认任务未触发安全规则
   └─ 检查资源使用是否超限
   └─ 验证文件访问权限
```

## 43.3 诊断工具

### 43.3.1 内置诊断命令

```bash
# 系统健康检查
python scripts/health_check.py

# 配置验证
python scripts/validate_config.py config/default.yaml

# 性能分析
python scripts/profile.py --duration 60

# 内存分析
python scripts/memory_profile.py

# 数据库检查
python scripts/check_db.py

# 网络诊断
python scripts/network_check.py
```

### 43.3.2 日志分析工具

```bash
# 实时日志监控
tail -f logs/agent.log | grep ERROR

# 错误统计
grep "ERROR" logs/agent.log | awk '{print $4}' | sort | uniq -c | sort -rn

# 性能趋势
grep "CYCLE_TIME" logs/agent.log | awk '{print $5}' > cycle_times.txt
python -c "import numpy as np; d=np.loadtxt('cycle_times.txt'); print(f'Mean: {np.mean(d):.2f}ms, Trend: {np.polyfit(range(len(d)), d, 1)[0]:.4f}')"

# 异常检测
python scripts/analyze_logs.py --file logs/agent.log --lookback 24h
```

### 43.3.3 性能分析工具

```python
# CPU性能分析
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# 运行需要分析的代码
for _ in range(1000):
    agent.step()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

```python
# 内存性能分析
from memory_profiler import profile

@profile
def analyze_memory():
    # 运行需要分析的代码
    agent.step()

analyze_memory()
```

## 43.4 应急处理

### 43.4.1 紧急停止流程

```bash
# 1. 尝试优雅停止
curl -X POST http://localhost:8080/api/v1/system/emergency-stop

# 2. 如果API不可用，发送信号
kill -SIGTERM <pid>

# 3. 等待5秒
sleep 5

# 4. 如果仍在运行，强制停止
kill -SIGKILL <pid>

# 5. 检查进程是否停止
ps aux | grep self-evolving-agent

# 6. 保存当前状态（如果可能）
cp -r data data.emergency.backup.$(date +%Y%m%d_%H%M%S)
```

### 43.4.2 数据恢复

```bash
# 1. 列出可用快照
curl http://localhost:8080/api/v1/memory/snapshots

# 2. 选择最近的稳定快照恢复
curl -X POST http://localhost:8080/api/v1/memory/snapshots/<snapshot_id>/restore

# 3. 如果没有快照，从备份恢复
cp backups/latest/* data/

# 4. 验证数据完整性
python scripts/check_db.py

# 5. 重启系统
sudo systemctl restart self-evolving-agent
```

### 43.4.3 降级运行

```yaml
# 降级配置 config/degraded.yaml
agent:
  name: "DegradedAgent"

runtime:
  loop_interval: 10.0  # 降低频率

prediction:
  mid_level:
    enabled: false  # 禁用LSTM
  high_level:
    enabled: false  # 禁用高层模型

perception:
  log_monitor:
    enabled: false  # 禁用日志监控
  file_monitor:
    enabled: false  # 禁用文件监控

task_generation:
  max_tasks_per_cycle: 3  # 减少任务数
```

## 43.5 预防性维护

### 43.5.1 定期检查清单

**每日检查：**
- [ ] 系统状态是否正常
- [ ] 预测误差是否在正常范围
- [ ] 资源使用是否超限
- [ ] 是否有未处理的安全告警

**每周检查：**
- [ ] 日志文件大小
- [ ] 数据库性能
- [ ] 备份完整性
- [ ] 配置变更记录

**每月检查：**
- [ ] 系统性能趋势
- [ ] 模型进化效果
- [ ] 安全漏洞扫描
- [ ] 依赖包更新

### 43.5.2 监控告警规则

```yaml
# 监控告警配置
alerts:
  - name: "系统宕机"
    condition: "system.state != 'running'"
    severity: "P0"
    action: "page_oncall"
    
  - name: "预测误差过高"
    condition: "prediction.error > 0.5"
    severity: "P1"
    action: "trigger_model_rebuild"
    
  - name: "内存泄漏"
    condition: "memory.growth_rate > 10MB/hour"
    severity: "P1"
    action: "restart_agent"
    
  - name: "CPU使用过高"
    condition: "cpu.usage > 18%"
    severity: "P2"
    action: "reduce_workload"
    
  - name: "磁盘空间不足"
    condition: "disk.free < 10GB"
    severity: "P2"
    action: "cleanup_storage"
    
  - name: "安全违规"
    condition: "safety.violation_count > 0"
    severity: "P1"
    action: "notify_security"
```

## 43.6 本章小结

本章提供了自驱永续进化Agent系统的故障排查与诊断指南：

1. **故障分类**：严重程度分级、类型分类
2. **常见故障**：系统无法启动、预测误差增大、内存泄漏、任务失败
3. **诊断工具**：内置命令、日志分析、性能分析
4. **应急处理**：紧急停止、数据恢复、降级运行
5. **预防维护**：定期检查清单、监控告警规则

这些指南确保系统在各种异常情况下都能快速恢复。
