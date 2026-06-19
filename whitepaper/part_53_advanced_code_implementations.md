# 第五十三章 高级代码实现与工程细节

## 53.1 引言

本章提供自驱永续进化Agent系统核心模块的完整代码实现，包括环境感知、驱力计算、预测模型、任务生成、决策优化等关键组件。代码采用Python 3.9+编写，遵循PEP 8规范，包含完整的类型注解和文档字符串。

## 53.2 核心框架实现

### 53.2.1 系统主循环

```python
import asyncio
import logging
import signal
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple, TypeVar, Generic
import numpy as np
import psutil


class SystemState(Enum):
    INITIALIZING = auto()
    RUNNING = auto()
    PAUSED = auto()
    SHUTTING_DOWN = auto()
    ERROR = auto()


@dataclass
class SystemMetrics:
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_usage: float
    network_io: Tuple[int, int]
    process_count: int
    thread_count: int
    
    def to_vector(self) -> np.ndarray:
        return np.array([
            self.cpu_percent,
            self.memory_percent,
            self.disk_usage,
            self.network_io[0],
            self.network_io[1],
            self.process_count,
            self.thread_count
        ])


class AgentCore:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.state = SystemState.INITIALIZING
        self.metrics_history: List[SystemMetrics] = []
        self.modules: Dict[str, Any] = {}
        self.logger = logging.getLogger(__name__)
        self._shutdown_event = asyncio.Event()
        
    async def initialize(self):
        self.logger.info("Initializing Agent Core...")
        self.modules['perception'] = EnvironmentPerceptionModule(self.config)
        self.modules['drive_engine'] = DriveEngineModule(self.config)
        self.modules['prediction'] = PredictionModule(self.config)
        self.modules['task_generator'] = TaskGeneratorModule(self.config)
        self.modules['decision'] = DecisionModule(self.config)
        self.modules['memory'] = MemoryModule(self.config)
        self.modules['optimizer'] = OptimizerModule(self.config)
        
        for module in self.modules.values():
            await module.initialize()
        
        self.state = SystemState.RUNNING
        self.logger.info("Agent Core initialized successfully")
        
    async def run(self):
        self.logger.info("Starting main loop...")
        while not self._shutdown_event.is_set():
            try:
                cycle_start = datetime.now()
                
                # Phase 1: Environment Perception
                env_state = await self.modules['perception'].perceive()
                
                # Phase 2: Drive Engine
                drive_signals = await self.modules['drive_engine'].compute(env_state)
                
                # Phase 3: Prediction
                predictions = await self.modules['prediction'].predict(env_state)
                
                # Phase 4: Error Evaluation
                errors = self._compute_prediction_errors(env_state, predictions)
                
                # Phase 5: Task Generation
                tasks = await self.modules['task_generator'].generate(
                    env_state, drive_signals, errors
                )
                
                # Phase 6: Decision Making
                selected_task = await self.modules['decision'].select(tasks)
                
                # Phase 7: Execution
                if selected_task:
                    result = await selected_task.execute()
                    await self.modules['memory'].store_experience(
                        env_state, selected_task, result, errors
                    )
                
                # Phase 8: Optimization
                await self.modules['optimizer'].optimize(errors)
                
                # Phase 9: Resource Check
                await self._enforce_resource_limits()
                
                cycle_duration = (datetime.now() - cycle_start).total_seconds()
                await self._adaptive_sleep(cycle_duration)
                
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                await self._handle_error(e)
                
    async def _adaptive_sleep(self, cycle_duration: float):
        target_cycle_time = self.config.get('target_cycle_time', 1.0)
        sleep_time = max(0, target_cycle_time - cycle_duration)
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)
            
    async def _enforce_resource_limits(self):
        process = psutil.Process()
        cpu_percent = process.cpu_percent()
        memory_info = process.memory_info()
        memory_percent = memory_info.rss / psutil.virtual_memory().total * 100
        
        max_cpu = self.config.get('max_cpu_percent', 20)
        max_memory = self.config.get('max_memory_percent', 20)
        
        if cpu_percent > max_cpu or memory_percent > max_memory:
            self.logger.warning(
                f"Resource limit exceeded: CPU={cpu_percent:.1f}%, "
                f"Memory={memory_percent:.1f}%"
            )
            await self._throttle()
            
    async def _throttle(self):
        await asyncio.sleep(self.config.get('throttle_delay', 5.0))
        
    async def _handle_error(self, error: Exception):
        if isinstance(error, ResourceExhaustedError):
            await self._emergency_cleanup()
        elif isinstance(error, PredictionDivergenceError):
            await self.modules['prediction'].reset()
            
    async def _emergency_cleanup(self):
        self.logger.critical("Performing emergency cleanup...")
        await self.modules['memory'].flush_cache()
        await self.modules['optimizer'].rollback()
        
    def shutdown(self):
        self.logger.info("Shutdown requested...")
        self.state = SystemState.SHUTTING_DOWN
        self._shutdown_event.set()
        
    async def cleanup(self):
        for module in reversed(list(self.modules.values())):
            await module.cleanup()
        self.logger.info("Cleanup completed")


class ResourceExhaustedError(Exception):
    pass


class PredictionDivergenceError(Exception):
    pass
```

### 53.2.2 环境感知模块

```python
import os
import re
import json
import glob
from collections import deque
from typing import Iterator, Optional
import hashlib


class Sensor(ABC):
    @abstractmethod
    async def read(self) -> Dict[str, Any]:
        pass
    
    @property
    @abstractmethod
    def sensor_type(self) -> str:
        pass


class CPUSensor(Sensor):
    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self._history = deque(maxlen=100)
        
    @property
    def sensor_type(self) -> str:
        return "cpu"
        
    async def read(self) -> Dict[str, Any]:
        cpu_percent = psutil.cpu_percent(interval=self.interval)
        cpu_freq = psutil.cpu_freq()
        cpu_count = psutil.cpu_count()
        load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else (0, 0, 0)
        
        data = {
            'percent': cpu_percent,
            'frequency': cpu_freq.current if cpu_freq else 0,
            'count': cpu_count,
            'load_avg_1m': load_avg[0],
            'load_avg_5m': load_avg[1],
            'load_avg_15m': load_avg[2],
            'per_cpu': psutil.cpu_percent(percpu=True)
        }
        self._history.append(data)
        return data


class MemorySensor(Sensor):
    def __init__(self):
        self._history = deque(maxlen=100)
        
    @property
    def sensor_type(self) -> str:
        return "memory"
        
    async def read(self) -> Dict[str, Any]:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        data = {
            'total': mem.total,
            'available': mem.available,
            'percent': mem.percent,
            'used': mem.used,
            'free': mem.free,
            'swap_total': swap.total,
            'swap_used': swap.used,
            'swap_percent': swap.percent
        }
        self._history.append(data)
        return data


class DiskSensor(Sensor):
    def __init__(self, paths: Optional[List[str]] = None):
        self.paths = paths or ['/']
        self._history = deque(maxlen=100)
        
    @property
    def sensor_type(self) -> str:
        return "disk"
        
    async def read(self) -> Dict[str, Any]:
        data = {'partitions': []}
        for path in self.paths:
            try:
                usage = psutil.disk_usage(path)
                io = psutil.disk_io_counters()
                data['partitions'].append({
                    'path': path,
                    'total': usage.total,
                    'used': usage.used,
                    'free': usage.free,
                    'percent': usage.percent,
                    'read_bytes': io.read_bytes if io else 0,
                    'write_bytes': io.write_bytes if io else 0
                })
            except Exception as e:
                data['partitions'].append({'path': path, 'error': str(e)})
        self._history.append(data)
        return data


class LogSensor(Sensor):
    def __init__(self, log_paths: List[str], max_lines: int = 100):
        self.log_paths = log_paths
        self.max_lines = max_lines
        self._file_positions: Dict[str, int] = {}
        self._error_patterns = [
            re.compile(r'ERROR|FATAL|CRITICAL', re.IGNORECASE),
            re.compile(r'exception|traceback', re.IGNORECASE),
            re.compile(r'failed|failure|error', re.IGNORECASE)
        ]
        
    @property
    def sensor_type(self) -> str:
        return "log"
        
    async def read(self) -> Dict[str, Any]:
        data = {'files': [], 'error_count': 0, 'warning_count': 0}
        
        for log_path in self.log_paths:
            try:
                new_lines = self._read_new_lines(log_path)
                errors = sum(1 for line in new_lines 
                           if any(p.search(line) for p in self._error_patterns))
                warnings = sum(1 for line in new_lines 
                             if 'WARNING' in line.upper())
                
                data['files'].append({
                    'path': log_path,
                    'new_lines': len(new_lines),
                    'errors': errors,
                    'warnings': warnings,
                    'sample': new_lines[-5:] if new_lines else []
                })
                data['error_count'] += errors
                data['warning_count'] += warnings
            except Exception as e:
                data['files'].append({'path': log_path, 'error': str(e)})
                
        return data
        
    def _read_new_lines(self, path: str) -> List[str]:
        if not os.path.exists(path):
            return []
            
        last_pos = self._file_positions.get(path, 0)
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            f.seek(last_pos)
            lines = f.readlines()
            self._file_positions[path] = f.tell()
            
        return [line.strip() for line in lines[-self.max_lines:]]


class FileSystemSensor(Sensor):
    def __init__(self, watch_paths: List[str]):
        self.watch_paths = watch_paths
        self._file_hashes: Dict[str, str] = {}
        
    @property
    def sensor_type(self) -> str:
        return "filesystem"
        
    async def read(self) -> Dict[str, Any]:
        data = {'changes': [], 'file_count': 0, 'total_size': 0}
        
        for watch_path in self.watch_paths:
            if not os.path.exists(watch_path):
                continue
                
            for root, dirs, files in os.walk(watch_path):
                for filename in files:
                    filepath = os.path.join(root, filename)
                    try:
                        stat = os.stat(filepath)
                        current_hash = self._compute_file_hash(filepath)
                        
                        if filepath in self._file_hashes:
                            if self._file_hashes[filepath] != current_hash:
                                data['changes'].append({
                                    'path': filepath,
                                    'type': 'modified',
                                    'size': stat.st_size,
                                    'mtime': stat.st_mtime
                                })
                        else:
                            data['changes'].append({
                                'path': filepath,
                                'type': 'new',
                                'size': stat.st_size,
                                'mtime': stat.st_mtime
                            })
                            
                        self._file_hashes[filepath] = current_hash
                        data['file_count'] += 1
                        data['total_size'] += stat.st_size
                    except Exception:
                        pass
                        
        return data
        
    def _compute_file_hash(self, filepath: str) -> str:
        try:
            stat = os.stat(filepath)
            return hashlib.md5(
                f"{stat.st_size}:{stat.st_mtime}".encode()
            ).hexdigest()
        except Exception:
            return ""


class EnvironmentPerceptionModule:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.sensors: List[Sensor] = []
        self._state_buffer = deque(maxlen=1000)
        
    async def initialize(self):
        self.sensors = [
            CPUSensor(interval=self.config.get('cpu_interval', 1.0)),
            MemorySensor(),
            DiskSensor(paths=self.config.get('disk_paths', ['/'])),
            LogSensor(
                log_paths=self.config.get('log_paths', ['/var/log/syslog']),
                max_lines=self.config.get('max_log_lines', 100)
            ),
            FileSystemSensor(
                watch_paths=self.config.get('watch_paths', ['/tmp'])
            )
        ]
        
    async def perceive(self) -> Dict[str, Any]:
        state = {'timestamp': datetime.now().isoformat(), 'sensors': {}}
        
        for sensor in self.sensors:
            try:
                state['sensors'][sensor.sensor_type] = await sensor.read()
            except Exception as e:
                state['sensors'][sensor.sensor_type] = {'error': str(e)}
                
        self._state_buffer.append(state)
        return state
        
    def get_state_history(self, n: int = 100) -> List[Dict[str, Any]]:
        return list(self._state_buffer)[-n:]
        
    async def cleanup(self):
        self.sensors.clear()
```

### 53.2.3 驱力引擎模块

```python
from dataclasses import dataclass
from typing import Callable


@dataclass
class DriveSignals:
    safety_reward: float
    gain_reward: float
    efficiency_reward: float
    safety_gap: float
    gain_gap: float
    efficiency_gap: float
    weights: Dict[str, float]
    total_reward: float


class DriveEngineModule:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_weights = config.get('base_weights', {
            'safety': 0.4,
            'gain': 0.4,
            'efficiency': 0.2
        })
        self._history = deque(maxlen=1000)
        self._error_history = deque(maxlen=100)
        
    async def initialize(self):
        pass
        
    async def compute(self, env_state: Dict[str, Any]) -> DriveSignals:
        safety_reward = self._compute_safety_reward(env_state)
        gain_reward = self._compute_gain_reward(env_state)
        efficiency_reward = self._compute_efficiency_reward(env_state)
        
        safety_gap = max(0, 1.0 - safety_reward)
        gain_gap = max(0, 1.0 - gain_reward)
        efficiency_gap = max(0, 1.0 - efficiency_reward)
        
        weights = self._compute_dynamic_weights(
            safety_gap, gain_gap, efficiency_gap, env_state
        )
        
        total_reward = (
            weights['safety'] * safety_reward +
            weights['gain'] * gain_reward +
            weights['efficiency'] * efficiency_reward
        )
        
        signals = DriveSignals(
            safety_reward=safety_reward,
            gain_reward=gain_reward,
            efficiency_reward=efficiency_reward,
            safety_gap=safety_gap,
            gain_gap=gain_gap,
            efficiency_gap=efficiency_gap,
            weights=weights,
            total_reward=total_reward
        )
        
        self._history.append(signals)
        return signals
        
    def _compute_safety_reward(self, env_state: Dict[str, Any]) -> float:
        sensors = env_state.get('sensors', {})
        
        # CPU异常检测
        cpu_data = sensors.get('cpu', {})
        cpu_percent = cpu_data.get('percent', 0)
        cpu_load = cpu_data.get('load_avg_1m', 0)
        
        # 内存异常检测
        mem_data = sensors.get('memory', {})
        mem_percent = mem_data.get('percent', 0)
        swap_percent = mem_data.get('swap_percent', 0)
        
        # 日志异常检测
        log_data = sensors.get('log', {})
        error_count = log_data.get('error_count', 0)
        warning_count = log_data.get('warning_count', 0)
        
        # 计算安全分数（越高越安全）
        cpu_score = max(0, 1.0 - cpu_percent / 100)
        mem_score = max(0, 1.0 - mem_percent / 100)
        swap_score = max(0, 1.0 - swap_percent / 100)
        log_score = max(0, 1.0 - (error_count + warning_count * 0.5) / 10)
        
        return (cpu_score + mem_score + swap_score + log_score) / 4
        
    def _compute_gain_reward(self, env_state: Dict[str, Any]) -> float:
        # 基于预测误差和信息增益计算
        if len(self._error_history) < 2:
            return 0.5
            
        recent_errors = list(self._error_history)[-10:]
        error_trend = np.polyfit(range(len(recent_errors)), recent_errors, 1)[0]
        
        # 误差下降表示收益
        if error_trend < 0:
            return min(1.0, 0.5 + abs(error_trend) * 10)
        else:
            return max(0.0, 0.5 - error_trend * 10)
            
    def _compute_efficiency_reward(self, env_state: Dict[str, Any]) -> float:
        sensors = env_state.get('sensors', {})
        
        cpu_data = sensors.get('cpu', {})
        cpu_percent = cpu_data.get('percent', 0)
        
        mem_data = sensors.get('memory', {})
        mem_percent = mem_data.get('percent', 0)
        
        # 资源使用效率（适度使用为最优）
        cpu_eff = 1.0 - abs(cpu_percent - 50) / 50
        mem_eff = 1.0 - abs(mem_percent - 50) / 50
        
        return (cpu_eff + mem_eff) / 2
        
    def _compute_dynamic_weights(
        self,
        safety_gap: float,
        gain_gap: float,
        efficiency_gap: float,
        env_state: Dict[str, Any]
    ) -> Dict[str, float]:
        weights = self.base_weights.copy()
        
        # 紧急风险场景：安全权重独占最高
        if safety_gap > 0.7:
            weights = {'safety': 0.7, 'gain': 0.2, 'efficiency': 0.1}
        # 资源紧张场景：能效权重独占最高
        elif efficiency_gap > 0.7:
            weights = {'safety': 0.2, 'gain': 0.1, 'efficiency': 0.7}
        # 稳态空闲场景：收益探索权重独占最高
        elif safety_gap < 0.3 and efficiency_gap < 0.3:
            weights = {'safety': 0.2, 'gain': 0.6, 'efficiency': 0.2}
            
        # 归一化
        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}
        
    def update_error_history(self, errors: Dict[str, float]):
        avg_error = np.mean(list(errors.values()))
        self._error_history.append(avg_error)
        
    async def cleanup(self):
        pass
```

### 53.2.4 多层预测模型

```python
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset


class BasePredictor(ABC):
    @abstractmethod
    def predict(self, state: np.ndarray) -> np.ndarray:
        pass
    
    @abstractmethod
    def update(self, state: np.ndarray, target: np.ndarray):
        pass


class AdaptiveExponentialSmoother(BasePredictor):
    def __init__(self, alpha: float = 0.3):
        self.alpha = alpha
        self.level: Optional[np.ndarray] = None
        self.trend: Optional[np.ndarray] = None
        self._history = deque(maxlen=100)
        
    def predict(self, state: np.ndarray) -> np.ndarray:
        if self.level is None:
            self.level = state.copy()
            self.trend = np.zeros_like(state)
            return state
            
        forecast = self.level + self.trend
        return forecast
        
    def update(self, state: np.ndarray, target: np.ndarray):
        if self.level is None:
            self.level = state.copy()
            self.trend = np.zeros_like(state)
            return
            
        error = target - (self.level + self.trend)
        
        # 自适应调整alpha
        self.alpha = self._adapt_alpha(error)
        
        new_level = self.alpha * target + (1 - self.alpha) * (self.level + self.trend)
        new_trend = self.alpha * (new_level - self.level) + (1 - self.alpha) * self.trend
        
        self.level = new_level
        self.trend = new_trend
        self._history.append({'error': error, 'alpha': self.alpha})
        
    def _adapt_alpha(self, error: np.ndarray) -> float:
        if len(self._history) < 10:
            return self.alpha
            
        recent_errors = [h['error'] for h in list(self._history)[-10:]]
        error_variance = np.var(recent_errors)
        
        # 高方差时降低alpha（更平滑），低方差时提高alpha（更敏感）
        target_alpha = 1.0 / (1.0 + error_variance)
        return 0.7 * self.alpha + 0.3 * target_alpha


class LSTMPredictor(BasePredictor):
    def __init__(self, input_size: int, hidden_size: int = 64, 
                 num_layers: int = 2, sequence_length: int = 10):
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.sequence_length = sequence_length
        
        self.model = self._build_model()
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
        self.criterion = nn.MSELoss()
        
        self._sequence_buffer = deque(maxlen=sequence_length)
        self._training_buffer = deque(maxlen=1000)
        
    def _build_model(self) -> nn.Module:
        class LSTMModel(nn.Module):
            def __init__(self, input_size, hidden_size, num_layers):
                super().__init__()
                self.lstm = nn.LSTM(
                    input_size, hidden_size, num_layers,
                    batch_first=True, dropout=0.2
                )
                self.fc = nn.Linear(hidden_size, input_size)
                
            def forward(self, x):
                lstm_out, _ = self.lstm(x)
                return self.fc(lstm_out[:, -1, :])
                
        return LSTMModel(self.input_size, self.hidden_size, self.num_layers)
        
    def predict(self, state: np.ndarray) -> np.ndarray:
        self._sequence_buffer.append(state)
        
        if len(self._sequence_buffer) < self.sequence_length:
            return state
            
        sequence = np.array(list(self._sequence_buffer))
        x = torch.FloatTensor(sequence).unsqueeze(0)
        
        with torch.no_grad():
            prediction = self.model(x).numpy().flatten()
            
        return prediction
        
    def update(self, state: np.ndarray, target: np.ndarray):
        self._sequence_buffer.append(state)
        
        if len(self._sequence_buffer) >= self.sequence_length:
            sequence = np.array(list(self._sequence_buffer))
            self._training_buffer.append((sequence, target))
            
        # 增量训练
        if len(self._training_buffer) >= 32:
            self._train_step()
            
    def _train_step(self):
        batch = list(self._training_buffer)[-32:]
        sequences = torch.FloatTensor([s for s, _ in batch])
        targets = torch.FloatTensor([t for _, t in batch])
        
        self.optimizer.zero_grad()
        predictions = self.model(sequences)
        loss = self.criterion(predictions, targets)
        loss.backward()
        
        # 梯度裁剪
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        self.optimizer.step()


class EnsemblePredictor(BasePredictor):
    def __init__(self, predictors: List[BasePredictor], 
                 weights: Optional[np.ndarray] = None):
        self.predictors = predictors
        self.weights = weights or np.ones(len(predictors)) / len(predictors)
        self._error_history = {i: deque(maxlen=100) for i in range(len(predictors))}
        
    def predict(self, state: np.ndarray) -> np.ndarray:
        predictions = [p.predict(state) for p in self.predictors]
        
        # 根据历史误差动态调整权重
        self._update_weights()
        
        weighted_pred = np.zeros_like(state)
        for i, pred in enumerate(predictions):
            weighted_pred += self.weights[i] * pred
            
        return weighted_pred
        
    def update(self, state: np.ndarray, target: np.ndarray):
        for i, predictor in enumerate(self.predictors):
            pred = predictor.predict(state)
            error = np.mean((target - pred) ** 2)
            self._error_history[i].append(error)
            predictor.update(state, target)
            
    def _update_weights(self):
        if all(len(h) > 0 for h in self._error_history.values()):
            avg_errors = [np.mean(list(h)) for h in self._error_history.values()]
            inv_errors = 1.0 / (np.array(avg_errors) + 1e-6)
            self.weights = inv_errors / inv_errors.sum()


class PredictionModule:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.predictors: Dict[str, BasePredictor] = {}
        self._prediction_history = deque(maxlen=1000)
        
    async def initialize(self):
        input_size = self.config.get('state_vector_size', 10)
        
        self.predictors = {
            'low_level': AdaptiveExponentialSmoother(alpha=0.3),
            'mid_level': LSTMPredictor(
                input_size=input_size,
                hidden_size=64,
                num_layers=2,
                sequence_length=10
            ),
            'high_level': EnsemblePredictor([
                AdaptiveExponentialSmoother(alpha=0.1),
                LSTMPredictor(input_size, hidden_size=128, num_layers=3)
            ])
        }
        
    async def predict(self, env_state: Dict[str, Any]) -> Dict[str, np.ndarray]:
        state_vector = self._state_to_vector(env_state)
        
        predictions = {}
        for name, predictor in self.predictors.items():
            try:
                predictions[name] = predictor.predict(state_vector)
            except Exception as e:
                predictions[name] = state_vector
                
        self._prediction_history.append({
            'timestamp': datetime.now(),
            'state': state_vector,
            'predictions': predictions
        })
        
        return predictions
        
    def _state_to_vector(self, env_state: Dict[str, Any]) -> np.ndarray:
        sensors = env_state.get('sensors', {})
        features = []
        
        cpu = sensors.get('cpu', {})
        features.extend([
            cpu.get('percent', 0) / 100,
            cpu.get('load_avg_1m', 0) / 10,
            cpu.get('load_avg_5m', 0) / 10
        ])
        
        mem = sensors.get('memory', {})
        features.extend([
            mem.get('percent', 0) / 100,
            mem.get('swap_percent', 0) / 100
        ])
        
        disk = sensors.get('disk', {})
        partitions = disk.get('partitions', [])
        if partitions:
            features.append(partitions[0].get('percent', 0) / 100)
        else:
            features.append(0)
            
        log = sensors.get('log', {})
        features.extend([
            min(log.get('error_count', 0) / 10, 1.0),
            min(log.get('warning_count', 0) / 10, 1.0)
        ])
        
        return np.array(features)
        
    async def cleanup(self):
        pass
```

### 53.2.5 任务生成与决策模块

```python
from dataclasses import dataclass, field
from typing import List, Dict, Callable
import random


@dataclass
class Task:
    id: str
    name: str
    task_type: str
    priority: float
    expected_reward: float
    expected_cost: float
    novelty_score: float
    execution_time_estimate: float
    params: Dict[str, Any] = field(default_factory=dict)
    
    def compute_score(self, weights: Dict[str, float]) -> float:
        return (
            weights.get('reward', 0.4) * self.expected_reward +
            weights.get('novelty', 0.2) * self.novelty_score -
            weights.get('cost', 0.4) * self.expected_cost
        )
        
    async def execute(self) -> Dict[str, Any]:
        # 具体执行逻辑由子类实现
        return {'status': 'completed', 'task_id': self.id}


class TaskGenerator:
    def __init__(self):
        self._task_templates: Dict[str, Callable] = {}
        self._task_counter = 0
        
    def register_template(self, task_type: str, generator: Callable):
        self._task_templates[task_type] = generator
        
    def generate_tasks(
        self,
        env_state: Dict[str, Any],
        drive_signals: DriveSignals,
        errors: Dict[str, float]
    ) -> List[Task]:
        tasks = []
        
        # 基于安全缺口生成任务
        if drive_signals.safety_gap > 0.3:
            tasks.extend(self._generate_safety_tasks(env_state, drive_signals))
            
        # 基于收益缺口生成任务
        if drive_signals.gain_gap > 0.3:
            tasks.extend(self._generate_gain_tasks(env_state, drive_signals, errors))
            
        # 基于能效缺口生成任务
        if drive_signals.efficiency_gap > 0.3:
            tasks.extend(self._generate_efficiency_tasks(env_state, drive_signals))
            
        # 探索任务（固定比例）
        if random.random() < 0.3:
            tasks.extend(self._generate_exploration_tasks(env_state))
            
        return tasks
        
    def _generate_safety_tasks(
        self,
        env_state: Dict[str, Any],
        drive_signals: DriveSignals
    ) -> List[Task]:
        tasks = []
        
        # 异常监控任务
        tasks.append(Task(
            id=self._next_id(),
            name="anomaly_monitoring",
            task_type="safety",
            priority=drive_signals.safety_gap,
            expected_reward=drive_signals.safety_gap * 0.8,
            expected_cost=0.1,
            novelty_score=0.1,
            execution_time_estimate=1.0
        ))
        
        # 日志分析任务
        tasks.append(Task(
            id=self._next_id(),
            name="log_analysis",
            task_type="safety",
            priority=drive_signals.safety_gap * 0.7,
            expected_reward=drive_signals.safety_gap * 0.6,
            expected_cost=0.2,
            novelty_score=0.2,
            execution_time_estimate=2.0
        ))
        
        return tasks
        
    def _generate_gain_tasks(
        self,
        env_state: Dict[str, Any],
        drive_signals: DriveSignals,
        errors: Dict[str, float]
    ) -> List[Task]:
        tasks = []
        
        # 模型训练任务
        tasks.append(Task(
            id=self._next_id(),
            name="model_training",
            task_type="gain",
            priority=drive_signals.gain_gap,
            expected_reward=drive_signals.gain_gap * 0.9,
            expected_cost=0.4,
            novelty_score=0.3,
            execution_time_estimate=5.0
        ))
        
        # 特征探索任务
        tasks.append(Task(
            id=self._next_id(),
            name="feature_exploration",
            task_type="gain",
            priority=drive_signals.gain_gap * 0.6,
            expected_reward=drive_signals.gain_gap * 0.7,
            expected_cost=0.3,
            novelty_score=0.8,
            execution_time_estimate=3.0
        ))
        
        return tasks
        
    def _generate_efficiency_tasks(
        self,
        env_state: Dict[str, Any],
        drive_signals: DriveSignals
    ) -> List[Task]:
        tasks = []
        
        # 模型压缩任务
        tasks.append(Task(
            id=self._next_id(),
            name="model_compression",
            task_type="efficiency",
            priority=drive_signals.efficiency_gap,
            expected_reward=drive_signals.efficiency_gap * 0.8,
            expected_cost=0.2,
            novelty_score=0.2,
            execution_time_estimate=4.0
        ))
        
        # 缓存优化任务
        tasks.append(Task(
            id=self._next_id(),
            name="cache_optimization",
            task_type="efficiency",
            priority=drive_signals.efficiency_gap * 0.5,
            expected_reward=drive_signals.efficiency_gap * 0.6,
            expected_cost=0.1,
            novelty_score=0.1,
            execution_time_estimate=1.0
        ))
        
        return tasks
        
    def _generate_exploration_tasks(
        self,
        env_state: Dict[str, Any]
    ) -> List[Task]:
        tasks = []
        
        # 随机探索任务
        exploration_types = [
            ("new_sensor_test", 0.7),
            ("parameter_sweep", 0.6),
            ("correlation_analysis", 0.5),
            ("anomaly_simulation", 0.4)
        ]
        
        for name, base_reward in exploration_types:
            tasks.append(Task(
                id=self._next_id(),
                name=name,
                task_type="exploration",
                priority=0.5,
                expected_reward=base_reward,
                expected_cost=0.3,
                novelty_score=0.9,
                execution_time_estimate=2.0
            ))
            
        return tasks
        
    def _next_id(self) -> str:
        self._task_counter += 1
        return f"task_{self._task_counter}_{int(datetime.now().timestamp())}"


class DecisionModule:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.exploration_rate = config.get('exploration_rate', 0.3)
        self._decision_history = deque(maxlen=1000)
        
    async def initialize(self):
        pass
        
    async def select(self, tasks: List[Task]) -> Optional[Task]:
        if not tasks:
            return None
            
        # 计算每个任务的得分
        weights = {
            'reward': 0.4,
            'novelty': 0.2,
            'cost': 0.4
        }
        
        scored_tasks = [(task, task.compute_score(weights)) for task in tasks]
        scored_tasks.sort(key=lambda x: x[1], reverse=True)
        
        # 70%利用：选择得分最高的任务
        # 30%探索：随机选择得分较低的任务
        if random.random() > self.exploration_rate:
            selected = scored_tasks[0][0]
        else:
            # 从后50%的任务中随机选择
            exploration_pool = scored_tasks[len(scored_tasks)//2:]
            if exploration_pool:
                selected = random.choice(exploration_pool)[0]
            else:
                selected = scored_tasks[0][0]
                
        self._decision_history.append({
            'timestamp': datetime.now(),
            'selected_task': selected.id,
            'available_tasks': [t.id for t in tasks],
            'was_exploration': random.random() <= self.exploration_rate
        })
        
        return selected
        
    async def cleanup(self):
        pass
```

## 53.3 辅助工具实现

### 53.3.1 配置管理器

```python
import yaml
import json
from pathlib import Path
from typing import Any, Dict, Optional
import os


class ConfigurationManager:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self._config: Dict[str, Any] = {}
        self._watchers: List[Callable] = []
        self._last_modified: float = 0
        
    def load(self, path: Optional[str] = None) -> Dict[str, Any]:
        path = path or self.config_path
        if not path:
            return {}
            
        path_obj = Path(path)
        if not path_obj.exists():
            return {}
            
        with open(path, 'r') as f:
            if path.endswith('.yaml') or path.endswith('.yml'):
                self._config = yaml.safe_load(f)
            elif path.endswith('.json'):
                self._config = json.load(f)
            else:
                raise ValueError(f"Unsupported config format: {path}")
                
        self._last_modified = path_obj.stat().st_mtime
        return self._config
        
    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        value = self._config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
                
        return value
        
    def set(self, key: str, value: Any):
        keys = key.split('.')
        config = self._config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
            
        config[keys[-1]] = value
        
    def reload_if_changed(self):
        if not self.config_path:
            return
            
        path_obj = Path(self.config_path)
        if not path_obj.exists():
            return
            
        current_mtime = path_obj.stat().st_mtime
        if current_mtime > self._last_modified:
            self.load()
            for watcher in self._watchers:
                watcher(self._config)
                
    def add_watcher(self, watcher: Callable):
        self._watchers.append(watcher)
        
    def merge_env_vars(self):
        prefix = "AGENT_"
        for key, value in os.environ.items():
            if key.startswith(prefix):
                config_key = key[len(prefix):].lower().replace('_', '.')
                self.set(config_key, self._parse_value(value))
                
    def _parse_value(self, value: str) -> Any:
        if value.lower() in ('true', 'yes', '1'):
            return True
        if value.lower() in ('false', 'no', '0'):
            return False
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value
```

### 53.3.2 日志管理器

```python
import logging
import logging.handlers
from datetime import datetime
from pathlib import Path


class LogManager:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger('agent')
        self._setup_logging()
        
    def _setup_logging(self):
        log_level = self.config.get('log_level', 'INFO')
        log_dir = Path(self.config.get('log_dir', './logs'))
        log_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # 清除现有处理器
        self.logger.handlers.clear()
        
        # 文件处理器（轮转）
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / 'agent.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=10
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # 错误文件处理器
        error_handler = logging.handlers.RotatingFileHandler(
            log_dir / 'agent.error.log',
            maxBytes=10*1024*1024,
            backupCount=10
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        self.logger.addHandler(error_handler)
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
        
    def get_logger(self, name: str) -> logging.Logger:
        return self.logger.getChild(name)
```

## 53.4 结论

本章提供了自驱永续进化Agent系统核心模块的完整代码实现。代码遵循模块化、可扩展的设计原则，包含完整的类型注解和错误处理。这些实现可作为系统开发的基础，根据具体需求进行定制和扩展。

