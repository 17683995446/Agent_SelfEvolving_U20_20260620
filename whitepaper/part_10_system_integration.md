# 系统整合与部署方案

## 1. 系统整体架构

### 1.1 模块关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                        自驱永续进化Agent系统                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│  │  环境感知模块 │───→│  驱力引擎模块 │───→│ 自主目标生成 │      │
│  │  (感官层)    │    │  (动机层)    │    │  (任务孵化层) │      │
│  └──────────────┘    └──────────────┘    └──────┬───────┘      │
│         ↑                                        │              │
│         │         ┌──────────────────┐          │              │
│         │         │   自主决策模块    │←─────────┘              │
│         │         │   (决策中枢)     │                         │
│         │         └────────┬─────────┘                         │
│         │                  │                                    │
│         │    ┌─────────────┼─────────────┐                    │
│         │    │             │             │                    │
│         │    ↓             ↓             ↓                    │
│  ┌──────┴──────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ 多层预测模型 │  │ 误差评估反馈 │  │ 双模式优化器 │         │
│  │ (认知核心层) │  │ (修正信号源) │  │ (进化执行层) │         │
│  └─────────────┘  └──────────────┘  └──────────────┘         │
│         ↑                                    │                │
│         │         ┌──────────────────┐      │                │
│         └─────────│  记忆与离线复盘  │←─────┘                │
│                   │  (睡眠进化层)    │                       │
│                   └──────────────────┘                       │
│                              │                                │
│                              ↓                                │
│                   ┌──────────────────┐                       │
│                   │  进化指标监控    │                       │
│                   │  (自我意识层)    │                       │
│                   └──────────────────┘                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 数据流图

```
环境状态 ──→ 感知模块 ──→ 状态向量 ──→ 驱力引擎 ──→ 缺口信号
                                              │
                                              ↓
任务池 ←── 目标生成 ←── 缺口信号          预测模型 ←── 历史数据
  │                                          │
  ↓                                          ↓
决策模块 ──→ 选中任务 ──→ 行为执行 ──→ 环境变化
  │                                          │
  └────────── 实际结果 ←── 误差评估 ←── 预测比对
                                              │
                                              ↓
记忆系统 ←── 记录数据 ←── 离线复盘 ←── 模型优化
  │
  ↓
监控模块 ──→ 进化指标 ──→ 反馈调整
```

## 2. 核心循环实现

### 2.1 主循环

```python
class SelfEvolvingAgent:
    def __init__(self, config: AgentConfig):
        self.perception = EnvironmentPerception(config.perception)
        self.drive_engine = DriveEngine(config.drive)
        self.predictor = MultiLayerPredictor(config.predictor)
        self.task_generator = TaskGenerator(config.task_gen)
        self.decision_engine = DecisionEngine(config.decision)
        self.memory = MemorySystem(config.memory)
        self.offline_review = OfflineReviewModule(config.review)
        self.monitor = EvolutionMonitor(config.monitor)
        self.evolution = StructuralEvolution(config.evolution)
        
        self.current_task = None
        self.running = False
    
    def run(self):
        """主运行循环"""
        self.running = True
        self.perception.start()
        
        while self.running:
            cycle_start = time.time()
            
            # 1. 环境感知
            state_vector = self.perception.get_current_state()
            self.memory.record_perception(state_vector)
            
            # 2. 多层预测
            predictions = self.predictor.predict_all(state_vector)
            
            # 3. 驱力计算
            drive_output = self.drive_engine.compute(state_vector)
            self.memory.record_drive(drive_output)
            
            # 4. 任务生成
            new_tasks = self.task_generator.generate_tasks(drive_output, state_vector)
            self.task_generator.update_task_pool(new_tasks)
            
            # 5. 自主决策
            task_pool = self.task_generator.get_task_pool()
            decision = self.decision_engine.decide(
                state_vector, drive_output, task_pool, self.current_task
            )
            self.memory.record_decision(decision)
            
            # 6. 任务执行与中断处理
            if decision.should_interrupt and self.current_task:
                self.interrupt_current_task()
            
            if decision.selected_task:
                self.current_task = decision.selected_task
                execution_result = self.execute_task(self.current_task)
                self.memory.record_task_execution(execution_result)
                
                # 7. 预测误差评估
                self.evaluate_predictions(state_vector, predictions)
                
                # 8. 模型微修正
                self.predictor.micro_adjust()
            
            # 9. 结构性重构检查
            if self.evolution.check_reconstruction_needed(
                self.predictor.get_error_history(),
                drive_output.get_gaps()
            ):
                recon_result = self.evolution.execute_reconstruction(
                    trigger_reason='high_error',
                    state_history=self.memory.get_recent_states()
                )
                self.memory.record_reconstruction(recon_result)
            
            # 10. 离线复盘检查
            if self.offline_review.check_review_needed(state_vector):
                review_result = self.offline_review.execute_review()
                self.memory.record_review(review_result)
            
            # 11. 进化指标更新
            self.monitor.update_metrics(
                state_vector, drive_output,
                self.predictor.get_recent_predictions(),
                self.memory.get_recent_tasks()
            )
            
            # 12. 检查告警并自动响应
            alerts = self.monitor.check_alerts()
            if alerts:
                self.auto_respond_to_alerts(alerts, drive_output)
            
            # 控制循环频率
            cycle_duration = time.time() - cycle_start
            if cycle_duration < self.config.cycle_interval:
                time.sleep(self.config.cycle_interval - cycle_duration)
    
    def execute_task(self, task: Task) -> ExecutionResult:
        """执行任务"""
        start_time = datetime.now()
        
        try:
            # 执行任务逻辑
            result = task.execution_logic()
            
            # 计算实际收益
            actual_reward = self.calculate_task_reward(task, result)
            
            return ExecutionResult(
                success=True,
                actual_reward=actual_reward,
                execution_duration=datetime.now() - start_time
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_duration=datetime.now() - start_time
            )
    
    def evaluate_predictions(self, actual_state: StateVector, 
                            predictions: List[Prediction]):
        """评估预测误差"""
        for prediction in predictions:
            error = calculate_prediction_error(prediction, actual_state)
            self.predictor.update(prediction, actual_state, error)
            self.memory.record_prediction(prediction, actual_state, error)
    
    def auto_respond_to_alerts(self, alerts: List[str], drive_output: DriveOutput):
        """自动响应进化告警"""
        for alert in alerts:
            if "精度退化" in alert or "精度停滞" in alert:
                # 提升收益驱力权重
                self.drive_engine.adjust_weight('gain', 1.2)
            elif "广度停滞" in alert:
                # 增加探索任务
                self.task_generator.boost_exploration()
            elif "能效退化" in alert:
                # 提升能效驱力权重
                self.drive_engine.adjust_weight('eff', 1.3)
```

## 3. 部署方案

### 3.1 环境要求

```
操作系统：Linux (Ubuntu 20.04+) / Windows 10+
Python版本：3.8+
内存要求：最低4GB，推荐8GB+
磁盘要求：最低10GB可用空间
CPU要求：支持多核处理
```

### 3.2 依赖安装

```bash
# 创建虚拟环境
python -m venv agent_env
source agent_env/bin/activate  # Linux
# 或 agent_env\Scripts\activate  # Windows

# 安装核心依赖
pip install numpy scipy pandas
pip install psutil
pip install sqlite3

# 安装机器学习依赖（可选，用于中层模型）
pip install torch  # 或 tensorflow

# 安装监控依赖（可选）
pip install matplotlib  # 用于可视化
```

### 3.3 配置文件

```python
# config.py
from dataclasses import dataclass
from datetime import timedelta

@dataclass
class AgentConfig:
    # 循环配置
    cycle_interval: float = 1.0  # 主循环间隔（秒）
    
    # 模块配置
    perception: PerceptionConfig = PerceptionConfig()
    drive: DriveConfig = DriveConfig()
    predictor: PredictorConfig = PredictorConfig()
    task_gen: TaskGenConfig = TaskGenConfig()
    decision: DecisionConfig = DecisionConfig()
    memory: MemoryConfig = MemoryConfig()
    review: ReviewConfig = ReviewConfig()
    evolution: EvolutionConfig = EvolutionConfig()
    monitor: MonitorConfig = MonitorConfig()
    
    # 顶层目标配置
    ultimate_goals = {
        'precision': True,  # 精度进化
        'breadth': True,    # 广度进化
        'efficiency': True  # 能效进化
    }
    
    # 边界约束
    constraints = {
        'max_cpu_percent': 20.0,
        'max_memory_percent': 20.0,
        'max_recon_iterations': 3,
        'storage_keep_ratio': 0.3
    }
    
    # 驱力权重偏置
    drive_weight_bias = {
        'safe': 0.4,
        'gain': 0.4,
        'eff': 0.2
    }
```

### 3.4 启动脚本

```python
#!/usr/bin/env python3
# main.py

import sys
import signal
from agent import SelfEvolvingAgent
from config import AgentConfig

class AgentRunner:
    def __init__(self):
        self.agent = None
        self.shutdown_requested = False
    
    def signal_handler(self, signum, frame):
        """处理系统信号"""
        print(f"\n收到信号 {signum}，正在优雅关闭...")
        self.shutdown_requested = True
        if self.agent:
            self.agent.running = False
    
    def run(self):
        """运行Agent"""
        # 注册信号处理
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # 加载配置
        config = AgentConfig()
        
        # 创建并启动Agent
        self.agent = SelfEvolvingAgent(config)
        
        print("=" * 60)
        print("自驱永续进化Agent系统启动")
        print("=" * 60)
        print(f"配置信息:")
        print(f"  - 循环间隔: {config.cycle_interval}秒")
        print(f"  - CPU上限: {config.constraints['max_cpu_percent']}%")
        print(f"  - 内存上限: {config.constraints['max_memory_percent']}%")
        print(f"  - 驱力权重: Safe={config.drive_weight_bias['safe']}, "
              f"Gain={config.drive_weight_bias['gain']}, "
              f"Eff={config.drive_weight_bias['eff']}")
        print("=" * 60)
        
        try:
            self.agent.run()
        except Exception as e:
            print(f"Agent运行异常: {e}")
            raise
        finally:
            print("Agent已停止")
            # 保存最终状态
            if self.agent:
                self.agent.memory.create_snapshot(tag="shutdown")

if __name__ == "__main__":
    runner = AgentRunner()
    runner.run()
```

### 3.5 系统服务配置（Linux）

```ini
# /etc/systemd/system/self-evolving-agent.service
[Unit]
Description=Self-Evolving Agent System
After=network.target

[Service]
Type=simple
User=agent
WorkingDirectory=/opt/agent
ExecStart=/opt/agent/venv/bin/python main.py
Restart=always
RestartSec=10

# 资源限制
CPUQuota=20%
MemoryLimit=2G

# 环境变量
Environment=PYTHONPATH=/opt/agent
Environment=AGENT_CONFIG=/opt/agent/config.yaml

[Install]
WantedBy=multi-user.target
```

## 4. 运维监控

### 4.1 日志管理

```python
import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    """配置日志系统"""
    logger = logging.getLogger('agent')
    logger.setLevel(logging.INFO)
    
    # 文件日志（轮转）
    file_handler = RotatingFileHandler(
        'logs/agent.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=10
    )
    file_handler.setLevel(logging.INFO)
    
    # 控制台日志
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    
    # 格式化
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger
```

### 4.2 健康检查

```python
def health_check(agent: SelfEvolvingAgent) -> HealthStatus:
    """系统健康检查"""
    status = HealthStatus()
    
    # 检查各模块状态
    status.modules = {
        'perception': agent.perception.is_healthy(),
        'drive_engine': agent.drive_engine.is_healthy(),
        'predictor': agent.predictor.is_healthy(),
        'task_generator': agent.task_generator.is_healthy(),
        'decision_engine': agent.decision_engine.is_healthy(),
        'memory': agent.memory.is_healthy(),
    }
    
    # 检查资源使用
    status.resource_usage = {
        'cpu': get_agent_cpu_usage(),
        'memory': get_agent_memory_usage(),
        'disk': get_storage_usage()
    }
    
    # 检查进化状态
    status.evolution = {
        'precision_score': agent.monitor.get_precision_score(),
        'breadth_score': agent.monitor.get_breadth_score(),
        'efficiency_score': agent.monitor.get_efficiency_score()
    }
    
    # 整体健康判断
    status.healthy = all(status.modules.values()) and \
                    status.resource_usage['cpu'] < 20 and \
                    status.resource_usage['memory'] < 20
    
    return status
```

## 5. 安全加固

### 5.1 沙箱限制

```python
import resource

def setup_sandbox():
    """设置沙箱限制"""
    # CPU时间限制（防止无限循环）
    resource.setrlimit(resource.RLIMIT_CPU, (3600, 3600))
    
    # 内存限制
    mem_limit = 2 * 1024 * 1024 * 1024  # 2GB
    resource.setrlimit(resource.RLIMIT_AS, (mem_limit, mem_limit))
    
    # 文件描述符限制
    resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
    
    # 进程数限制
    resource.setrlimit(resource.RLIMIT_NPROC, (50, 50))
```

### 5.2 文件访问控制

```python
# 禁止访问的系统路径
FORBIDDEN_PATHS = [
    '/etc/passwd',
    '/etc/shadow',
    '/proc/sys',
    '/sys',
    '/dev',
    '/boot',
    agent.core_code_path  # 禁止修改自身核心代码
]

def is_path_allowed(path: str) -> bool:
    """检查路径是否允许访问"""
    resolved = os.path.realpath(path)
    for forbidden in FORBIDDEN_PATHS:
        if resolved.startswith(forbidden):
            return False
    return True
```

---

系统整合与部署方案作为Agent系统的"工程实现指南"，确保所有模块能够协同工作、稳定运行、安全可控。通过清晰的架构设计、完善的部署流程和严格的运维监控，使Agent系统能够在单机环境下实现真正的永续自主进化。
