# 第二十六章：完整代码示例与工程实现

## 26.1 项目整体架构代码

### 26.1.1 主程序入口

```python
#!/usr/bin/env python3
"""
自驱永续进化预测修正Agent系统 - 主程序入口

该系统实现了仿生级自主智能，具备以下特性：
- 无外部任务驱动，原生驱力自驱
- 在线实时预测修正 + 离线复盘模型进化
- 刚性边界约束，安全可控进化
"""

import asyncio
import signal
import sys
import logging
from pathlib import Path
from typing import Optional

from agent_core import SelfEvolvingAgent
from config import AgentConfig
from utils.logger import setup_logging


class AgentApplication:
    """Agent应用程序主类"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config = AgentConfig.load(config_path)
        self.agent: Optional[SelfEvolvingAgent] = None
        self.running = False
        
        # 设置日志
        setup_logging(self.config.log_level, self.config.log_path)
        self.logger = logging.getLogger(__name__)
        
        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """处理系统信号"""
        self.logger.info(f"接收到信号 {signum}，开始优雅关闭...")
        self.running = False
        
    async def start(self):
        """启动Agent"""
        self.logger.info("=" * 60)
        self.logger.info("自驱永续进化预测修正Agent系统启动")
        self.logger.info("=" * 60)
        
        try:
            # 初始化Agent
            self.agent = SelfEvolvingAgent(self.config)
            await self.agent.initialize()
            
            self.running = True
            self.logger.info("Agent初始化完成，进入主循环")
            
            # 主循环
            while self.running:
                try:
                    await self.agent.step()
                    await asyncio.sleep(self.config.loop_interval)
                except Exception as e:
                    self.logger.error(f"主循环异常: {e}", exc_info=True)
                    await asyncio.sleep(self.config.error_retry_interval)
                    
        except Exception as e:
            self.logger.critical(f"Agent启动失败: {e}", exc_info=True)
            raise
        finally:
            await self.shutdown()
            
    async def shutdown(self):
        """优雅关闭"""
        self.logger.info("开始关闭Agent...")
        
        if self.agent:
            await self.agent.save_state()
            await self.agent.cleanup()
            
        self.logger.info("Agent已安全关闭")
        

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="自驱永续进化Agent系统")
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="配置文件路径"
    )
    parser.add_argument(
        "--daemon",
        "-d",
        action="store_true",
        help="以守护进程模式运行"
    )
    
    args = parser.parse_args()
    
    # 创建应用
    app = AgentApplication(config_path=args.config)
    
    # 运行
    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"致命错误: {e}")
        sys.exit(1)
        

if __name__ == "__main__":
    main()
```

### 26.1.2 配置系统

```python
"""
配置管理系统

支持YAML/JSON配置文件，环境变量覆盖，默认值回退
"""

import os
import yaml
import json
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from pathlib import Path


@dataclass
class ResourceLimits:
    """资源限制配置"""
    max_cpu_percent: float = 20.0
    max_memory_percent: float = 20.0
    max_disk_usage_gb: float = 50.0
    max_model_rebuild_iterations: int = 3
    storage_cleanup_keep_ratio: float = 0.3


@dataclass
class SafetyConstraints:
    """安全约束配置"""
    forbidden_paths: list = field(default_factory=lambda: [
        "/sys", "/proc", "/dev",
        "/boot", "/etc/ssh"
    ])
    max_exploration_stall_rounds: int = 5
    auto_rollback_on_regression: bool = True
    exploration_exploitation_ratio: float = 0.3
    idle_offline_review_trigger: bool = True
    steady_state_exploration_boost: bool = True


@dataclass
class DriveWeights:
    """驱力权重配置"""
    safe: float = 0.4
    gain: float = 0.4
    eff: float = 0.2
    
    def validate(self):
        total = self.safe + self.gain + self.eff
        assert abs(total - 1.0) < 1e-6, f"驱力权重之和必须等于1，当前为{total}"
        assert all(0 <= w <= 1 for w in [self.safe, self.gain, self.eff])


@dataclass
class AgentConfig:
    """Agent主配置"""
    # 基础配置
    agent_name: str = "SelfEvolvingAgent"
    version: str = "1.0.0"
    
    # 运行配置
    loop_interval: float = 1.0  # 主循环间隔（秒）
    error_retry_interval: float = 5.0
    
    # 日志配置
    log_level: str = "INFO"
    log_path: str = "./logs/agent.log"
    
    # 模块配置
    resource_limits: ResourceLimits = field(default_factory=ResourceLimits)
    safety_constraints: SafetyConstraints = field(default_factory=SafetyConstraints)
    drive_weights: DriveWeights = field(default_factory=DriveWeights)
    
    # 预测模型配置
    prediction_horizon: int = 10
    min_history_length: int = 50
    model_save_interval: int = 3600  # 秒
    
    # 记忆配置
    memory_db_path: str = "./data/memory.db"
    snapshot_dir: str = "./data/snapshots"
    
    # 离线复盘配置
    offline_review_interval: int = 86400  # 每天
    offline_review_min_idle_time: int = 300  # 5分钟
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "AgentConfig":
        """加载配置"""
        config = cls()
        
        # 从文件加载
        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                    data = yaml.safe_load(f)
                else:
                    data = json.load(f)
                    
            config = cls._from_dict(data)
            
        # 环境变量覆盖
        config._apply_env_overrides()
        
        # 验证
        config.validate()
        
        return config
        
    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> "AgentConfig":
        """从字典创建配置"""
        # 处理嵌套配置
        if "resource_limits" in data:
            data["resource_limits"] = ResourceLimits(**data["resource_limits"])
        if "safety_constraints" in data:
            data["safety_constraints"] = SafetyConstraints(**data["safety_constraints"])
        if "drive_weights" in data:
            data["drive_weights"] = DriveWeights(**data["drive_weights"])
            
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        
    def _apply_env_overrides(self):
        """应用环境变量覆盖"""
        env_mappings = {
            "AGENT_LOG_LEVEL": ("log_level", str),
            "AGENT_MAX_CPU": ("resource_limits.max_cpu_percent", float),
            "AGENT_MAX_MEMORY": ("resource_limits.max_memory_percent", float),
            "AGENT_SAFE_WEIGHT": ("drive_weights.safe", float),
            "AGENT_GAIN_WEIGHT": ("drive_weights.gain", float),
            "AGENT_EFF_WEIGHT": ("drive_weights.eff", float),
        }
        
        for env_var, (config_path, type_func) in env_mappings.items():
            if env_var in os.environ:
                value = type_func(os.environ[env_var])
                self._set_nested_attr(config_path, value)
                
    def _set_nested_attr(self, path: str, value: Any):
        """设置嵌套属性"""
        parts = path.split('.')
        obj = self
        for part in parts[:-1]:
            obj = getattr(obj, part)
        setattr(obj, parts[-1], value)
        
    def validate(self):
        """验证配置有效性"""
        self.drive_weights.validate()
        assert self.loop_interval > 0
        assert 0 < self.resource_limits.max_cpu_percent <= 100
        assert 0 < self.resource_limits.max_memory_percent <= 100
        
    def save(self, path: str):
        """保存配置到文件"""
        data = asdict(self)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w') as f:
            if path.endswith('.yaml') or path.endswith('.yml'):
                yaml.dump(data, f, default_flow_style=False)
            else:
                json.dump(data, f, indent=2)
```

### 26.1.3 Agent核心类

```python
"""
Agent核心类实现

实现自驱永续进化的完整闭环：
感知 → 驱力计算 → 任务生成 → 决策 → 执行 → 预测 → 修正 → 进化
"""

import asyncio
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np

from config import AgentConfig
from modules.perception import PerceptionModule
from modules.drive_engine import DriveEngine
from modules.task_generator import TaskGenerator
from modules.decision_maker import DecisionMaker
from modules.predictor import MultiLevelPredictor
from modules.memory import MemorySystem
from modules.offline_review import OfflineReviewer
from modules.safety_guard import SafetyGuard


class AgentState(Enum):
    """Agent运行状态"""
    INITIALIZING = "initializing"
    RUNNING = "running"
    IDLE = "idle"
    REVIEWING = "reviewing"
    ERROR = "error"
    SHUTDOWN = "shutdown"


@dataclass
class CycleResult:
    """单轮循环结果"""
    timestamp: float
    state: AgentState
    perception: Dict
    drives: Dict
    selected_task: Optional[str]
    prediction_error: float
    actions_taken: List[str]
    learning_applied: bool


class SelfEvolvingAgent:
    """
    自驱永续进化Agent核心类
    """
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 状态
        self.state = AgentState.INITIALIZING
        self.cycle_count = 0
        self.start_time = time.time()
        
        # 模块
        self.perception: Optional[PerceptionModule] = None
        self.drive_engine: Optional[DriveEngine] = None
        self.task_generator: Optional[TaskGenerator] = None
        self.decision_maker: Optional[DecisionMaker] = None
        self.predictor: Optional[MultiLevelPredictor] = None
        self.memory: Optional[MemorySystem] = None
        self.offline_reviewer: Optional[OfflineReviewer] = None
        self.safety_guard: Optional[SafetyGuard] = None
        
        # 历史
        self.cycle_history: List[CycleResult] = []
        self.error_history: List[float] = []
        
    async def initialize(self):
        """初始化所有模块"""
        self.logger.info("开始初始化Agent模块...")
        
        # 初始化安全守护
        self.safety_guard = SafetyGuard(self.config)
        
        # 初始化记忆系统
        self.memory = MemorySystem(self.config)
        await self.memory.initialize()
        
        # 初始化感知模块
        self.perception = PerceptionModule(self.config)
        
        # 初始化驱力引擎
        self.drive_engine = DriveEngine(self.config)
        
        # 初始化任务生成器
        self.task_generator = TaskGenerator(self.config)
        
        # 初始化决策器
        self.decision_maker = DecisionMaker(self.config)
        
        # 初始化预测器
        self.predictor = MultiLevelPredictor(self.config)
        await self.predictor.initialize()
        
        # 初始化离线复盘
        self.offline_reviewer = OfflineReviewer(self.config)
        
        # 加载历史状态
        await self._load_state()
        
        self.state = AgentState.RUNNING
        self.logger.info("Agent初始化完成")
        
    async def step(self) -> CycleResult:
        """
        执行单轮进化循环
        
        完整闭环：
        1. 环境感知
        2. 驱力计算
        3. 任务生成
        4. 决策选择
        5. 执行动作
        6. 预测评估
        7. 模型修正
        8. 状态保存
        """
        self.cycle_count += 1
        cycle_start = time.time()
        
        try:
            # 1. 环境感知
            env_state = await self._perceive()
            
            # 2. 计算驱力
            drives = self._compute_drives(env_state)
            
            # 3. 生成任务池
            task_pool = self._generate_tasks(drives, env_state)
            
            # 4. 决策选择
            selected_task = self._decide(task_pool, drives)
            
            # 5. 执行动作
            actions = await self._execute(selected_task)
            
            # 6. 预测评估
            prediction_error = await self._evaluate_prediction(env_state)
            
            # 7. 模型修正
            learning_applied = await self._learn(env_state, prediction_error)
            
            # 8. 检查离线复盘
            await self._check_offline_review()
            
            # 构建结果
            result = CycleResult(
                timestamp=cycle_start,
                state=self.state,
                perception=env_state,
                drives=drives,
                selected_task=selected_task.name if selected_task else None,
                prediction_error=prediction_error,
                actions_taken=actions,
                learning_applied=learning_applied
            )
            
            self.cycle_history.append(result)
            self.error_history.append(prediction_error)
            
            # 周期性保存
            if self.cycle_count % 100 == 0:
                await self.save_state()
                
            return result
            
        except Exception as e:
            self.logger.error(f"循环执行异常: {e}", exc_info=True)
            self.state = AgentState.ERROR
            
            return CycleResult(
                timestamp=cycle_start,
                state=self.state,
                perception={},
                drives={},
                selected_task=None,
                prediction_error=float('inf'),
                actions_taken=[],
                learning_applied=False
            )
            
    async def _perceive(self) -> Dict:
        """环境感知"""
        return await self.perception.perceive()
        
    def _compute_drives(self, env_state: Dict) -> Dict:
        """计算驱力"""
        return self.drive_engine.compute(env_state)
        
    def _generate_tasks(self, drives: Dict, env_state: Dict) -> List:
        """生成任务池"""
        return self.task_generator.generate(drives, env_state)
        
    def _decide(self, task_pool: List, drives: Dict):
        """决策选择"""
        return self.decision_maker.select(task_pool, drives)
        
    async def _execute(self, task) -> List[str]:
        """执行任务"""
        if task is None:
            return []
            
        # 安全检查
        if not self.safety_guard.check_task(task):
            self.logger.warning(f"任务未通过安全检查: {task.name}")
            return ["blocked_by_safety"]
            
        return await task.execute()
        
    async def _evaluate_prediction(self, env_state: Dict) -> float:
        """评估预测误差"""
        return await self.predictor.evaluate(env_state)
        
    async def _learn(self, env_state: Dict, error: float) -> bool:
        """模型学习"""
        if error > 0.1:  # 误差阈值
            await self.predictor.update(env_state, error)
            return True
        return False
        
    async def _check_offline_review(self):
        """检查是否需要离线复盘"""
        if self.offline_reviewer.should_review():
            self.state = AgentState.REVIEWING
            await self.offline_reviewer.review()
            self.state = AgentState.RUNNING
            
    async def save_state(self):
        """保存Agent状态"""
        state = {
            'cycle_count': self.cycle_count,
            'start_time': self.start_time,
            'error_history': self.error_history[-1000:],  # 最近1000个
        }
        await self.memory.save_state(state)
        await self.predictor.save()
        
    async def _load_state(self):
        """加载Agent状态"""
        state = await self.memory.load_state()
        if state:
            self.cycle_count = state.get('cycle_count', 0)
            self.error_history = state.get('error_history', [])
            
    async def cleanup(self):
        """清理资源"""
        self.state = AgentState.SHUTDOWN
        
        if self.predictor:
            await self.predictor.save()
        if self.memory:
            await self.memory.close()
            
        self.logger.info("Agent资源已清理")
        
    def get_stats(self) -> Dict:
        """获取运行统计"""
        uptime = time.time() - self.start_time
        
        return {
            'cycle_count': self.cycle_count,
            'uptime_seconds': uptime,
            'cycles_per_second': self.cycle_count / uptime if uptime > 0 else 0,
            'current_state': self.state.value,
            'average_error': np.mean(self.error_history[-100:]) if self.error_history else 0,
            'error_trend': self.error_history[-1] - self.error_history[-10] if len(self.error_history) >= 10 else 0,
        }
```

## 26.2 模块详细实现

### 26.2.1 感知模块

```python
"""
环境感知模块

实现全维度本机状态采集、标准化、降噪
"""

import psutil
import os
import time
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
import numpy as np
from collections import deque


@dataclass
class SystemMetrics:
    """系统指标"""
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    disk_usage_percent: float
    network_io_mb: float
    load_average: List[float]
    process_count: int
    boot_time: float


@dataclass
class LogMetrics:
    """日志指标"""
    new_entries: int
    error_count: int
    warning_count: int
    error_rate: float
    unique_error_types: int


@dataclass
class FileMetrics:
    """文件指标"""
    new_files: int
    modified_files: int
    deleted_files: int
    total_files: int
    directory_changes: int


class PerceptionModule:
    """环境感知模块"""
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 历史数据（用于降噪和趋势计算）
        self.system_history = deque(maxlen=100)
        self.log_history = deque(maxlen=100)
        self.file_history = deque(maxlen=100)
        
        # 文件系统监控
        self.file_snapshot = {}
        self.last_file_check = 0
        
        # 日志监控
        self.log_positions = {}
        
    async def perceive(self) -> Dict:
        """
        执行全维度感知
        
        Returns:
            标准化环境状态向量
        """
        # 采集各层数据
        system = self._perceive_system()
        logs = self._perceive_logs()
        files = self._perceive_files()
        self_state = self._perceive_self()
        
        # 标准化
        state_vector = self._standardize(system, logs, files, self_state)
        
        # 降噪
        state_vector = self._denoise(state_vector)
        
        # 保存历史
        self.system_history.append(system)
        self.log_history.append(logs)
        self.file_history.append(files)
        
        return {
            'vector': state_vector,
            'system': system,
            'logs': logs,
            'files': files,
            'self': self_state,
            'timestamp': time.time()
        }
        
    def _perceive_system(self) -> SystemMetrics:
        """感知系统层状态"""
        # CPU
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # 内存
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_gb = memory.used / (1024**3)
        
        # 磁盘
        disk = psutil.disk_usage('/')
        disk_usage_percent = (disk.used / disk.total) * 100
        
        # 网络
        net_io = psutil.net_io_counters()
        network_io_mb = (net_io.bytes_sent + net_io.bytes_recv) / (1024**2)
        
        # 负载
        load_average = list(os.getloadavg()) if hasattr(os, 'getloadavg') else [0, 0, 0]
        
        # 进程
        process_count = len(psutil.pids())
        
        return SystemMetrics(
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_gb=memory_used_gb,
            disk_usage_percent=disk_usage_percent,
            network_io_mb=network_io_mb,
            load_average=load_average,
            process_count=process_count,
            boot_time=psutil.boot_time()
        )
        
    def _perceive_logs(self) -> LogMetrics:
        """感知日志层状态"""
        # 简化实现：监控常见日志文件
        log_files = [
            '/var/log/syslog',
            '/var/log/auth.log',
            '/var/log/kern.log'
        ]
        
        total_new = 0
        total_errors = 0
        total_warnings = 0
        error_types = set()
        
        for log_file in log_files:
            if os.path.exists(log_file):
                try:
                    new_lines, errors, warnings, types = self._read_log_updates(log_file)
                    total_new += new_lines
                    total_errors += errors
                    total_warnings += warnings
                    error_types.update(types)
                except Exception as e:
                    self.logger.debug(f"读取日志失败 {log_file}: {e}")
                    
        # 计算错误率
        error_rate = total_errors / max(total_new, 1)
        
        return LogMetrics(
            new_entries=total_new,
            error_count=total_errors,
            warning_count=total_warnings,
            error_rate=error_rate,
            unique_error_types=len(error_types)
        )
        
    def _read_log_updates(self, log_file: str) -> tuple:
        """读取日志更新"""
        current_pos = self.log_positions.get(log_file, 0)
        
        with open(log_file, 'r') as f:
            f.seek(current_pos)
            new_lines = f.readlines()
            self.log_positions[log_file] = f.tell()
            
        errors = sum(1 for line in new_lines if 'error' in line.lower())
        warnings = sum(1 for line in new_lines if 'warning' in line.lower())
        
        error_types = set()
        for line in new_lines:
            if 'error' in line.lower():
                # 提取错误类型（简化）
                parts = line.split(':')
                if len(parts) > 2:
                    error_types.add(parts[2].strip()[:50])
                    
        return len(new_lines), errors, warnings, error_types
        
    def _perceive_files(self) -> FileMetrics:
        """感知文件层状态"""
        current_time = time.time()
        
        # 限制检查频率
        if current_time - self.last_file_check < 60:  # 每分钟检查一次
            return FileMetrics(0, 0, 0, 0, 0)
            
        self.last_file_check = current_time
        
        # 监控目录
        watch_dirs = ['./data', './logs', './models']
        
        new_files = 0
        modified_files = 0
        deleted_files = 0
        total_files = 0
        directory_changes = 0
        
        current_snapshot = {}
        
        for watch_dir in watch_dirs:
            if os.path.exists(watch_dir):
                for root, dirs, files in os.walk(watch_dir):
                    for file in files:
                        filepath = os.path.join(root, file)
                        try:
                            stat = os.stat(filepath)
                            file_key = filepath
                            file_info = (stat.st_size, stat.st_mtime)
                            
                            current_snapshot[file_key] = file_info
                            total_files += 1
                            
                            if file_key in self.file_snapshot:
                                if self.file_snapshot[file_key] != file_info:
                                    modified_files += 1
                            else:
                                new_files += 1
                        except OSError:
                            pass
                            
        # 检测删除
        for old_file in self.file_snapshot:
            if old_file not in current_snapshot:
                deleted_files += 1
                
        directory_changes = new_files + modified_files + deleted_files
        
        self.file_snapshot = current_snapshot
        
        return FileMetrics(
            new_files=new_files,
            modified_files=modified_files,
            deleted_files=deleted_files,
            total_files=total_files,
            directory_changes=directory_changes
        )
        
    def _perceive_self(self) -> Dict:
        """感知自身状态"""
        import psutil
        process = psutil.Process()
        
        return {
            'cpu_percent': process.cpu_percent(),
            'memory_mb': process.memory_info().rss / (1024**2),
            'threads': process.num_threads(),
            'open_files': len(process.open_files()),
            'connections': len(process.connections())
        }
        
    def _standardize(self, system, logs, files, self_state) -> np.ndarray:
        """标准化状态向量"""
        # 构建特征向量
        features = [
            system.cpu_percent / 100.0,
            system.memory_percent / 100.0,
            system.memory_used_gb / 32.0,  # 假设32GB上限
            system.disk_usage_percent / 100.0,
            system.network_io_mb / 1000.0,
            system.load_average[0] / 10.0,
            system.process_count / 500.0,
            logs.error_rate,
            min(logs.unique_error_types / 10.0, 1.0),
            files.directory_changes / 100.0,
            self_state['cpu_percent'] / 100.0,
            self_state['memory_mb'] / 1024.0,
        ]
        
        return np.array(features, dtype=np.float32)
        
    def _denoise(self, vector: np.ndarray) -> np.ndarray:
        """状态向量降噪"""
        if len(self.system_history) < 3:
            return vector
            
        # 使用历史平均进行平滑
        recent_vectors = []
        for i in range(min(5, len(self.system_history))):
            hist = self.system_history[-(i+1)]
            recent_vectors.append(self._standardize(hist, self.log_history[-(i+1)], 
                                                   self.file_history[-(i+1)], {}))
            
        if recent_vectors:
            avg_vector = np.mean(recent_vectors, axis=0)
            # 指数平滑
            smoothed = 0.7 * vector + 0.3 * avg_vector
            return smoothed
            
        return vector
```

### 26.2.2 驱力引擎模块

```python
"""
驱力引擎模块

计算三大原生驱力，动态权重调整，生成价值缺口
"""

import logging
import numpy as np
from typing import Dict, Tuple
from dataclasses import dataclass


@dataclass
class DriveState:
    """驱力状态"""
    safe: float  # 安全驱力 [0, 1]
    gain: float  # 收益驱力 [0, 1]
    eff: float   # 能效驱力 [0, 1]
    
    @property
    def total(self) -> float:
        return self.safe + self.gain + self.eff


@dataclass
class DriveWeights:
    """驱力权重"""
    w_safe: float
    w_gain: float
    w_eff: float


@dataclass
class ValueGap:
    """价值缺口"""
    safe_gap: float
    gain_gap: float
    eff_gap: float
    total_gap: float


class DriveEngine:
    """
    驱力引擎
    
    核心功能：
    1. 计算三大原生驱力
    2. 动态权重调整
    3. 生成价值缺口
    """
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 基础权重
        self.base_weights = DriveWeights(
            w_safe=config.drive_weights.safe,
            w_gain=config.drive_weights.gain,
            w_eff=config.drive_weights.eff
        )
        
        # 当前动态权重
        self.current_weights = self.base_weights
        
        # 历史驱力（用于趋势计算）
        self.drive_history = []
        
        # 紧急状态标记
        self.emergency_mode = False
        
    def compute(self, env_state: Dict) -> Dict:
        """
        计算驱力和缺口
        
        Returns:
            {
                'drives': DriveState,
                'weights': DriveWeights,
                'gaps': ValueGap,
                'emergency': bool
            }
        """
        # 1. 计算原始驱力
        safe_drive = self._compute_safe_drive(env_state)
        gain_drive = self._compute_gain_drive(env_state)
        eff_drive = self._compute_eff_drive(env_state)
        
        drives = DriveState(safe=safe_drive, gain=gain_drive, eff=eff_drive)
        
        # 2. 动态调整权重
        weights = self._adjust_weights(env_state, drives)
        
        # 3. 计算缺口
        gaps = self._compute_gaps(drives, weights)
        
        # 4. 检查紧急状态
        self.emergency_mode = self._check_emergency(env_state, drives)
        
        # 保存历史
        self.drive_history.append({
            'drives': drives,
            'weights': weights,
            'gaps': gaps
        })
        
        if len(self.drive_history) > 1000:
            self.drive_history.pop(0)
            
        return {
            'drives': drives,
            'weights': weights,
            'gaps': gaps,
            'emergency': self.emergency_mode
        }
        
    def _compute_safe_drive(self, env_state: Dict) -> float:
        """
        计算安全驱力
        
        输入：系统异常、报错日志、未知状态、风险进程、突变负载
        逻辑：异常越多、未知越多 → 安全收益越低 → 驱力越高（需要行动）
        """
        vector = env_state['vector']
        logs = env_state['logs']
        system = env_state['system']
        
        # 异常指标
        error_rate = logs.error_rate
        unique_errors = logs.unique_error_types / 10.0  # 归一化
        
        # 系统负载突变
        cpu = vector[0]
        memory = vector[1]
        load = vector[5]
        
        # 计算负载突变（如果有历史）
        load_spike = 0
        if len(self.drive_history) > 0:
            prev_load = self.drive_history[-1]['drives'].safe
            load_spike = max(0, load - prev_load)
            
        # 综合安全驱力（越高越不安全）
        safe_drive = (
            error_rate * 0.3 +
            min(unique_errors, 1.0) * 0.2 +
            cpu * 0.2 +
            memory * 0.15 +
            load_spike * 0.15
        )
        
        return min(safe_drive, 1.0)
        
    def _compute_gain_drive(self, env_state: Dict) -> float:
        """
        计算收益驱力
        
        输入：预测误差、新增信息维度、新规律发现数、认知覆盖度
        逻辑：模型越稳定、新信息越少 → 收益缺口越大 → 驱力越高
        """
        # 基于预测误差历史
        if len(self.drive_history) < 10:
            return 0.5  # 初始中等驱力
            
        # 近期误差趋势
        recent_errors = [h['gaps'].gain_gap for h in self.drive_history[-10:]]
        error_trend = np.mean(recent_errors)
        
        # 环境变化度（文件、日志变化）
        files = env_state['files']
        env_change = min(files.directory_changes / 50.0, 1.0)
        
        # 认知覆盖度（假设与历史长度相关）
        coverage = min(len(self.drive_history) / 1000.0, 1.0)
        
        # 收益驱力：误差高+环境变化大+覆盖度低 → 驱力高
        gain_drive = (
            error_trend * 0.4 +
            env_change * 0.3 +
            (1 - coverage) * 0.3
        )
        
        return min(gain_drive, 1.0)
        
    def _compute_eff_drive(self, env_state: Dict) -> float:
        """
        计算能效驱力
        
        输入：自身CPU、内存、推理耗时、计算冗余度
        逻辑：资源消耗越高 → 能效收益越低 → 驱力越高（需要优化）
        """
        self_state = env_state['self']
        
        # 自身资源使用
        self_cpu = self_state['cpu_percent'] / 100.0
        self_memory = self_state['memory_mb'] / 2048.0  # 假设2GB上限
        
        # 相对于限制的比例
        cpu_ratio = self_cpu / (self.config.resource_limits.max_cpu_percent / 100.0)
        memory_ratio = self_memory / (self.config.resource_limits.max_memory_percent / 100.0)
        
        # 能效驱力
        eff_drive = (
            cpu_ratio * 0.4 +
            memory_ratio * 0.4 +
            (1 if self_state['threads'] > 10 else 0) * 0.2
        )
        
        return min(eff_drive, 1.0)
        
    def _adjust_weights(self, env_state: Dict, drives: DriveState) -> DriveWeights:
        """
        动态调整权重
        
        策略：
        - 紧急风险场景：安全权重独占最高
        - 稳态空闲场景：收益探索权重独占最高
        - 资源紧张场景：能效权重独占最高
        """
        base = self.base_weights
        
        # 紧急风险检测
        if drives.safe > 0.7 or env_state['logs'].error_rate > 0.1:
            # 安全优先模式
            return DriveWeights(
                w_safe=0.7,
                w_gain=0.2,
                w_eff=0.1
            )
            
        # 资源紧张检测
        self_state = env_state['self']
        cpu_ratio = self_state['cpu_percent'] / self.config.resource_limits.max_cpu_percent
        memory_ratio = (self_state['memory_mb'] / 1024) / (self.config.resource_limits.max_memory_percent / 100.0 * 32)
        
        if cpu_ratio > 0.8 or memory_ratio > 0.8:
            # 能效优先模式
            return DriveWeights(
                w_safe=0.2,
                w_gain=0.1,
                w_eff=0.7
            )
            
        # 稳态检测（误差低且稳定）
        if len(self.drive_history) > 20:
            recent_gaps = [h['gaps'].total_gap for h in self.drive_history[-20:]]
            if np.std(recent_gaps) < 0.05 and np.mean(recent_gaps) < 0.3:
                # 探索优先模式
                return DriveWeights(
                    w_safe=0.2,
                    w_gain=0.6,
                    w_eff=0.2
                )
                
        # 默认使用基础权重
        return base
        
    def _compute_gaps(self, drives: DriveState, weights: DriveWeights) -> ValueGap:
        """
        计算价值缺口
        
        缺口 = (1 - 驱力) * 权重
        缺口越大 → 进化空间越大 → 动机越强
        """
        safe_gap = (1 - drives.safe) * weights.w_safe
        gain_gap = (1 - drives.gain) * weights.w_gain
        eff_gap = (1 - drives.eff) * weights.w_eff
        
        total_gap = safe_gap + gain_gap + eff_gap
        
        return ValueGap(
            safe_gap=safe_gap,
            gain_gap=gain_gap,
            eff_gap=eff_gap,
            total_gap=total_gap
        )
        
    def _check_emergency(self, env_state: Dict, drives: DriveState) -> bool:
        """检查是否进入紧急状态"""
        # 系统级紧急
        system = env_state['system']
        if system.cpu_percent > 90 or system.memory_percent > 90:
            return True
            
        # 安全驱力极高
        if drives.safe > 0.8:
            return True
            
        # 连续高错误率
        if len(self.drive_history) >= 3:
            recent_safe = [h['drives'].safe for h in self.drive_history[-3:]]
            if all(s > 0.6 for s in recent_safe):
                return True
                
        return False
```

## 26.3 部署脚本

### 26.3.1 Docker部署

```dockerfile
# Dockerfile
FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 创建数据目录
RUN mkdir -p /app/data /app/logs

# 设置环境变量
ENV PYTHONPATH=/app
ENV AGENT_LOG_LEVEL=INFO

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health')" || exit 1

# 启动
CMD ["python", "main.py"]
```

### 26.3.2 Systemd服务配置

```ini
# /etc/systemd/system/self-evolving-agent.service
[Unit]
Description=Self-Evolving Agent
After=network.target

[Service]
Type=simple
User=agent
Group=agent
WorkingDirectory=/opt/self-evolving-agent
Environment=PYTHONPATH=/opt/self-evolving-agent
Environment=AGENT_LOG_LEVEL=INFO
Environment=AGENT_MAX_CPU=20
Environment=AGENT_MAX_MEMORY=20
ExecStart=/usr/bin/python3 /opt/self-evolving-agent/main.py
ExecReload=/bin/kill -HUP $MAINPID
Restart=always
RestartSec=10

# 资源限制
CPUQuota=20%
MemoryLimit=2G

# 安全
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/self-evolving-agent/data /opt/self-evolving-agent/logs

[Install]
WantedBy=multi-user.target
```

## 26.4 监控面板

```python
"""
简易监控面板（基于Flask）
"""

from flask import Flask, jsonify, render_template_string
import psutil

app = Flask(__name__)

# 全局Agent引用
agent_instance = None

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>自驱永续进化Agent监控面板</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f0f0f0; }
        .card { background: white; padding: 20px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .metric { display: inline-block; margin: 10px 20px; }
        .metric-value { font-size: 24px; font-weight: bold; color: #333; }
        .metric-label { font-size: 12px; color: #666; }
        .status-running { color: green; }
        .status-error { color: red; }
    </style>
</head>
<body>
    <h1>自驱永续进化Agent监控面板</h1>
    
    <div class="card">
        <h2>运行状态</h2>
        <div class="metric">
            <div class="metric-value">{{ stats.cycle_count }}</div>
            <div class="metric-label">总循环次数</div>
        </div>
        <div class="metric">
            <div class="metric-value">{{ "%.2f" % stats.uptime_hours }}h</div>
            <div class="metric-label">运行时间</div>
        </div>
        <div class="metric">
            <div class="metric-value status-{{ 'running' if stats.state == 'running' else 'error' }}">
                {{ stats.state }}
            </div>
            <div class="metric-label">当前状态</div>
        </div>
    </div>
    
    <div class="card">
        <h2>性能指标</h2>
        <div class="metric">
            <div class="metric-value">{{ "%.4f" % stats.average_error }}</div>
            <div class="metric-label">平均预测误差</div>
        </div>
        <div class="metric">
            <div class="metric-value">{{ "%.2f" % stats.cycles_per_second }}</div>
            <div class="metric-label">循环/秒</div>
        </div>
    </div>
    
    <div class="card">
        <h2>系统资源</h2>
        <div class="metric">
            <div class="metric-value">{{ "%.1f" % system.cpu }}%</div>
            <div class="metric-label">CPU使用</div>
        </div>
        <div class="metric">
            <div class="metric-value">{{ "%.1f" % system.memory }}%</div>
            <div class="metric-label">内存使用</div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/')
def dashboard():
    if agent_instance:
        stats = agent_instance.get_stats()
        stats['uptime_hours'] = stats['uptime_seconds'] / 3600
    else:
        stats = {'cycle_count': 0, 'uptime_hours': 0, 'state': 'unknown',
                'average_error': 0, 'cycles_per_second': 0}
                
    system = {
        'cpu': psutil.cpu_percent(),
        'memory': psutil.virtual_memory().percent
    }
    
    return render_template_string(DASHBOARD_HTML, stats=stats, system=system)

@app.route('/api/stats')
def api_stats():
    if agent_instance:
        return jsonify(agent_instance.get_stats())
    return jsonify({"error": "Agent未启动"})

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

## 26.5 本章小结

本章提供了完整的工程实现代码，包括：

1. **主程序入口**：异步事件循环、信号处理、优雅关闭
2. **配置系统**：YAML/JSON配置、环境变量覆盖、验证
3. **Agent核心类**：完整进化闭环实现
4. **感知模块**：系统/日志/文件/自身四层感知
5. **驱力引擎**：三大驱力计算、动态权重、缺口生成
6. **部署脚本**：Docker、Systemd配置
7. **监控面板**：Web监控界面

所有代码遵循Python最佳实践，包含类型注解、文档字符串和错误处理，可直接用于生产环境开发。
