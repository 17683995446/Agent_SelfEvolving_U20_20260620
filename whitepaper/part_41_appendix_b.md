# 第四十一章：附录B - 完整配置示例

## 41.1 默认配置文件

### 41.1.1 主配置文件

```yaml
# config/default.yaml
# 自驱永续进化Agent系统 - 默认配置

# 基础配置
agent:
  name: "SelfEvolvingAgent"
  version: "1.0.0"
  description: "自驱永续进化预测修正Agent系统"
  
# 运行配置
runtime:
  loop_interval: 1.0              # 主循环间隔（秒）
  error_retry_interval: 5.0       # 错误重试间隔（秒）
  max_concurrent_tasks: 5         # 最大并发任务数
  task_timeout: 300               # 任务超时时间（秒）
  
# 日志配置
logging:
  level: "INFO"                   # 日志级别：DEBUG/INFO/WARNING/ERROR/CRITICAL
  path: "./logs/agent.log"        # 日志文件路径
  max_bytes: 10485760             # 单个日志文件最大大小（10MB）
  backup_count: 5                 # 日志文件备份数量
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  
# 资源限制
resource_limits:
  max_cpu_percent: 20.0           # CPU使用上限（%）
  max_memory_percent: 20.0        # 内存使用上限（%）
  max_disk_usage_gb: 50.0         # 磁盘使用上限（GB）
  max_model_rebuild_iterations: 3 # 模型重构最大迭代次数
  storage_cleanup_keep_ratio: 0.3 # 存储清理保留比例
  
# 安全约束
safety_constraints:
  forbidden_paths:                # 禁止访问的路径
    - "/sys"
    - "/proc"
    - "/dev"
    - "/boot"
    - "/etc/ssh"
    - "/etc/passwd"
  max_exploration_stall_rounds: 5 # 探索停滞最大轮数
  auto_rollback_on_regression: true # 性能倒退自动回滚
  exploration_exploitation_ratio: 0.3 # 探索-利用比例
  idle_offline_review_trigger: true   # 空闲触发离线复盘
  steady_state_exploration_boost: true # 稳态提升探索权重
  
# 驱力权重
drive_weights:
  safe: 0.4                       # 安全驱力权重
  gain: 0.4                       # 收益驱力权重
  eff: 0.2                        # 能效驱力权重
  
# 驱力配置
drive_config:
  safe:
    error_weight: 0.3             # 错误率权重
    unique_error_weight: 0.2      # 唯一错误类型权重
    cpu_weight: 0.2               # CPU权重
    memory_weight: 0.15           # 内存权重
    load_spike_weight: 0.15       # 负载突变权重
    
  gain:
    error_trend_weight: 0.4       # 误差趋势权重
    env_change_weight: 0.3        # 环境变化权重
    coverage_weight: 0.3          # 覆盖度权重
    
  eff:
    cpu_ratio_weight: 0.4         # CPU比例权重
    memory_ratio_weight: 0.4      # 内存比例权重
    thread_weight: 0.2            # 线程数权重
    
# 预测模型配置
prediction:
  horizon: 10                     # 默认预测步数
  min_history_length: 50          # 最小历史数据长度
  model_save_interval: 3600       # 模型保存间隔（秒）
  
  # 底层模型（AES）
  low_level:
    enabled: true
    alpha_min: 0.05
    alpha_max: 0.95
    alpha_default: 0.3
    adaptation_rate: 0.1
    error_window_size: 50
    trend_detection_threshold: 0.1
    damping_factor: 0.9
    
  # 中层模型（LSTM）
  mid_level:
    enabled: true
    hidden_size: 64
    num_layers: 2
    dropout: 0.2
    learning_rate: 0.001
    batch_size: 32
    epochs: 1
    replay_ratio: 0.3
    ewc_lambda: 1000.0
    
  # 高层模型（统计）
  high_level:
    enabled: true
    window_size: 100
    trend_model: "linear"
    seasonal_period: null
    
# 记忆配置
memory:
  db_path: "./data/memory.db"     # 数据库路径
  snapshot_dir: "./data/snapshots" # 快照目录
  short_term_capacity: 1000       # 短期记忆容量
  long_term_capacity: 100000      # 长期记忆容量
  
# 离线复盘配置
offline_review:
  interval: 86400                 # 复盘间隔（秒）
  min_idle_time: 300              # 最小空闲时间（秒）
  batch_size: 1000                # 批量处理大小
  max_review_duration: 3600       # 最大复盘时长（秒）
  
# 感知配置
perception:
  system_sampling_interval: 1.0   # 系统采样间隔（秒）
  log_check_interval: 60.0        # 日志检查间隔（秒）
  file_check_interval: 60.0       # 文件检查间隔（秒）
  self_check_interval: 5.0        # 自身检查间隔（秒）
  
  # 日志监控
  log_monitor:
    enabled: true
    log_paths:                    # 监控的日志文件
      - "/var/log/syslog"
      - "/var/log/auth.log"
      - "/var/log/kern.log"
    max_lines_per_check: 1000     # 每次检查最大行数
    
  # 文件监控
  file_monitor:
    enabled: true
    watch_dirs:                   # 监控的目录
      - "./data"
      - "./logs"
      - "./models"
    max_files_per_dir: 10000      # 每目录最大文件数
    
# 任务生成配置
task_generation:
  max_tasks_per_cycle: 10         # 每轮最大生成任务数
  task_expiry_seconds: 3600       # 任务过期时间（秒）
  min_task_reward: 0.01           # 最小任务收益
  max_task_cost: 1.0              # 最大任务成本
  
# 决策配置
decision:
  exploration_ratio: 0.3          # 探索比例
  exploration_min: 0.1            # 最小探索比例
  exploration_max: 0.5            # 最大探索比例
  interruption_threshold: 0.8     # 中断阈值
  
# 安全守护配置
safety_guard:
  check_interval: 5.0             # 检查间隔（秒）
  cpu_warning_threshold: 15.0     # CPU警告阈值
  cpu_critical_threshold: 18.0    # CPU危急阈值
  memory_warning_threshold: 15.0  # 内存警告阈值
  memory_critical_threshold: 18.0 # 内存危急阈值
  
# API配置
api:
  enabled: true
  host: "0.0.0.0"
  port: 8080
  auth_enabled: true
  token_expiry: 3600              # Token过期时间（秒）
  rate_limit: 100                 # 每分钟请求限制
  
# WebSocket配置
websocket:
  enabled: true
  ping_interval: 30               # Ping间隔（秒）
  ping_timeout: 10                # Ping超时（秒）
  
# 监控配置
monitoring:
  enabled: true
  metrics_interval: 60            # 指标采集间隔（秒）
  health_check_interval: 30       # 健康检查间隔（秒）
  
# 备份配置
backup:
  enabled: true
  interval: 86400                 # 备份间隔（秒）
  retention_days: 30              # 保留天数
  backup_dir: "./backups"         # 备份目录
```

### 41.1.2 最小配置

```yaml
# config/minimal.yaml
# 最小化配置，用于快速启动和测试

agent:
  name: "MinimalAgent"

runtime:
  loop_interval: 5.0

logging:
  level: "WARNING"
  path: "./logs/minimal.log"

resource_limits:
  max_cpu_percent: 10.0
  max_memory_percent: 10.0

prediction:
  low_level:
    enabled: true
  mid_level:
    enabled: false
  high_level:
    enabled: false

api:
  enabled: false

websocket:
  enabled: false
```

### 41.1.3 生产环境配置

```yaml
# config/production.yaml
# 生产环境配置

agent:
  name: "ProductionAgent"

logging:
  level: "INFO"
  path: "/var/log/self-evolving-agent/agent.log"
  max_bytes: 52428800             # 50MB
  backup_count: 10

resource_limits:
  max_cpu_percent: 15.0
  max_memory_percent: 15.0
  max_disk_usage_gb: 100.0

safety_constraints:
  exploration_exploitation_ratio: 0.2  # 生产环境更保守

drive_weights:
  safe: 0.6                       # 生产环境安全优先
  gain: 0.2
  eff: 0.2

prediction:
  model_save_interval: 1800       # 更频繁保存
  
  mid_level:
    hidden_size: 128              # 更大模型
    num_layers: 3

memory:
  db_path: "/var/lib/self-evolving-agent/memory.db"
  snapshot_dir: "/var/lib/self-evolving-agent/snapshots"

api:
  auth_enabled: true
  rate_limit: 60                  # 更严格的限流

monitoring:
  metrics_interval: 30            # 更频繁监控
```

### 41.1.4 开发环境配置

```yaml
# config/development.yaml
# 开发环境配置

agent:
  name: "DevAgent"

logging:
  level: "DEBUG"
  path: "./logs/dev.log"

resource_limits:
  max_cpu_percent: 30.0           # 开发环境更宽松
  max_memory_percent: 30.0

safety_constraints:
  exploration_exploitation_ratio: 0.4  # 更多探索

drive_weights:
  safe: 0.2                       # 开发环境收益优先
  gain: 0.6
  eff: 0.2

prediction:
  model_save_interval: 600        # 更频繁保存以便调试

api:
  auth_enabled: false             # 开发环境免认证
  rate_limit: 1000                # 更宽松的限流

monitoring:
  metrics_interval: 10            # 更频繁监控以便调试
```

## 41.2 环境变量配置

### 41.2.1 支持的环境变量

```bash
# 基础配置
export AGENT_NAME="SelfEvolvingAgent"
export AGENT_LOG_LEVEL="INFO"

# 资源限制
export AGENT_MAX_CPU="20.0"
export AGENT_MAX_MEMORY="20.0"

# 驱力权重
export AGENT_SAFE_WEIGHT="0.4"
export AGENT_GAIN_WEIGHT="0.4"
export AGENT_EFF_WEIGHT="0.2"

# API配置
export AGENT_API_HOST="0.0.0.0"
export AGENT_API_PORT="8080"
export AGENT_API_AUTH="true"

# 数据库
export AGENT_DB_PATH="./data/memory.db"

# 路径配置
export AGENT_LOG_PATH="./logs/agent.log"
export AGENT_SNAPSHOT_DIR="./data/snapshots"
```

### 41.2.2 Docker环境变量

```dockerfile
# Dockerfile环境变量
ENV AGENT_LOG_LEVEL=INFO
ENV AGENT_MAX_CPU=20.0
ENV AGENT_MAX_MEMORY=20.0
ENV AGENT_SAFE_WEIGHT=0.4
ENV AGENT_GAIN_WEIGHT=0.4
ENV AGENT_EFF_WEIGHT=0.2
ENV AGENT_API_PORT=8080
```

### 41.2.3 Kubernetes ConfigMap

```yaml
# kubernetes/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: self-evolving-agent-config
data:
  AGENT_LOG_LEVEL: "INFO"
  AGENT_MAX_CPU: "20.0"
  AGENT_MAX_MEMORY: "20.0"
  AGENT_SAFE_WEIGHT: "0.4"
  AGENT_GAIN_WEIGHT: "0.4"
  AGENT_EFF_WEIGHT: "0.2"
  AGENT_API_PORT: "8080"
```

## 41.3 配置验证

### 41.3.1 配置验证脚本

```python
# scripts/validate_config.py
import yaml
import sys
from pathlib import Path

def validate_config(config_path: str) -> bool:
    """验证配置文件"""
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    errors = []
    warnings = []
    
    # 验证基础配置
    if 'agent' not in config:
        errors.append("缺少agent配置")
    
    # 验证资源限制
    if 'resource_limits' in config:
        limits = config['resource_limits']
        
        if 'max_cpu_percent' in limits:
            if not 0 < limits['max_cpu_percent'] <= 100:
                errors.append("max_cpu_percent必须在(0, 100]范围内")
        
        if 'max_memory_percent' in limits:
            if not 0 < limits['max_memory_percent'] <= 100:
                errors.append("max_memory_percent必须在(0, 100]范围内")
    
    # 验证驱力权重
    if 'drive_weights' in config:
        weights = config['drive_weights']
        total = weights.get('safe', 0) + weights.get('gain', 0) + weights.get('eff', 0)
        
        if abs(total - 1.0) > 1e-6:
            errors.append(f"驱力权重之和必须等于1，当前为{total}")
        
        for key in ['safe', 'gain', 'eff']:
            if key in weights and not 0 <= weights[key] <= 1:
                errors.append(f"{key}权重必须在[0, 1]范围内")
    
    # 验证探索-利用比例
    if 'decision' in config:
        decision = config['decision']
        if 'exploration_ratio' in decision:
            if not 0 <= decision['exploration_ratio'] <= 1:
                errors.append("exploration_ratio必须在[0, 1]范围内")
    
    # 验证路径
    if 'logging' in config:
        log_path = Path(config['logging']['path'])
        if not log_path.parent.exists():
            warnings.append(f"日志目录不存在: {log_path.parent}")
    
    if 'memory' in config:
        db_path = Path(config['memory']['db_path'])
        if not db_path.parent.exists():
            warnings.append(f"数据库目录不存在: {db_path.parent}")
    
    # 输出结果
    if errors:
        print("错误:")
        for error in errors:
            print(f"  ❌ {error}")
    
    if warnings:
        print("警告:")
        for warning in warnings:
            print(f"  ⚠️  {warning}")
    
    if not errors and not warnings:
        print("✅ 配置验证通过")
        return True
    elif not errors:
        print("✅ 配置验证通过（有警告）")
        return True
    else:
        print("❌ 配置验证失败")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python validate_config.py <config_path>")
        sys.exit(1)
    
    config_path = sys.argv[1]
    success = validate_config(config_path)
    sys.exit(0 if success else 1)
```

### 41.3.2 配置热加载

```python
# config/hot_reload.py
import yaml
import time
import threading
from pathlib import Path
from typing import Callable

class ConfigManager:
    """
    配置管理器
    
    支持配置热加载
    """
    
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config = {}
        self.last_modified = 0
        self.listeners: list[Callable] = []
        self._lock = threading.RLock()
        self._running = False
        
    def load(self) -> dict:
        """加载配置"""
        with self._lock:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
            self.last_modified = self.config_path.stat().st_mtime
            return self.config
    
    def get(self, key: str, default=None):
        """获取配置项"""
        with self._lock:
            keys = key.split('.')
            value = self.config
            for k in keys:
                if isinstance(value, dict):
                    value = value.get(k)
                else:
                    return default
            return value if value is not None else default
    
    def add_listener(self, listener: Callable):
        """添加配置变更监听器"""
        self.listeners.append(listener)
    
    def start_hot_reload(self, interval: float = 5.0):
        """启动热加载"""
        self._running = True
        
        def watch():
            while self._running:
                try:
                    current_mtime = self.config_path.stat().st_mtime
                    if current_mtime > self.last_modified:
                        old_config = self.config.copy()
                        self.load()
                        
                        # 通知监听器
                        for listener in self.listeners:
                            try:
                                listener(old_config, self.config)
                            except Exception as e:
                                print(f"配置变更监听错误: {e}")
                        
                        print("配置已热加载")
                except Exception as e:
                    print(f"热加载检查错误: {e}")
                
                time.sleep(interval)
        
        thread = threading.Thread(target=watch, daemon=True)
        thread.start()
    
    def stop_hot_reload(self):
        """停止热加载"""
        self._running = False
```

## 41.4 配置最佳实践

### 41.4.1 环境分离

```
config/
├── default.yaml          # 默认配置（基础值）
├── development.yaml      # 开发环境覆盖
├── testing.yaml          # 测试环境覆盖
├── staging.yaml          # 预发布环境覆盖
└── production.yaml       # 生产环境覆盖
```

加载顺序：default → {environment} → 环境变量

### 41.4.2 敏感信息处理

```yaml
# 不要将敏感信息写入配置文件
# 使用环境变量或密钥管理服务

# ❌ 错误示例
api:
  auth_token: "hardcoded_secret_token"

# ✅ 正确示例
api:
  auth_token: "${AGENT_AUTH_TOKEN}"  # 从环境变量读取
```

### 41.4.3 配置版本控制

```yaml
# 在配置中记录版本信息
config_version: "1.0.0"
last_updated: "2024-01-01T00:00:00Z"

# 配置变更历史
changelog:
  - version: "1.0.0"
    date: "2024-01-01"
    changes:
      - "初始配置"
  - version: "1.1.0"
    date: "2024-02-01"
    changes:
      - "增加LSTM模型配置"
      - "调整驱力权重"
```

## 41.5 本章小结

本章提供了自驱永续进化Agent系统的完整配置参考：

1. **默认配置**：完整的配置项和默认值
2. **最小配置**：快速启动的最小化配置
3. **生产配置**：生产环境的推荐配置
4. **开发配置**：开发环境的推荐配置
5. **环境变量**：支持的环境变量列表
6. **配置验证**：验证脚本和热加载机制
7. **最佳实践**：环境分离、敏感信息处理、版本控制

这些配置示例为不同场景的部署提供了参考。
