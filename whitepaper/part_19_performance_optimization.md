# 性能优化与工程实践

## 1. 计算性能优化

### 1.1 向量化计算

使用NumPy的向量化操作替代Python循环，可提升10-100倍性能：

```python
# 优化前：Python循环
errors = []
for i in range(len(predictions)):
    error = (predictions[i] - actuals[i]) ** 2
    errors.append(error)
mean_error = sum(errors) / len(errors)

# 优化后：NumPy向量化
errors = (predictions - actuals) ** 2
mean_error = np.mean(errors)
```

### 1.2 缓存策略

#### 1.2.1 LRU缓存

```python
from functools import lru_cache

class CachedPredictor:
    def __init__(self, maxsize=128):
        self._predict = lru_cache(maxsize=maxsize)(self._predict_impl)
    
    def _predict_impl(self, state_tuple):
        """实际预测实现"""
        state = np.array(state_tuple)
        return self.model.predict(state)
    
    def predict(self, state):
        """带缓存的预测"""
        state_tuple = tuple(state.flatten())
        return self._predict(state_tuple)
```

#### 1.2.2 预计算缓存

```python
class PrecomputedCache:
    """预计算缓存"""
    
    def __init__(self):
        self._feature_cache = {}
        self._score_cache = {}
    
    def get_or_compute_feature(self, state, feature_name):
        """获取或计算特征"""
        key = (hash(state.tobytes()), feature_name)
        
        if key not in self._feature_cache:
            self._feature_cache[key] = self._compute_feature(state, feature_name)
        
        return self._feature_cache[key]
    
    def invalidate_old_cache(self, max_age_seconds=60):
        """失效旧缓存"""
        current_time = time.time()
        # 实现缓存清理逻辑
```

### 1.3 并行计算

#### 1.3.1 多线程任务评分

```python
from concurrent.futures import ThreadPoolExecutor

class ParallelTaskScorer:
    def __init__(self, max_workers=4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
    
    def score_tasks_parallel(self, tasks, state_vector, drive_output):
        """并行评分多个任务"""
        futures = []
        
        for task in tasks:
            future = self.executor.submit(
                self._score_task, task, state_vector, drive_output
            )
            futures.append((task, future))
        
        results = []
        for task, future in futures:
            try:
                score = future.result(timeout=1.0)
                results.append((task, score))
            except TimeoutError:
                results.append((task, 0.0))
        
        return results
```

#### 1.3.2 异步I/O

```python
import aiofiles

class AsyncStorage:
    """异步存储"""
    
    async def write_batch(self, records):
        """异步批量写入"""
        async with aiofiles.open(self.file_path, 'a') as f:
            for record in records:
                await f.write(json.dumps(record) + '\n')
    
    async def read_batch(self, offset, limit):
        """异步批量读取"""
        async with aiofiles.open(self.file_path, 'r') as f:
            await f.seek(offset)
            lines = []
            for _ in range(limit):
                line = await f.readline()
                if not line:
                    break
                lines.append(json.loads(line))
            return lines
```

## 2. 内存优化

### 2.1 内存池管理

```python
class MemoryPool:
    """内存池管理"""
    
    def __init__(self, object_size, pool_size=1000):
        self.object_size = object_size
        self.pool_size = pool_size
        self.available = []
        self.in_use = set()
        
        # 预分配内存
        for _ in range(pool_size):
            self.available.append(np.zeros(object_size))
    
    def acquire(self):
        """获取内存块"""
        if self.available:
            obj = self.available.pop()
            self.in_use.add(id(obj))
            return obj
        else:
            # 池耗尽，分配新内存
            return np.zeros(self.object_size)
    
    def release(self, obj):
        """释放内存块"""
        obj_id = id(obj)
        if obj_id in self.in_use:
            self.in_use.remove(obj_id)
            obj.fill(0)  # 清零
            self.available.append(obj)
```

### 2.2 数据压缩

```python
import zlib
import pickle

class CompressedStorage:
    """压缩存储"""
    
    def __init__(self, compression_level=6):
        self.compression_level = compression_level
    
    def compress_data(self, data):
        """压缩数据"""
        pickled = pickle.dumps(data)
        compressed = zlib.compress(pickled, self.compression_level)
        return compressed
    
    def decompress_data(self, compressed):
        """解压数据"""
        pickled = zlib.decompress(compressed)
        data = pickle.loads(pickled)
        return data
    
    def get_compression_ratio(self, data):
        """获取压缩比"""
        original_size = len(pickle.dumps(data))
        compressed_size = len(self.compress_data(data))
        return original_size / compressed_size
```

### 2.3 内存映射

```python
import mmap

class MemoryMappedStorage:
    """内存映射存储"""
    
    def __init__(self, filepath, size):
        self.filepath = filepath
        self.size = size
        
        # 创建文件
        with open(filepath, 'wb') as f:
            f.write(b'\x00' * size)
        
        # 内存映射
        self.file = open(filepath, 'r+b')
        self.mm = mmap.mmap(self.file.fileno(), size)
    
    def write(self, offset, data):
        """写入数据"""
        self.mm.seek(offset)
        self.mm.write(data)
    
    def read(self, offset, length):
        """读取数据"""
        self.mm.seek(offset)
        return self.mm.read(length)
    
    def close(self):
        """关闭映射"""
        self.mm.close()
        self.file.close()
```

## 3. 存储优化

### 3.1 数据库索引优化

```sql
-- 主键索引
CREATE TABLE perceptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    state_vector BLOB NOT NULL,
    data_quality REAL
);

-- 时间索引（用于范围查询）
CREATE INDEX idx_perceptions_time ON perceptions(timestamp);

-- 复合索引（用于多条件查询）
CREATE INDEX idx_perceptions_time_quality ON perceptions(timestamp, data_quality);

-- 覆盖索引（避免回表查询）
CREATE INDEX idx_drives_summary ON drives(timestamp, reward_total, gap_safe);

-- 部分索引（只索引高价值数据）
CREATE INDEX idx_high_quality_perceptions ON perceptions(timestamp) 
WHERE data_quality > 0.8;
```

### 3.2 分区策略

```python
class PartitionedStorage:
    """分区存储"""
    
    def __init__(self, partition_duration=timedelta(days=1)):
        self.partition_duration = partition_duration
        self.partitions = {}
    
    def get_partition(self, timestamp):
        """获取对应分区"""
        partition_key = timestamp.strftime('%Y%m%d')
        
        if partition_key not in self.partitions:
            self.partitions[partition_key] = self._create_partition(partition_key)
        
        return self.partitions[partition_key]
    
    def _create_partition(self, partition_key):
        """创建新分区"""
        return {
            'filepath': f'data/perceptions_{partition_key}.db',
            'start_time': datetime.strptime(partition_key, '%Y%m%d'),
            'record_count': 0
        }
    
    def cleanup_old_partitions(self, retention_days=30):
        """清理旧分区"""
        cutoff = datetime.now() - timedelta(days=retention_days)
        
        for key in list(self.partitions.keys()):
            partition = self.partitions[key]
            if partition['start_time'] < cutoff:
                # 归档或删除
                self._archive_partition(partition)
                del self.partitions[key]
```

## 4. 网络优化（如适用）

### 4.1 连接池

```python
class ConnectionPool:
    """连接池"""
    
    def __init__(self, max_connections=10):
        self.max_connections = max_connections
        self.available = []
        self.in_use = []
    
    def get_connection(self):
        """获取连接"""
        if self.available:
            conn = self.available.pop()
            self.in_use.append(conn)
            return conn
        
        if len(self.in_use) < self.max_connections:
            conn = self._create_connection()
            self.in_use.append(conn)
            return conn
        
        raise PoolExhaustedError()
    
    def release_connection(self, conn):
        """释放连接"""
        if conn in self.in_use:
            self.in_use.remove(conn)
            self.available.append(conn)
```

### 4.2 数据序列化优化

```python
import msgpack
import orjson

class OptimizedSerializer:
    """优化序列化"""
    
    @staticmethod
    def serialize_json(data):
        """使用orjson进行快速JSON序列化"""
        return orjson.dumps(data)
    
    @staticmethod
    def deserialize_json(data):
        """使用orjson进行快速JSON反序列化"""
        return orjson.loads(data)
    
    @staticmethod
    def serialize_msgpack(data):
        """使用msgpack进行二进制序列化"""
        return msgpack.packb(data, use_bin_type=True)
    
    @staticmethod
    def deserialize_msgpack(data):
        """使用msgpack进行二进制反序列化"""
        return msgpack.unpackb(data, raw=False)
```

## 5. 算法优化

### 5.1 近似算法

```python
class ApproximateAlgorithms:
    """近似算法"""
    
    @staticmethod
    def approximate_median(data, epsilon=0.1):
        """
        近似中位数
        
        使用随机采样近似，O(1/epsilon^2)复杂度
        """
        sample_size = int(1 / (epsilon ** 2))
        sample = random.sample(data, min(sample_size, len(data)))
        return np.median(sample)
    
    @staticmethod
    def count_min_sketch(data, width=1000, depth=5):
        """
        Count-Min Sketch
        
        近似频率统计，亚线性空间
        """
        sketch = np.zeros((depth, width))
        
        for item in data:
            for d in range(depth):
                hash_val = hash((item, d)) % width
                sketch[d][hash_val] += 1
        
        return sketch
```

### 5.2 增量计算

```python
class IncrementalStatistics:
    """增量统计"""
    
    def __init__(self):
        self.n = 0
        self.mean = 0
        self.m2 = 0  # 用于计算方差
    
    def update(self, x):
        """增量更新统计量"""
        self.n += 1
        delta = x - self.mean
        self.mean += delta / self.n
        delta2 = x - self.mean
        self.m2 += delta * delta2
    
    def get_mean(self):
        return self.mean
    
    def get_variance(self):
        return self.m2 / self.n if self.n > 0 else 0
    
    def get_std(self):
        return np.sqrt(self.get_variance())
    
    def merge(self, other):
        """合并两个统计量"""
        combined_n = self.n + other.n
        
        delta = other.mean - self.mean
        combined_mean = self.mean + delta * other.n / combined_n
        
        combined_m2 = self.m2 + other.m2 + delta**2 * self.n * other.n / combined_n
        
        self.n = combined_n
        self.mean = combined_mean
        self.m2 = combined_m2
```

## 6. 监控与调优

### 6.1 性能监控

```python
import time
from contextlib import contextmanager

class PerformanceMonitor:
    """性能监控"""
    
    def __init__(self):
        self.metrics = {}
    
    @contextmanager
    def measure(self, operation_name):
        """测量操作耗时"""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            
            if operation_name not in self.metrics:
                self.metrics[operation_name] = []
            
            self.metrics[operation_name].append(elapsed)
    
    def get_stats(self, operation_name):
        """获取统计信息"""
        times = self.metrics.get(operation_name, [])
        
        if not times:
            return None
        
        return {
            'count': len(times),
            'mean': np.mean(times),
            'median': np.median(times),
            'p95': np.percentile(times, 95),
            'p99': np.percentile(times, 99),
            'max': np.max(times)
        }
    
    def report(self):
        """生成性能报告"""
        report = []
        for op_name in self.metrics:
            stats = self.get_stats(op_name)
            report.append(f"{op_name}: {stats}")
        
        return '\n'.join(report)
```

### 6.2 自动调优

```python
class AutoTuner:
    """自动调优器"""
    
    def __init__(self, config_space):
        self.config_space = config_space
        self.history = []
    
    def suggest_config(self):
        """建议配置"""
        if len(self.history) < 10:
            # 随机探索
            return self._random_config()
        else:
            # 贝叶斯优化
            return self._bayesian_optimize()
    
    def _random_config(self):
        """随机配置"""
        config = {}
        for param, space in self.config_space.items():
            if space['type'] == 'float':
                config[param] = random.uniform(space['low'], space['high'])
            elif space['type'] == 'int':
                config[param] = random.randint(space['low'], space['high'])
            elif space['type'] == 'choice':
                config[param] = random.choice(space['options'])
        
        return config
    
    def _bayesian_optimize(self):
        """贝叶斯优化"""
        # 使用高斯过程建模
        from sklearn.gaussian_process import GaussianProcessRegressor
        
        X = [h['config'] for h in self.history]
        y = [h['performance'] for h in self.history]
        
        gp = GaussianProcessRegressor()
        gp.fit(X, y)
        
        # 获取采集函数（Expected Improvement）
        best_performance = max(y)
        
        def acquisition(config):
            mean, std = gp.predict([config], return_std=True)
            ei = (mean - best_performance) * norm.cdf((mean - best_performance) / std)
            ei += std * norm.pdf((mean - best_performance) / std)
            return ei
        
        # 优化采集函数
        best_config = max(
            [self._random_config() for _ in range(100)],
            key=acquisition
        )
        
        return best_config
    
    def report_result(self, config, performance):
        """报告结果"""
        self.history.append({
            'config': config,
            'performance': performance,
            'timestamp': time.time()
        })
```

## 7. 部署优化

### 7.1 容器化

```dockerfile
# Dockerfile
FROM python:3.9-slim

# 安装依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 设置资源限制
ENV AGENT_MAX_CPU=20
ENV AGENT_MAX_MEMORY=20

# 启动命令
CMD ["python", "main.py"]
```

### 7.2 系统服务配置

```ini
# /etc/systemd/system/agent.service
[Unit]
Description=Self-Evolving Agent
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
TasksMax=50

# 安全限制
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/agent/storage

[Install]
WantedBy=multi-user.target
```

---

性能优化与工程实践部分提供了Agent系统在实际部署中的优化策略，从计算、内存、存储到网络，从算法到系统配置，确保Agent在资源受限的单机环境下高效运行。
