# 测试策略与质量保证

## 1. 测试金字塔

```
                    /\
                   /  \
                  / E2E \         端到端测试 (5%)
                 /--------\
                /          \
               / Integration \    集成测试 (15%)
              /--------------\
             /                \
            /    Unit Tests    \   单元测试 (80%)
           /--------------------\
```

## 2. 单元测试

### 2.1 感知模块测试

```python
# tests/test_perception.py

import pytest
import numpy as np
from unittest.mock import Mock, patch

from modules.perception import EnvironmentPerception
from modules.perception.system_monitor import SystemMonitor


class TestSystemMonitor:
    """系统监控测试"""
    
    def test_cpu_sampling(self):
        """测试CPU采样"""
        monitor = SystemMonitor()
        
        with patch('psutil.cpu_percent') as mock_cpu:
            mock_cpu.return_value = 45.5
            
            cpu_usage = monitor.sample_cpu()
            
            assert cpu_usage == 45.5
            mock_cpu.assert_called_once()
    
    def test_memory_sampling(self):
        """测试内存采样"""
        monitor = SystemMonitor()
        
        with patch('psutil.virtual_memory') as mock_mem:
            mock_mem.return_value = Mock(
                percent=60.0,
                available=4 * 1024 * 1024 * 1024,
                total=16 * 1024 * 1024 * 1024
            )
            
            mem_info = monitor.sample_memory()
            
            assert mem_info['usage'] == 60.0
            assert mem_info['available_ratio'] == 0.25
    
    def test_anomaly_detection(self):
        """测试异常检测"""
        monitor = SystemMonitor()
        
        # 正常值
        assert not monitor.is_anomalous(50, mean=45, std=10)
        
        # 异常值（3σ外）
        assert monitor.is_anomalous(100, mean=45, std=10)
    
    def test_smoothing(self):
        """测试平滑处理"""
        monitor = SystemMonitor(alpha=0.3)
        
        values = [10, 20, 30, 20, 10]
        smoothed = []
        
        for v in values:
            smoothed.append(monitor.smooth(v))
        
        # 平滑后的值应该比原始值更稳定
        assert np.std(smoothed) < np.std(values)


class TestEnvironmentPerception:
    """环境感知模块测试"""
    
    def test_state_vector_generation(self):
        """测试状态向量生成"""
        perception = EnvironmentPerception()
        
        with patch.object(perception, '_sample_system') as mock_sys:
            mock_sys.return_value = {
                'cpu': 50.0,
                'memory': 60.0,
                'disk': 70.0
            }
            
            state = perception.get_current_state()
            
            assert state is not None
            assert len(state.values) > 0
    
    def test_state_vector_normalization(self):
        """测试状态向量归一化"""
        perception = EnvironmentPerception()
        
        raw_values = [0, 50, 100]
        normalized = perception.normalize(raw_values)
        
        assert all(0 <= v <= 1 for v in normalized)
        assert normalized[0] == 0.0
        assert normalized[2] == 1.0
    
    def test_resource_limit(self):
        """测试资源限制"""
        config = PerceptionConfig(max_cpu_usage_percent=2.0)
        perception = EnvironmentPerception(config)
        
        # 模拟高负载
        with patch.object(perception, '_get_cpu_usage') as mock_cpu:
            mock_cpu.return_value = 5.0  # 超过限制
            
            perception.check_resource_limit()
            
            # 应该降低采样频率
            assert perception.current_interval > perception.base_interval
```

### 2.2 驱力引擎测试

```python
# tests/test_drive.py

import pytest
from modules.drive import DriveEngine


class TestDriveEngine:
    """驱力引擎测试"""
    
    def test_safe_drive_normal(self):
        """测试正常状态下的安全驱力"""
        engine = DriveEngine()
        
        state = MockState(
            cpu_usage=30.0,
            memory_usage=40.0,
            error_count=0
        )
        
        reward_safe = engine.compute_safe_drive(state)
        
        assert 0.8 <= reward_safe <= 1.0
    
    def test_safe_drive_threat(self):
        """测试威胁状态下的安全驱力"""
        engine = DriveEngine()
        
        state = MockState(
            cpu_usage=95.0,
            memory_usage=90.0,
            error_count=10
        )
        
        reward_safe = engine.compute_safe_drive(state)
        
        assert reward_safe < 0.5
    
    def test_gain_drive_high_error(self):
        """测试高误差时的收益驱力"""
        engine = DriveEngine()
        
        state = MockState(prediction_error=0.5)
        
        reward_gain = engine.compute_gain_drive(state)
        
        assert reward_gain < 0.5  # 误差高，收益低
    
    def test_weight_adjustment(self):
        """测试权重调整"""
        engine = DriveEngine()
        
        # 紧急场景
        engine.adjust_weights(scene='emergency')
        weights = engine.get_weights()
        
        assert weights['safe'] > weights['gain']
        assert weights['safe'] > weights['eff']
        
        # 稳态场景
        engine.adjust_weights(scene='stable')
        weights = engine.get_weights()
        
        assert weights['gain'] > weights['safe']
    
    def test_gap_calculation(self):
        """测试缺口计算"""
        engine = DriveEngine()
        
        engine.reward_safe = 0.8
        engine.reward_gain = 0.6
        engine.reward_eff = 0.7
        
        gaps = engine.compute_gaps()
        
        assert gaps['safe'] == 0.2
        assert gaps['gain'] == 0.4
        assert gaps['eff'] == 0.3
```

### 2.3 预测模型测试

```python
# tests/test_prediction.py

import pytest
import numpy as np
from modules.prediction import AdaptiveExponentialSmoother, OnlineLSTM


class TestAdaptiveExponentialSmoother:
    """自适应指数平滑测试"""
    
    def test_basic_prediction(self):
        """测试基本预测"""
        smoother = AdaptiveExponentialSmoother()
        
        # 训练数据
        data = [10, 10, 10, 10, 10]
        for x in data:
            smoother.update(x)
        
        # 预测
        prediction = smoother.predict()
        
        assert abs(prediction - 10) < 0.1
    
    def test_adaptation(self):
        """测试自适应能力"""
        smoother = AdaptiveExponentialSmoother()
        
        # 稳定期
        for _ in range(50):
            smoother.update(10)
        
        # 突变
        for _ in range(10):
            smoother.update(20)
        
        prediction = smoother.predict()
        
        # 应该适应新值
        assert prediction > 15
    
    def test_trend_detection(self):
        """测试趋势检测"""
        smoother = AdaptiveExponentialSmoother()
        
        # 上升趋势
        for i in range(20):
            smoother.update(10 + i)
        
        # 应该切换到Holt方法
        assert smoother.current_method == 'holt'


class TestOnlineLSTM:
    """在线LSTM测试"""
    
    def test_sequence_prediction(self):
        """测试序列预测"""
        model = OnlineLSTM(input_size=5, hidden_size=10, output_size=1)
        
        # 生成训练数据
        sequences = []
        targets = []
        for i in range(100):
            seq = np.sin(np.linspace(0, 2*np.pi, 5)) + np.random.normal(0, 0.1, 5)
            target = np.sin(2*np.pi) + np.random.normal(0, 0.1)
            sequences.append(seq)
            targets.append(target)
        
        # 训练
        for seq, target in zip(sequences, targets):
            model.update(seq, target)
        
        # 预测
        test_seq = np.sin(np.linspace(0, 2*np.pi, 5))
        prediction = model.predict(test_seq)
        
        assert prediction is not None
        assert not np.isnan(prediction)
    
    def test_incremental_learning(self):
        """测试增量学习"""
        model = OnlineLSTM(input_size=3, hidden_size=5, output_size=1)
        
        # 第一阶段数据
        for _ in range(50):
            model.update(np.array([1, 2, 3]), 6)
        
        pred1 = model.predict(np.array([1, 2, 3]))
        
        # 第二阶段数据（不同分布）
        for _ in range(50):
            model.update(np.array([2, 4, 6]), 12)
        
        pred2 = model.predict(np.array([2, 4, 6]))
        
        # 应该适应新分布
        assert abs(pred2 - 12) < abs(pred1 - 6)
```

## 3. 集成测试

### 3.1 端到端闭环测试

```python
# tests/test_integration.py

import pytest
import asyncio
from agent import SelfEvolvingAgent


class TestEndToEndLoop:
    """端到端闭环测试"""
    
    @pytest.fixture
    async def agent(self):
        """创建测试Agent"""
        config = AgentConfig(
            cycle_interval=0.1,  # 快速循环用于测试
            perception=PerceptionConfig(
                cpu_sample_interval=0.1,
                memory_sample_interval=0.1
            )
        )
        
        agent = SelfEvolvingAgent(config)
        yield agent
        agent.shutdown()
    
    async def test_full_cycle(self, agent):
        """测试完整循环"""
        # 运行10个循环
        for _ in range(10):
            await agent._run_cycle()
        
        # 验证状态更新
        assert agent.state.cycle_count == 10
        
        # 验证记忆记录
        assert len(agent.memory.perception_buffer) > 0
        assert len(agent.memory.drive_buffer) > 0
    
    async def test_task_execution(self, agent):
        """测试任务执行"""
        # 运行直到有任务执行
        for _ in range(20):
            await agent._run_cycle()
            if agent.memory.task_buffer:
                break
        
        # 验证任务执行记录
        assert len(agent.memory.task_buffer) > 0
        
        # 验证任务有结果
        last_task = agent.memory.task_buffer[-1]
        assert hasattr(last_task, 'execution_result')
    
    async def test_prediction_feedback(self, agent):
        """测试预测反馈"""
        # 运行多个循环
        for _ in range(50):
            await agent._run_cycle()
        
        # 验证预测误差被记录
        assert len(agent.memory.prediction_buffer) > 0
        
        # 验证误差在合理范围
        errors = [p.error for p in agent.memory.prediction_buffer]
        assert all(0 <= e <= 1 for e in errors)
    
    async def test_drive_evolution(self, agent):
        """测试驱力进化"""
        initial_weights = agent.drive_engine.get_weights().copy()
        
        # 模拟紧急场景
        with patch.object(agent.perception, 'get_current_state') as mock_state:
            mock_state.return_value = MockState(
                cpu_usage=95.0,
                threat_level=0.9
            )
            
            for _ in range(10):
                await agent._run_cycle()
        
        # 验证权重调整
        final_weights = agent.drive_engine.get_weights()
        assert final_weights['safe'] > initial_weights['safe']
```

### 3.2 模块间交互测试

```python
# tests/test_module_interaction.py

class TestPerceptionDriveInteraction:
    """感知-驱力交互测试"""
    
    def test_anomaly_triggers_safe_drive(self):
        """测试异常触发安全驱力"""
        perception = EnvironmentPerception()
        drive = DriveEngine()
        
        # 生成异常状态
        anomalous_state = perception.generate_test_state(
            cpu_usage=99.0,
            error_logs=['CRITICAL: System failure']
        )
        
        # 计算驱力
        drive_output = drive.compute(anomalous_state)
        
        # 安全驱力应该很低（缺口高）
        assert drive_output.gap_safe > 0.7
        
        # 应该生成安全任务
        tasks = TaskGenerator().generate_tasks(drive_output, anomalous_state)
        safe_tasks = [t for t in tasks if t.drive_type == 'safe']
        assert len(safe_tasks) > 0


class TestDecisionExecutionInteraction:
    """决策-执行交互测试"""
    
    def test_high_priority_interrupt(self):
        """测试高优先级中断"""
        decision = DecisionEngine()
        
        # 当前低优先级任务
        current_task = MockTask(priority=0.3, drive_type='gain')
        
        # 新的高优先级缺口
        new_drive = MockDriveOutput(gap_safe=0.9)
        
        # 决策应该中断当前任务
        result = decision.decide(
            state=MockState(),
            drive_output=new_drive,
            task_pool=[MockTask(priority=0.8, drive_type='safe')],
            current_task=current_task
        )
        
        assert result.should_interrupt
        assert result.selected_task.drive_type == 'safe'
```

## 4. 性能测试

### 4.1 基准测试

```python
# tests/test_performance.py

import pytest
import time
from statistics import mean


class TestPerformanceBenchmarks:
    """性能基准测试"""
    
    def test_cycle_latency(self):
        """测试循环延迟"""
        agent = SelfEvolvingAgent()
        
        latencies = []
        for _ in range(100):
            start = time.perf_counter()
            asyncio.run(agent._run_cycle())
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)
        
        avg_latency = mean(latencies)
        p99_latency = np.percentile(latencies, 99)
        
        # 断言性能要求
        assert avg_latency < 1.0, f"Average latency {avg_latency}s exceeds 1s"
        assert p99_latency < 2.0, f"P99 latency {p99_latency}s exceeds 2s"
    
    def test_perception_overhead(self):
        """测试感知模块开销"""
        perception = EnvironmentPerception()
        
        cpu_usages = []
        for _ in range(50):
            start_cpu = get_process_cpu()
            perception.get_current_state()
            end_cpu = get_process_cpu()
            cpu_usages.append(end_cpu - start_cpu)
        
        avg_cpu = mean(cpu_usages)
        
        # 感知模块CPU占用应<2%
        assert avg_cpu < 2.0
    
    def test_memory_growth(self):
        """测试内存增长"""
        agent = SelfEvolvingAgent()
        
        initial_mem = get_process_memory()
        
        # 运行1000个循环
        for _ in range(1000):
            asyncio.run(agent._run_cycle())
        
        final_mem = get_process_memory()
        mem_growth = final_mem - initial_mem
        
        # 内存增长应<100MB/1000循环
        assert mem_growth < 100 * 1024 * 1024
    
    def test_prediction_accuracy_benchmark(self):
        """测试预测精度基准"""
        predictor = MultiLayerPredictor()
        
        # 生成测试数据
        test_data = generate_synthetic_data(n=1000, pattern='seasonal')
        
        errors = []
        for i in range(100, 1000):
            history = test_data[:i]
            actual = test_data[i]
            
            prediction = predictor.predict(history, horizon=1)
            error = abs(prediction - actual) / actual
            errors.append(error)
        
        mape = mean(errors) * 100
        
        # MAPE应<10%
        assert mape < 10.0, f"MAPE {mape}% exceeds 10%"
```

### 4.2 压力测试

```python
# tests/test_stress.py

import pytest
import multiprocessing


class TestStressConditions:
    """压力条件测试"""
    
    def test_high_cpu_load(self):
        """测试高CPU负载下的行为"""
        # 创建CPU负载
        load_process = multiprocessing.Process(target=cpu_load_generator)
        load_process.start()
        
        try:
            agent = SelfEvolvingAgent()
            
            # Agent应适应高负载
            for _ in range(50):
                asyncio.run(agent._run_cycle())
            
            # 验证Agent自身CPU使用受限
            agent_cpu = get_agent_cpu_usage()
            assert agent_cpu <= 20.0
            
            # 验证任务选择偏向能效
            recent_tasks = agent.memory.get_recent_tasks(50)
            eff_tasks = [t for t in recent_tasks if t.drive_type == 'eff']
            assert len(eff_tasks) > len(recent_tasks) * 0.3
            
        finally:
            load_process.terminate()
    
    def test_memory_pressure(self):
        """测试内存压力下的行为"""
        # 模拟内存压力
        memory_hog = bytearray(1024 * 1024 * 1024)  # 1GB
        
        try:
            agent = SelfEvolvingAgent()
            
            for _ in range(50):
                asyncio.run(agent._run_cycle())
            
            # 验证Agent内存使用受限
            agent_mem = get_agent_memory_usage()
            assert agent_mem <= 20.0
            
        finally:
            del memory_hog
    
    def test_rapid_state_changes(self):
        """测试快速状态变化"""
        agent = SelfEvolvingAgent()
        
        states = [
            MockState(cpu_usage=10),  # 低负载
            MockState(cpu_usage=90),  # 高负载
            MockState(cpu_usage=10),  # 低负载
            MockState(cpu_usage=95),  # 极高负载
        ]
        
        for state in states * 10:  # 重复10次
            with patch.object(agent.perception, 'get_current_state', return_value=state):
                asyncio.run(agent._run_cycle())
        
        # 验证Agent没有崩溃
        assert agent.state.running
        
        # 验证有响应性
        assert len(agent.memory.drive_buffer) > 0
```

## 5. 安全测试

### 5.1 边界约束测试

```python
# tests/test_security.py

class TestSecurityConstraints:
    """安全约束测试"""
    
    def test_forbidden_path_access(self):
        """测试禁止路径访问"""
        from modules.security import is_path_allowed
        
        # 禁止路径
        assert not is_path_allowed('/etc/passwd')
        assert not is_path_allowed('/etc/shadow')
        assert not is_path_allowed('/proc/sys/kernel')
        
        # 允许路径
        assert is_path_allowed('/tmp/test')
        assert is_path_allowed('/home/user/documents')
    
    def test_resource_limit_enforcement(self):
        """测试资源限制执行"""
        agent = SelfEvolvingAgent()
        
        # 尝试超过CPU限制
        with patch.object(agent, '_get_cpu_usage', return_value=25.0):
            agent._enforce_resource_limits()
            
            # 应该降低活动水平
            assert agent.perception.current_interval > agent.perception.base_interval
    
    def test_model_rollback_on_degradation(self):
        """测试模型退化时回滚"""
        agent = SelfEvolvingAgent()
        
        # 创建快照
        snapshot_id = agent.memory.create_snapshot()
        
        # 模拟模型退化
        with patch.object(agent.predictor, 'get_error', return_value=0.9):
            agent._check_evolution()
            
            # 应该触发回滚
            assert agent.memory.last_rollback == snapshot_id
    
    def test_exploration_freeze_after_failures(self):
        """测试探索失败后冻结"""
        task = MockTask(task_type='exploration')
        
        # 模拟连续失败
        for _ in range(5):
            task.record_failure()
        
        # 应该被冻结
        assert task.is_frozen
        assert not task.can_execute()
```

## 6. 长期稳定性测试

### 6.1 持续运行测试

```python
# tests/test_long_term.py

import pytest


class TestLongTermStability:
    """长期稳定性测试"""
    
    def test_24_hour_run(self):
        """测试24小时连续运行"""
        agent = SelfEvolvingAgent()
        
        # 模拟24小时（加速）
        cycles = 24 * 60 * 60  # 1秒一个循环
        
        for i in range(cycles):
            asyncio.run(agent._run_cycle())
            
            # 每小时检查一次
            if i % 3600 == 0:
                assert agent.state.running
                assert agent.state.last_error is None
        
        # 验证进化指标
        evolution_state = agent.monitor.get_current_state()
        assert evolution_state.precision_score > 0
        assert evolution_state.breadth_score > 0
        assert evolution_state.efficiency_score > 0
    
    def test_memory_leak_detection(self):
        """测试内存泄漏检测"""
        agent = SelfEvolvingAgent()
        
        memory_samples = []
        
        for i in range(1000):
            asyncio.run(agent._run_cycle())
            
            if i % 100 == 0:
                mem = get_process_memory()
                memory_samples.append(mem)
        
        # 检查内存增长趋势
        from scipy import stats
        slope, _, _, _, _ = stats.linregress(range(len(memory_samples)), memory_samples)
        
        # 内存增长应<1MB/100循环
        assert slope < 1024 * 1024
    
    def test_storage_cleanup(self):
        """测试存储清理"""
        agent = SelfEvolvingAgent()
        
        # 运行产生大量数据
        for _ in range(10000):
            asyncio.run(agent._run_cycle())
        
        initial_size = get_storage_size()
        
        # 触发清理
        agent.memory.auto_cleanup()
        
        final_size = get_storage_size()
        
        # 存储应被清理
        assert final_size <= initial_size
```

## 7. 测试自动化

### 7.1 CI/CD集成

```yaml
# .github/workflows/test.yml
name: Agent Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    strategy:
      matrix:
        python-version: [3.8, 3.9, '3.10']
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-test.txt
    
    - name: Run unit tests
      run: pytest tests/ -v --cov=agent --cov-report=xml
    
    - name: Run integration tests
      run: pytest tests/test_integration.py -v
    
    - name: Run performance tests
      run: pytest tests/test_performance.py -v
    
    - name: Upload coverage
      uses: codecov/codecov-action@v1
      with:
        file: ./coverage.xml
```

### 7.2 测试报告

```python
# tests/conftest.py

import pytest


def pytest_configure(config):
    """配置pytest"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "performance: marks tests as performance tests"
    )


@pytest.fixture(scope='session')
def test_report_dir():
    """测试报告目录"""
    import os
    dir_path = 'test_reports'
    os.makedirs(dir_path, exist_ok=True)
    return dir_path


@pytest.fixture(autouse=True)
def log_test_execution(request):
    """自动记录测试执行"""
    start_time = time.time()
    
    yield
    
    elapsed = time.time() - start_time
    logging.info(f"Test {request.node.name} took {elapsed:.2f}s")
```

---

测试策略与质量保证部分建立了完整的测试体系，从单元测试到集成测试，从性能测试到安全测试，从短期验证到长期稳定性测试，确保Agent系统的可靠性和稳定性。
