# 第三十三章：数据结构与存储设计

## 33.1 内存数据结构

### 33.1.1 循环缓冲区（Ring Buffer）

循环缓冲区用于高效存储时间序列数据，避免频繁的内存分配。

```python
import numpy as np
from typing import Optional, Generic, TypeVar

T = TypeVar('T')

class RingBuffer(Generic[T]):
    """
    泛型循环缓冲区
    
    特性：
    - O(1) 写入
    - O(1) 读取最新N个元素
    - 自动覆盖旧数据
    - 线程安全（可选）
    """
    
    def __init__(self, capacity: int, dtype: type = float):
        self.capacity = capacity
        self.buffer = np.zeros(capacity, dtype=dtype)
        self.write_index = 0
        self.size = 0
        self._lock = asyncio.Lock() if threading else None
        
    async def append(self, value: T) -> None:
        """追加元素"""
        async with self._lock:
            self.buffer[self.write_index] = value
            self.write_index = (self.write_index + 1) % self.capacity
            self.size = min(self.size + 1, self.capacity)
            
    def get_recent(self, n: int) -> np.ndarray:
        """获取最近n个元素"""
        if n >= self.size:
            return self._get_all_ordered()
            
        result = np.zeros(n, dtype=self.buffer.dtype)
        for i in range(n):
            idx = (self.write_index - 1 - i) % self.capacity
            result[n - 1 - i] = self.buffer[idx]
        return result
        
    def _get_all_ordered(self) -> np.ndarray:
        """获取所有元素（按时间顺序）"""
        if self.size < self.capacity:
            return self.buffer[:self.size]
        
        # 重新排序
        result = np.zeros(self.capacity, dtype=self.buffer.dtype)
        for i in range(self.capacity):
            idx = (self.write_index + i) % self.capacity
            result[i] = self.buffer[idx]
        return result
        
    def get_statistics(self) -> Dict[str, float]:
        """获取统计信息"""
        data = self._get_all_ordered()
        return {
            'mean': float(np.mean(data)),
            'std': float(np.std(data)),
            'min': float(np.min(data)),
            'max': float(np.max(data)),
            'count': self.size
        }
```

### 33.1.2 优先队列（任务调度）

```python
import heapq
from dataclasses import dataclass, field

@dataclass(order=True)
class PrioritizedItem:
    """支持动态优先级的优先队列项"""
    priority: float
    sequence: int = field(compare=True)
    item: Any = field(compare=False)
    
class DynamicPriorityQueue:
    """
    动态优先级队列
    
    支持：
    - 优先级动态调整
    - 按时间衰减的优先级
    - 批量操作
    """
    
    def __init__(self, decay_rate: float = 0.99):
        self._queue = []
        self._counter = 0
        self._entry_map = {}
        self.decay_rate = decay_rate
        self._removed_set = set()
        
    def put(self, item: Any, priority: float) -> str:
        """放入队列"""
        entry_id = str(uuid.uuid4())
        self._counter += 1
        
        entry = [priority, self._counter, entry_id, item]
        self._entry_map[entry_id] = entry
        heapq.heappush(self._queue, entry)
        
        return entry_id
        
    def get(self) -> Optional[Any]:
        """取出最高优先级项"""
        while self._queue:
            priority, count, entry_id, item = heapq.heappop(self._queue)
            
            if entry_id not in self._removed_set:
                del self._entry_map[entry_id]
                return item
                
        return None
        
    def update_priority(self, entry_id: str, new_priority: float) -> bool:
        """更新优先级"""
        if entry_id not in self._entry_map:
            return False
            
        # 标记旧条目为已删除
        self._removed_set.add(entry_id)
        
        # 创建新条目
        old_entry = self._entry_map[entry_id]
        self.put(old_entry[3], new_priority)
        
        return True
        
    def decay_priorities(self) -> None:
        """衰减所有优先级（用于时间敏感场景）"""
        new_queue = []
        for entry in self._queue:
            if entry[2] not in self._removed_set:
                entry[0] *= self.decay_rate
                new_queue.append(entry)
                
        self._queue = new_queue
        heapq.heapify(self._queue)
```

### 33.1.3 稀疏矩阵存储

```python
from collections import defaultdict

class SparseMatrix:
    """
    稀疏矩阵实现
    
    用于存储大规模但稀疏的关联数据（如因果图）
    """
    
    def __init__(self, shape: Tuple[int, int]):
        self.shape = shape
        self._data = defaultdict(float)
        
    def __setitem__(self, key: Tuple[int, int], value: float):
        """设置元素"""
        i, j = key
        if 0 <= i < self.shape[0] and 0 <= j < self.shape[1]:
            if abs(value) > 1e-10:
                self._data[(i, j)] = value
            elif (i, j) in self._data:
                del self._data[(i, j)]
                
    def __getitem__(self, key: Tuple[int, int]) -> float:
        """获取元素"""
        return self._data.get(key, 0.0)
        
    def get_row(self, i: int) -> Dict[int, float]:
        """获取整行非零元素"""
        return {j: v for (ii, j), v in self._data.items() if ii == i}
        
    def get_col(self, j: int) -> Dict[int, float]:
        """获取整列非零元素"""
        return {i: v for (i, jj), v in self._data.items() if jj == j}
        
    def multiply_vector(self, vector: np.ndarray) -> np.ndarray:
        """矩阵向量乘法（优化实现）"""
        result = np.zeros(self.shape[0])
        for (i, j), value in self._data.items():
            result[i] += value * vector[j]
        return result
        
    def density(self) -> float:
        """计算矩阵密度"""
        return len(self._data) / (self.shape[0] * self.shape[1])
```

## 33.2 数据库存储设计

### 33.2.1 SQLite 数据库Schema

```sql
-- 主数据库：memory.db

-- 感知历史表
CREATE TABLE perception_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    sensor_type TEXT NOT NULL,
    sensor_id TEXT NOT NULL,
    raw_value BLOB,
    processed_value BLOB,
    confidence REAL DEFAULT 1.0,
    metadata TEXT  -- JSON格式
);

CREATE INDEX idx_perception_time ON perception_history(timestamp);
CREATE INDEX idx_perception_sensor ON perception_history(sensor_type, sensor_id);

-- 驱力历史表
CREATE TABLE drive_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    safe_drive REAL NOT NULL,
    gain_drive REAL NOT NULL,
    eff_drive REAL NOT NULL,
    safe_weight REAL NOT NULL,
    gain_weight REAL NOT NULL,
    eff_weight REAL NOT NULL,
    safe_gap REAL NOT NULL,
    gain_gap REAL NOT NULL,
    eff_gap REAL NOT NULL,
    emergency INTEGER DEFAULT 0
);

CREATE INDEX idx_drive_time ON drive_history(timestamp);

-- 任务历史表
CREATE TABLE task_history (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    task_type TEXT NOT NULL,
    priority INTEGER NOT NULL,
    status TEXT NOT NULL,
    expected_reward REAL,
    actual_reward REAL,
    expected_cost REAL,
    actual_cost REAL,
    created_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL,
    execution_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    metadata TEXT
);

CREATE INDEX idx_task_status ON task_history(status);
CREATE INDEX idx_task_type ON task_history(task_type);

-- 预测历史表
CREATE TABLE prediction_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    model_level TEXT NOT NULL,  -- low/mid/high/ensemble
    model_version TEXT NOT NULL,
    input_data BLOB,
    predicted_value BLOB,
    actual_value BLOB,
    error REAL,
    confidence REAL,
    horizon INTEGER
);

CREATE INDEX idx_prediction_time ON prediction_history(timestamp);
CREATE INDEX idx_prediction_model ON prediction_history(model_level, model_version);

-- 模型快照表
CREATE TABLE model_snapshots (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at REAL NOT NULL,
    model_type TEXT NOT NULL,
    model_level TEXT NOT NULL,
    model_path TEXT NOT NULL,
    performance_metrics TEXT,  -- JSON
    parent_snapshot TEXT,
    FOREIGN KEY (parent_snapshot) REFERENCES model_snapshots(id)
);

-- 决策历史表
CREATE TABLE decision_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    selected_task_id TEXT,
    exploration_mode INTEGER DEFAULT 0,
    drive_state TEXT,  -- JSON
    candidate_count INTEGER,
    reasoning TEXT,
    FOREIGN KEY (selected_task_id) REFERENCES task_history(id)
);

-- 安全违规表
CREATE TABLE safety_violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    violation_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    description TEXT,
    action_taken TEXT,
    task_id TEXT,
    FOREIGN KEY (task_id) REFERENCES task_history(id)
);

-- 系统状态表（用于快速恢复）
CREATE TABLE system_state (
    key TEXT PRIMARY KEY,
    value BLOB,
    updated_at REAL NOT NULL
);
```

### 33.2.2 数据库访问层

```python
import sqlite3
import json
import pickle
from contextlib import contextmanager

class MemoryDatabase:
    """
    记忆数据库访问层
    
    提供高性能、事务安全的数据库操作
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        
    def _get_connection(self) -> sqlite3.Connection:
        """获取线程本地连接"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                isolation_level=None  # 自动提交模式
            )
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            self._local.connection.execute("PRAGMA synchronous=NORMAL")
        return self._local.connection
        
    @contextmanager
    def transaction(self):
        """事务上下文管理器"""
        conn = self._get_connection()
        conn.execute("BEGIN")
        try:
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
            
    async def store_perception(self, data: PerceptionData) -> int:
        """存储感知数据"""
        with self.transaction() as conn:
            cursor = conn.execute(
                """INSERT INTO perception_history 
                   (timestamp, sensor_type, sensor_id, raw_value, processed_value, confidence, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    data.timestamp,
                    data.sensor_type,
                    data.sensor_id,
                    pickle.dumps(data.raw_value),
                    pickle.dumps(data.processed_value),
                    data.confidence,
                    json.dumps(data.metadata)
                )
            )
            return cursor.lastrowid
            
    async def get_perception_range(
        self,
        start_time: float,
        end_time: float,
        sensor_type: Optional[str] = None,
        limit: int = 1000
    ) -> List[PerceptionData]:
        """获取时间范围内的感知数据"""
        conn = self._get_connection()
        
        if sensor_type:
            cursor = conn.execute(
                """SELECT * FROM perception_history 
                   WHERE timestamp >= ? AND timestamp <= ? AND sensor_type = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (start_time, end_time, sensor_type, limit)
            )
        else:
            cursor = conn.execute(
                """SELECT * FROM perception_history 
                   WHERE timestamp >= ? AND timestamp <= ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (start_time, end_time, limit)
            )
            
        results = []
        for row in cursor.fetchall():
            results.append(PerceptionData(
                timestamp=row['timestamp'],
                sensor_type=row['sensor_type'],
                sensor_id=row['sensor_id'],
                raw_value=pickle.loads(row['raw_value']),
                processed_value=pickle.loads(row['processed_value']),
                confidence=row['confidence'],
                metadata=json.loads(row['metadata'])
            ))
        return results
        
    async def cleanup_old_data(self, retention_days: int = 30) -> int:
        """清理过期数据"""
        cutoff_time = time.time() - retention_days * 86400
        
        with self.transaction() as conn:
            # 清理感知历史
            conn.execute(
                "DELETE FROM perception_history WHERE timestamp < ?",
                (cutoff_time,)
            )
            perception_deleted = conn.total_changes
            
            # 清理预测历史
            conn.execute(
                "DELETE FROM prediction_history WHERE timestamp < ?",
                (cutoff_time,)
            )
            
            # 清理已完成的任务
            conn.execute(
                """DELETE FROM task_history 
                   WHERE status IN ('completed', 'cancelled') 
                   AND completed_at < ?""",
                (cutoff_time,)
            )
            
            # VACUUM优化
            conn.execute("VACUUM")
            
        return perception_deleted
```

## 33.3 文件存储设计

### 33.3.1 模型快照存储

```python
import os
import shutil
from pathlib import Path

class SnapshotManager:
    """
    模型快照管理器
    
    管理模型版本的保存、加载、回滚
    """
    
    def __init__(self, snapshot_dir: str):
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        
    async def create_snapshot(
        self,
        name: str,
        model_data: Dict[str, Any],
        metadata: Optional[Dict] = None
    ) -> str:
        """
        创建模型快照
        
        Returns:
            快照ID
        """
        snapshot_id = f"{name}_{int(time.time())}"
        snapshot_path = self.snapshot_dir / snapshot_id
        snapshot_path.mkdir(exist_ok=True)
        
        # 保存模型数据
        for model_name, model in model_data.items():
            model_file = snapshot_path / f"{model_name}.pkl"
            with open(model_file, 'wb') as f:
                pickle.dump(model, f)
                
        # 保存元数据
        meta = {
            'id': snapshot_id,
            'name': name,
            'created_at': time.time(),
            'models': list(model_data.keys()),
            **(metadata or {})
        }
        
        meta_file = snapshot_path / "metadata.json"
        with open(meta_file, 'w') as f:
            json.dump(meta, f, indent=2)
            
        return snapshot_id
        
    async def load_snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        """加载模型快照"""
        snapshot_path = self.snapshot_dir / snapshot_id
        
        if not snapshot_path.exists():
            raise FileNotFoundError(f"快照不存在: {snapshot_id}")
            
        # 加载元数据
        meta_file = snapshot_path / "metadata.json"
        with open(meta_file, 'r') as f:
            metadata = json.load(f)
            
        # 加载模型
        models = {}
        for model_name in metadata['models']:
            model_file = snapshot_path / f"{model_name}.pkl"
            with open(model_file, 'rb') as f:
                models[model_name] = pickle.load(f)
                
        return {'metadata': metadata, 'models': models}
        
    async def list_snapshots(self) -> List[Dict]:
        """列出所有快照"""
        snapshots = []
        
        for snapshot_path in sorted(self.snapshot_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if snapshot_path.is_dir():
                meta_file = snapshot_path / "metadata.json"
                if meta_file.exists():
                    with open(meta_file, 'r') as f:
                        snapshots.append(json.load(f))
                        
        return snapshots
        
    async def rollback(self, snapshot_id: str) -> bool:
        """回滚到指定快照"""
        # 验证快照存在
        snapshot_path = self.snapshot_dir / snapshot_id
        if not snapshot_path.exists():
            return False
            
        # 创建当前状态的备份
        current_backup = self.snapshot_dir / f"auto_backup_{int(time.time())}"
        current_backup.mkdir(exist_ok=True)
        
        # 复制当前模型到备份
        for model_file in self.snapshot_dir.glob("current/*.pkl"):
            shutil.copy2(model_file, current_backup)
            
        # 恢复快照
        snapshot_models = snapshot_path / "*.pkl"
        current_dir = self.snapshot_dir / "current"
        current_dir.mkdir(exist_ok=True)
        
        for model_file in snapshot_path.glob("*.pkl"):
            shutil.copy2(model_file, current_dir)
            
        return True
```

### 33.3.2 日志存储

```python
import logging
from logging.handlers import RotatingFileHandler

class AgentLogger:
    """
    Agent专用日志系统
    
    特性：
    - 结构化日志
    - 自动轮转
    - 分级存储
    """
    
    def __init__(self, log_dir: str, max_bytes: int = 10*1024*1024, backup_count: int = 5):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 主日志
        self.main_logger = logging.getLogger("agent.main")
        self.main_logger.setLevel(logging.DEBUG)
        
        # 文件处理器（轮转）
        file_handler = RotatingFileHandler(
            self.log_dir / "agent.log",
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setLevel(logging.INFO)
        
        # 错误日志（单独文件）
        error_handler = RotatingFileHandler(
            self.log_dir / "agent.error.log",
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        error_handler.setLevel(logging.ERROR)
        
        # 结构化日志（JSON格式）
        json_handler = RotatingFileHandler(
            self.log_dir / "agent.json.log",
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        json_handler.setLevel(logging.DEBUG)
        
        # 格式化器
        standard_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        )
        
        import pythonjsonlogger.jsonlogger
        json_formatter = pythonjsonlogger.jsonlogger.JsonFormatter(
            '%(asctime)s %(name)s %(levelname)s %(message)s'
        )
        
        file_handler.setFormatter(standard_formatter)
        error_handler.setFormatter(standard_formatter)
        json_handler.setFormatter(json_formatter)
        
        self.main_logger.addHandler(file_handler)
        self.main_logger.addHandler(error_handler)
        self.main_logger.addHandler(json_handler)
        
    def log_event(self, event_type: str, data: Dict):
        """记录结构化事件"""
        self.main_logger.info(f"EVENT:{event_type}", extra=data)
        
    def log_metric(self, metric_name: str, value: float, tags: Optional[Dict] = None):
        """记录指标"""
        self.main_logger.debug(
            f"METRIC:{metric_name}={value}",
            extra={'metric_name': metric_name, 'value': value, 'tags': tags or {}}
        )
```

## 33.4 缓存策略

### 33.4.1 多级缓存

```python
from functools import lru_cache
import time

class MultiLevelCache:
    """
    多级缓存系统
    
    L1: 内存缓存（最快，最小）
    L2: 本地文件缓存（中等速度，中等容量）
    L3: 数据库存储（最慢，最大容量）
    """
    
    def __init__(self, l1_size: int = 1000, l2_dir: str = "./cache"):
        self.l1_cache = {}  # 简单字典
        self.l1_timestamps = {}
        self.l1_max_size = l1_size
        
        self.l2_dir = Path(l2_dir)
        self.l2_dir.mkdir(parents=True, exist_ok=True)
        
        self.l3_db = None  # 数据库连接
        
    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        # L1查找
        if key in self.l1_cache:
            return self.l1_cache[key]
            
        # L2查找
        l2_path = self.l2_dir / f"{key}.cache"
        if l2_path.exists():
            with open(l2_path, 'rb') as f:
                value = pickle.load(f)
            # 提升到L1
            await self._l1_set(key, value)
            return value
            
        # L3查找
        if self.l3_db:
            value = await self._l3_get(key)
            if value is not None:
                # 提升到L2和L1
                await self._l2_set(key, value)
                await self._l1_set(key, value)
            return value
            
        return None
        
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值"""
        await self._l1_set(key, value)
        await self._l2_set(key, value)
        if self.l3_db:
            await self._l3_set(key, value, ttl)
            
    async def _l1_set(self, key: str, value: Any) -> None:
        """L1缓存设置"""
        # LRU淘汰
        if len(self.l1_cache) >= self.l1_max_size:
            oldest_key = min(self.l1_timestamps, key=self.l1_timestamps.get)
            del self.l1_cache[oldest_key]
            del self.l1_timestamps[oldest_key]
            
        self.l1_cache[key] = value
        self.l1_timestamps[key] = time.time()
        
    async def _l2_set(self, key: str, value: Any) -> None:
        """L2缓存设置"""
        l2_path = self.l2_dir / f"{key}.cache"
        with open(l2_path, 'wb') as f:
            pickle.dump(value, f)
            
    async def invalidate(self, key: str) -> None:
        """使缓存失效"""
        # L1删除
        self.l1_cache.pop(key, None)
        self.l1_timestamps.pop(key, None)
        
        # L2删除
        l2_path = self.l2_dir / f"{key}.cache"
        l2_path.unlink(missing_ok=True)
        
        # L3删除
        if self.l3_db:
            await self._l3_delete(key)
```

## 33.5 本章小结

本章详细设计了自驱永续进化Agent系统的数据结构与存储方案：

1. **内存数据结构**：循环缓冲区、动态优先级队列、稀疏矩阵
2. **数据库存储**：SQLite Schema设计、数据库访问层
3. **文件存储**：模型快照管理、日志存储
4. **缓存策略**：多级缓存系统

这些设计确保了系统在高频运行下的数据一致性和访问效率。
