# 实践指南

## 1. 快速开始

### 1.1 环境准备

```bash
# 1. 克隆仓库
git clone https://github.com/self-evolving-agent/agent.git
cd agent

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 验证安装
python -c "from agent import SelfEvolvingAgent; print('安装成功')"
```

### 1.2 最小配置启动

```python
# quickstart.py
from agent import SelfEvolvingAgent
from agent.config import AgentConfig

# 使用默认配置
config = AgentConfig()

# 创建Agent
agent = SelfEvolvingAgent(config)

# 启动Agent
try:
    agent.run()
except KeyboardInterrupt:
    print("Agent已停止")
```

### 1.3 配置文件示例

```yaml
# config.yaml
agent:
  cycle_interval: 1.0
  
  constraints:
    max_cpu_percent: 20.0
    max_memory_percent: 20.0
    max_recon_iterations: 3
    storage_keep_ratio: 0.3
  
  drive_weight_bias:
    safe: 0.4
    gain: 0.4
    eff: 0.2

perception:
  cpu_sample_interval: 1.0
  memory_sample_interval: 1.0
  disk_sample_interval: 5.0
  network_sample_interval: 5.0

memory:
  storage_dir: "./agent_storage"
  max_storage_size_gb: 10.0
```

## 2. 自定义开发

### 2.1 自定义感知模块

```python
# custom_perception.py
from modules.perception.base import BasePerception

class CustomPerception(BasePerception):
    """自定义感知模块示例"""
    
    def __init__(self, config):
        super().__init__(config)
        self.custom_metrics = []
    
    def add_metric(self, metric_func, name):
        """添加自定义指标"""
        self.custom_metrics.append({
            'func': metric_func,
            'name': name
        })
    
    def get_current_state(self):
        """获取当前状态（包含自定义指标）"""
        base_state = super().get_current_state()
        
        # 添加自定义指标
        custom_values = []
        for metric in self.custom_metrics:
            try:
                value = metric['func']()
                custom_values.append(value)
            except Exception as e:
                self.logger.warning(f"自定义指标 {metric['name']} 采集失败: {e}")
                custom_values.append(0)
        
        # 合并到状态向量
        return StateVector(
            values=np.concatenate([base_state.values, custom_values]),
            metadata={
                **base_state.metadata,
                'custom_metrics': [m['name'] for m in self.custom_metrics]
            }
        )


# 使用自定义感知
from agent import SelfEvolvingAgent

agent = SelfEvolvingAgent()

# 替换感知模块
custom_perception = CustomPerception(agent.config.perception)

# 添加自定义指标：GPU使用率
custom_perception.add_metric(
    metric_func=lambda: get_gpu_usage(),
    name='gpu_usage'
)

# 添加自定义指标：应用特定指标
custom_perception.add_metric(
    metric_func=lambda: get_application_queue_length(),
    name='app_queue_length'
)

agent.perception = custom_perception
agent.run()
```

### 2.2 自定义任务类型

```python
# custom_tasks.py
from modules.task.types import TaskTemplate

# 定义自定义任务模板
custom_task_templates = {
    'database_optimize': TaskTemplate(
        task_type='database_optimize',
        description='优化数据库性能',
        required_resources={'cpu': 0.1, 'memory': 200, 'time': 300},
        expected_duration=timedelta(minutes=5),
        execution_logic=optimize_database,
        success_criteria=lambda result: result['improvement'] > 0.1
    ),
    
    'cache_warmup': TaskTemplate(
        task_type='cache_warmup',
        description='预热缓存',
        required_resources={'cpu': 0.05, 'memory': 100, 'time': 60},
        expected_duration=timedelta(minutes=1),
        execution_logic=warmup_cache,
        success_criteria=lambda result: result['hit_rate'] > 0.8
    ),
    
    'log_archive': TaskTemplate(
        task_type='log_archive',
        description='归档旧日志',
        required_resources={'cpu': 0.05, 'memory': 50, 'time': 600},
        expected_duration=timedelta(minutes=10),
        execution_logic=archive_old_logs,
        success_criteria=lambda result: result['archived_size'] > 0
    )
}

# 注册自定义任务
def optimize_database():
    """数据库优化逻辑"""
    import subprocess
    
    # 分析表
    subprocess.run(['mysqlcheck', '-a', '--all-databases'])
    
    # 优化表
    result = subprocess.run(
        ['mysqlcheck', '-o', '--all-databases'],
        capture_output=True,
        text=True
    )
    
    # 评估优化效果
    before_size = get_database_size()
    # ... 执行优化 ...
    after_size = get_database_size()
    
    return {
        'improvement': (before_size - after_size) / before_size,
        'details': result.stdout
    }


def warmup_cache():
    """缓存预热逻辑"""
    # 加载热点数据到缓存
    hot_keys = get_hot_keys_from_logs()
    
    for key in hot_keys:
        load_to_cache(key)
    
    # 验证命中率
    hit_rate = measure_cache_hit_rate(duration=30)
    
    return {'hit_rate': hit_rate}


def archive_old_logs():
    """日志归档逻辑"""
    import shutil
    from datetime import datetime, timedelta
    
    cutoff_date = datetime.now() - timedelta(days=30)
    archived_size = 0
    
    for log_file in Path('/var/log').glob('*.log.*'):
        if log_file.stat().st_mtime < cutoff_date.timestamp():
            # 压缩并移动
            archive_path = f'/archive/logs/{log_file.name}.gz'
            shutil.make_archive(archive_path, 'gztar', str(log_file))
            archived_size += log_file.stat().st_size
            log_file.unlink()
    
    return {'archived_size': archived_size}


# 注册到任务生成器
from modules.task.generator import TaskGenerator

TaskGenerator.register_templates(custom_task_templates)
```

### 2.3 自定义驱力权重

```python
# custom_drive_weights.py
from agent import SelfEvolvingAgent

# 创建Agent
agent = SelfEvolvingAgent()

# 场景1：安全优先（生产环境）
agent.drive_engine.set_weight_bias(
    safe=0.6,
    gain=0.2,
    eff=0.2
)

# 场景2：进化优先（实验环境）
agent.drive_engine.set_weight_bias(
    safe=0.2,
    gain=0.6,
    eff=0.2
)

# 场景3：能效优先（资源受限环境）
agent.drive_engine.set_weight_bias(
    safe=0.3,
    gain=0.2,
    eff=0.5
)

# 动态调整回调
def dynamic_weight_adjustment(drive_output):
    """根据时间动态调整权重"""
    hour = datetime.now().hour
    
    if 9 <= hour <= 18:  # 工作时间
        return {'safe': 0.5, 'gain': 0.3, 'eff': 0.2}
    else:  # 非工作时间
        return {'safe': 0.2, 'gain': 0.5, 'eff': 0.3}

agent.drive_engine.set_dynamic_callback(dynamic_weight_adjustment)
```

## 3. 监控与运维

### 3.1 日志分析

```python
# log_analyzer.py
import re
from collections import Counter

def analyze_agent_logs(log_file):
    """分析Agent日志"""
    
    patterns = {
        'cycle_time': r'Cycle (\d+) completed in ([\d.]+)s',
        'task_execution': r'Task (\w+) executed: (success|failed)',
        'drive_weights': r'Drive weights: safe=([\d.]+), gain=([\d.]+), eff=([\d.]+)',
        'prediction_error': r'Prediction error: ([\d.]+)',
        'reconstruction': r'Structural reconstruction (triggered|completed)',
        'review': r'Offline review (started|completed)'
    }
    
    results = {key: [] for key in patterns}
    
    with open(log_file, 'r') as f:
        for line in f:
            for key, pattern in patterns.items():
                match = re.search(pattern, line)
                if match:
                    results[key].append(match.groups())
    
    # 统计分析
    analysis = {}
    
    # 循环时间分析
    if results['cycle_time']:
        cycle_times = [float(x[1]) for x in results['cycle_time']]
        analysis['avg_cycle_time'] = np.mean(cycle_times)
        analysis['max_cycle_time'] = np.max(cycle_times)
    
    # 任务成功率
    if results['task_execution']:
        outcomes = [x[1] for x in results['task_execution']]
        analysis['task_success_rate'] = outcomes.count('success') / len(outcomes)
    
    # 驱力权重变化
    if results['drive_weights']:
        weights = results['drive_weights'][-1]
        analysis['current_weights'] = {
            'safe': float(weights[0]),
            'gain': float(weights[1]),
            'eff': float(weights[2])
        }
    
    # 预测误差趋势
    if results['prediction_error']:
        errors = [float(x[0]) for x in results['prediction_error']]
        analysis['avg_prediction_error'] = np.mean(errors[-100:])
        analysis['error_trend'] = 'decreasing' if errors[-1] < errors[0] else 'increasing'
    
    # 重构频率
    analysis['reconstruction_count'] = len(results['reconstruction']) // 2
    
    # 复盘频率
    analysis['review_count'] = len(results['review']) // 2
    
    return analysis


# 使用示例
analysis = analyze_agent_logs('logs/agent.log')
print(f"平均循环时间: {analysis['avg_cycle_time']:.2f}s")
print(f"任务成功率: {analysis['task_success_rate']:.1%}")
print(f"当前驱力权重: {analysis['current_weights']}")
print(f"预测误差趋势: {analysis['error_trend']}")
```

### 3.2 性能监控脚本

```bash
#!/bin/bash
# monitor.sh

AGENT_PID=$(pgrep -f "python main.py")

if [ -z "$AGENT_PID" ]; then
    echo "Agent未运行"
    exit 1
fi

echo "=== Agent性能监控 ==="
echo "PID: $AGENT_PID"

# CPU和内存使用
ps -p $AGENT_PID -o pid,ppid,cmd,%cpu,%mem --no-headers

# 打开文件数
FD_COUNT=$(ls /proc/$AGENT_PID/fd | wc -l)
echo "打开文件数: $FD_COUNT"

# 线程数
THREAD_COUNT=$(ls /proc/$AGENT_PID/task | wc -l)
echo "线程数: $THREAD_COUNT"

# 存储使用
STORAGE_SIZE=$(du -sh ./agent_storage | cut -f1)
echo "存储使用: $STORAGE_SIZE"

# 最近错误
echo "=== 最近错误 ==="
tail -n 20 logs/agent.log | grep -i "error\|exception\|failed"

# 进化状态
echo "=== 进化状态 ==="
tail -n 50 logs/agent.log | grep -E "precision|breadth|efficiency|score"
```

### 3.3 告警配置

```python
# alerter.py
import smtplib
from email.mime.text import MIMEText
import requests

class AgentAlerter:
    """Agent告警系统"""
    
    def __init__(self, config):
        self.config = config
        self.alert_history = []
    
    def check_and_alert(self, agent_state):
        """检查并发送告警"""
        alerts = []
        
        # 检查Agent是否运行
        if not agent_state['running']:
            alerts.append({
                'level': 'critical',
                'message': 'Agent已停止运行'
            })
        
        # 检查资源使用
        if agent_state.get('cpu_usage', 0) > 25:
            alerts.append({
                'level': 'warning',
                'message': f"CPU使用过高: {agent_state['cpu_usage']:.1f}%"
            })
        
        # 检查预测误差
        if agent_state.get('prediction_error', 0) > 0.5:
            alerts.append({
                'level': 'warning',
                'message': f"预测误差过高: {agent_state['prediction_error']:.2f}"
            })
        
        # 检查进化停滞
        if agent_state.get('stagnation_duration', 0) > 3600:
            alerts.append({
                'level': 'info',
                'message': '进化可能停滞，建议检查'
            })
        
        # 发送告警
        for alert in alerts:
            self._send_alert(alert)
        
        return alerts
    
    def _send_alert(self, alert):
        """发送告警通知"""
        # 邮件告警
        if self.config.get('email'):
            self._send_email(alert)
        
        # Webhook告警
        if self.config.get('webhook_url'):
            self._send_webhook(alert)
        
        # 日志记录
        logging.warning(f"ALERT [{alert['level']}]: {alert['message']}")
    
    def _send_email(self, alert):
        """发送邮件"""
        msg = MIMEText(alert['message'])
        msg['Subject'] = f"[Agent Alert] {alert['level'].upper()}"
        msg['From'] = self.config['email']['from']
        msg['To'] = self.config['email']['to']
        
        with smtplib.SMTP(self.config['email']['smtp_server']) as server:
            server.send_message(msg)
    
    def _send_webhook(self, alert):
        """发送Webhook"""
        requests.post(
            self.config['webhook_url'],
            json={
                'level': alert['level'],
                'message': alert['message'],
                'timestamp': datetime.now().isoformat()
            }
        )
```

## 4. 故障排查

### 4.1 常见问题

#### 问题1：Agent启动后立即退出

```bash
# 检查日志
tail -n 50 logs/agent.log

# 常见原因：
# 1. 权限不足
ls -la agent_storage/
# 解决：chmod 755 agent_storage/

# 2. 端口冲突
netstat -tlnp | grep <port>
# 解决：修改配置中的端口

# 3. 依赖缺失
pip install -r requirements.txt --force-reinstall
```

#### 问题2：预测误差持续升高

```python
# 诊断脚本
from agent.memory import MemorySystem

memory = MemorySystem()

# 检查最近预测误差
recent_errors = memory.get_recent_prediction_errors(hours=24)
print(f"平均误差: {np.mean(recent_errors):.3f}")
print(f"误差趋势: {'上升' if recent_errors[-1] > recent_errors[0] else '下降'}")

# 检查模型状态
predictor = memory.load_predictor_state()
print(f"模型数量: {len(predictor.models)}")
print(f"活跃模型: {len([m for m in predictor.models if not m.dormant])}")

# 检查是否有异常状态
recent_states = memory.get_recent_states(hours=1)
print(f"状态异常率: {sum(1 for s in recent_states if s.is_anomalous) / len(recent_states):.1%}")
```

#### 问题3：存储空间快速增长

```bash
# 检查存储使用
du -sh agent_storage/*

# 手动触发清理
python -c "
from agent.memory import MemorySystem
memory = MemorySystem()
memory.auto_cleanup()
print('清理完成')
"

# 调整保留策略
# 编辑配置：减少 retention_days 或 keep_ratio
```

### 4.2 调试模式

```python
# debug_mode.py
from agent import SelfEvolvingAgent
from agent.config import AgentConfig

# 启用调试模式
config = AgentConfig()
config.debug = True
config.cycle_interval = 5.0  # 减慢循环便于观察

agent = SelfEvolvingAgent(config)

# 添加调试钩子
@agent.on_cycle_complete
def on_cycle(cycle_result):
    print(f"\n=== Cycle {cycle_result.cycle_id} ===")
    print(f"State: {cycle_result.state_vector.summary()}")
    print(f"Drive: {cycle_result.drive_output}")
    print(f"Selected Task: {cycle_result.selected_task}")
    print(f"Predictions: {cycle_result.predictions}")

# 单步执行
for i in range(10):
    agent.run_single_cycle()
    input("按Enter继续...")
```

## 5. 最佳实践

### 5.1 配置建议

| 场景 | CPU限制 | 内存限制 | 探索率 | 复盘频率 |
|-----|--------|---------|--------|---------|
| 生产服务器 | 15% | 15% | 20% | 每天1次 |
| 开发工作站 | 25% | 25% | 40% | 每6小时 |
| 边缘设备 | 10% | 10% | 30% | 每天1次 |
| 实验环境 | 30% | 30% | 50% | 每2小时 |

### 5.2 运维清单

- [ ] 每日检查Agent运行状态
- [ ] 每周审查进化指标趋势
- [ ] 每月清理过期存储数据
- [ ] 每季度评估驱力权重配置
- [ ] 每年进行系统架构评审

---

实践指南提供了从快速开始、自定义开发到监控运维的完整操作手册，帮助用户快速上手并有效使用自驱永续进化Agent系统。
