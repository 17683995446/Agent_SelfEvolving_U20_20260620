"""
集成测试框架 — 阶段17

第一性原理：生物体的生存依赖于各器官系统的协调运作。
集成测试验证模块间的接口契约和端到端流程，确保"预测-误差-修正"闭环完整。

验收标准：
1. 所有模块可独立实例化并满足接口契约
2. Agent主类支持依赖注入（Mock替换）
3. 单步运行不抛异常
4. 异常状态和稳态检测正确
"""

from __future__ import annotations

import numpy as np
import pytest
from typing import Dict, List

from core.types import (
    STATE_VECTOR_DIM,
    EventType,
    MemoryEntry,
    Prediction,
    PredictionError,
    DriveState,
    DriveType,
    Task,
    SafetyEvent,
    SystemEvent,
)
from core.config import AgentConfig
from core.logger import get_logger
from core.event_bus import EventBus
from core.interfaces import (
    IPredictor,
    IDriveEngine,
    ISensor,
    IMemory,
    ITaskGenerator,
    ISafetyMonitor,
    IOptimizer,
)
from perception.system_monitor import SystemMonitor
from perception.anomaly_detector import AnomalyDetector
from drive.drive_base import DriveEngine
from prediction.gru_predictor import GRUPredictor
from prediction.ensemble_predictor import EnsemblePredictor
from memory.short_term_memory import ShortTermMemory
from task.task_generator import TaskGenerator
from safety.resource_limiter import ResourceLimiter
from agent import SelfEvolvingAgent as Agent


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def config(tmp_path_factory) -> AgentConfig:
    """使用临时目录的配置，避免测试污染 ./data/（秩序化阶段1：测试数据隔离）"""
    tmp_dir = tmp_path_factory.mktemp("agent_data")
    cfg = AgentConfig()
    cfg.data_dir = str(tmp_dir)
    cfg.long_term_db_path = str(tmp_dir / "memory.db")
    cfg.snapshot_dir = str(tmp_dir / "snapshots")
    return cfg


@pytest.fixture
def random_state() -> np.ndarray:
    return np.random.rand(STATE_VECTOR_DIM).astype(np.float32)


# =============================================================================
# 阶段1-5：核心基础设施测试
# =============================================================================

class TestCoreInfrastructure:
    def test_state_vector_dimension(self):
        assert STATE_VECTOR_DIM == 28

    def test_config_defaults(self, config: AgentConfig):
        assert config.state_vector_dim == 28
        assert 0 < config.exploration_ratio < 1
        errors = config.validate()
        assert len(errors) == 0, f"Config validation failed: {errors}"

    def test_logger_output(self, capsys):
        logger = get_logger("test_integration")
        logger.info("integration_test_message")
        # 日志输出到stdout，但get_logger使用缓存，不重复创建

    def test_event_bus_sync_dispatch(self):
        bus = EventBus()
        received: List[SystemEvent] = []
        bus.subscribe(EventType.SYSTEM_STATE, lambda e: received.append(e))
        event = SystemEvent(event_type=EventType.SYSTEM_STATE, payload={"test": True})
        bus.publish(event)
        bus._dispatch(event)
        assert len(received) == 1
        assert received[0].payload["test"] is True

    def test_interface_abstraction(self):
        assert hasattr(IPredictor, "predict")
        assert hasattr(IPredictor, "update")
        assert hasattr(IPredictor, "reset")
        assert hasattr(IDriveEngine, "compute")
        assert hasattr(ISensor, "read")
        assert hasattr(ISensor, "encode_to_vector")
        assert hasattr(IMemory, "store")
        assert hasattr(IMemory, "retrieve")
        assert hasattr(ITaskGenerator, "generate")
        assert hasattr(ISafetyMonitor, "check")
        assert hasattr(ISafetyMonitor, "is_within_limits")


# =============================================================================
# 阶段6-7：感知模块测试
# =============================================================================

class TestPerception:
    def test_system_monitor_encoding(self):
        sensor = SystemMonitor()
        raw = sensor.read()
        assert raw is not None
        out = sensor.encode_to_vector(raw)
        vec = out.feature_vector
        assert vec.shape == (STATE_VECTOR_DIM,)
        assert np.all((vec >= 0) & (vec <= 1))

    def test_anomaly_detector(self):
        detector = AnomalyDetector()
        vec = np.random.rand(STATE_VECTOR_DIM)
        for _ in range(15):
            result = detector.update(vec)
        assert "anomaly_score" in result
        assert 0 <= result["anomaly_score"] <= 1


# =============================================================================
# 阶段8：驱力引擎测试
# =============================================================================

class TestDriveEngine:
    def test_compute_returns_drive_state(self, config: AgentConfig, random_state: np.ndarray):
        engine = DriveEngine(config)
        state = random_state
        ds = engine.compute(state, 0.1)
        assert isinstance(ds, DriveState)
        assert ds.dominant_drive is not None

    def test_emergency_state(self, config: AgentConfig):
        engine = DriveEngine(config)
        state = np.zeros(STATE_VECTOR_DIM)
        state[0] = 0.99  # CPU critical
        ds = engine.compute(state, 0.1)
        assert ds.emergency is True
        assert ds.drives[DriveType.SAFETY].intensity == 1.0

    def test_steady_state(self, config: AgentConfig):
        engine = DriveEngine(config)
        state = np.random.rand(STATE_VECTOR_DIM)
        for _ in range(25):
            ds = engine.compute(state, 0.01)
        assert ds.steady_state is True


# =============================================================================
# 阶段9-10：预测模型测试
# =============================================================================

class TestPredictors:
    def test_gru_predictor(self, random_state: np.ndarray):
        gru = GRUPredictor(input_dim=STATE_VECTOR_DIM, hidden_dim=16)
        pred = gru.predict(random_state)
        assert isinstance(pred, Prediction)
        assert pred.value.shape == (STATE_VECTOR_DIM,)
        assert 0 <= pred.confidence <= 1

    def test_gru_online_update(self, random_state: np.ndarray):
        gru = GRUPredictor(input_dim=STATE_VECTOR_DIM, hidden_dim=16)
        next_state = random_state
        err = gru.update(random_state, next_state)
        assert isinstance(err, PredictionError)
        assert err.mse >= 0

    def test_ensemble_predictor(self, config: AgentConfig, random_state: np.ndarray):
        ensemble = EnsemblePredictor(config)
        pred = ensemble.predict(random_state)
        assert pred.value.shape == (STATE_VECTOR_DIM,)
        assert 0 <= pred.confidence <= 1

    def test_predictor_reset(self, random_state: np.ndarray):
        gru = GRUPredictor(input_dim=STATE_VECTOR_DIM, hidden_dim=16)
        gru.predict(random_state)
        gru.reset()
        # 重置后再次预测应正常
        pred = gru.predict(random_state)
        assert pred.value.shape == (STATE_VECTOR_DIM,)


# =============================================================================
# 阶段11：记忆系统测试
# =============================================================================

class TestMemory:
    def test_short_term_memory_store_retrieve(self, random_state: np.ndarray, tmp_path):
        mem = ShortTermMemory(max_size=100, db_path=str(tmp_path / "test_mem.db"))
        entry = MemoryEntry(id="test_1", content=random_state, value_score=0.5)
        mem.store(entry)
        retrieved = mem.retrieve("test_1")
        assert retrieved is not None
        assert np.allclose(retrieved.content, random_state)

    def test_memory_eviction(self, random_state: np.ndarray, tmp_path):
        mem = ShortTermMemory(max_size=5, db_path=str(tmp_path / "test_evict.db"))
        for i in range(10):
            entry = MemoryEntry(id=f"k{i}", content=random_state, value_score=float(i) / 10)
            mem.store(entry)
        # 超容量后低价值记忆应被淘汰
        assert len(mem._cache) <= 5


# =============================================================================
# 阶段12：任务生成测试
# =============================================================================

class TestTaskGenerator:
    def test_generate_tasks(self, config: AgentConfig, random_state: np.ndarray):
        engine = DriveEngine(config)
        ds = engine.compute(random_state, 0.1)
        gen = TaskGenerator()
        tasks = gen.generate(ds, random_state)
        assert isinstance(tasks, list)

    def test_safety_tasks_on_high_cpu(self, config: AgentConfig):
        gen = TaskGenerator()
        engine = DriveEngine(config)
        state = np.zeros(STATE_VECTOR_DIM)
        state[0] = 0.95
        ds = engine.compute(state, 0.1)
        tasks = gen.generate(ds, state)
        names = [t.name for t in tasks]
        assert "cpu_throttle" in names


# =============================================================================
# 阶段13：安全约束测试
# =============================================================================

class TestSafety:
    def test_resource_limiter_check(self, config: AgentConfig):
        limiter = ResourceLimiter(config)
        events = limiter.check()
        assert isinstance(events, list)

    def test_is_within_limits(self, config: AgentConfig):
        limiter = ResourceLimiter(config)
        assert isinstance(limiter.is_within_limits(), bool)


# =============================================================================
# 阶段14：接口实现检查
# =============================================================================

class TestInterfaceCompliance:
    def test_all_modules_implement_interfaces(self, config: AgentConfig, tmp_path):
        assert isinstance(SystemMonitor(), ISensor)
        assert isinstance(DriveEngine(config), IDriveEngine)
        assert isinstance(GRUPredictor(input_dim=STATE_VECTOR_DIM, hidden_dim=8), IPredictor)
        assert isinstance(EnsemblePredictor(config), IPredictor)
        assert isinstance(ShortTermMemory(max_size=10, db_path=str(tmp_path / "iface.db")), IMemory)
        assert isinstance(TaskGenerator(), ITaskGenerator)
        assert isinstance(ResourceLimiter(config), ISafetyMonitor)


# =============================================================================
# 阶段15：预测器reset接口测试
# =============================================================================

class TestReset:
    def test_all_predictors_support_reset(self, config: AgentConfig, random_state: np.ndarray):
        gru = GRUPredictor(input_dim=STATE_VECTOR_DIM, hidden_dim=8)
        ensemble = EnsemblePredictor(config)
        gru.predict(random_state)
        ensemble.predict(random_state)
        gru.reset()
        ensemble.reset()
        # 重置后预测应不抛异常
        gru.predict(random_state)
        ensemble.predict(random_state)


# =============================================================================
# 阶段16：端到端主流程测试
# =============================================================================

class TestEndToEnd:
    def test_single_step(self, config: AgentConfig, random_state: np.ndarray):
        sensor = SystemMonitor()
        drive = DriveEngine(config)
        ensemble = EnsemblePredictor(config)
        safety = ResourceLimiter(config)

        raw = sensor.read()
        vec = sensor.encode_to_vector(raw).feature_vector
        ds = drive.compute(vec, 0.05)
        pred = ensemble.predict(vec)
        tasks = TaskGenerator().generate(ds, vec)
        events = safety.check()

        assert vec.shape == (STATE_VECTOR_DIM,)
        assert pred.value.shape == (STATE_VECTOR_DIM,)
        assert isinstance(tasks, list)
        assert isinstance(events, list)

    def test_agent_dependency_injection(self, config: AgentConfig):
        # Mock 预测器
        class MockPredictor(IPredictor):
            def predict(self, state_vector: np.ndarray) -> Prediction:
                return Prediction(value=state_vector.copy(), confidence=1.0)
            def update(self, state_vector: np.ndarray, actual_next: np.ndarray) -> PredictionError:
                return PredictionError(mse=0.0, mae=0.0)
            def reset(self) -> None:
                pass

        agent = Agent(config=config, predictor=MockPredictor())
        assert agent.predictor is not None

    def test_agent_step_runs(self, config: AgentConfig):
        agent = Agent(config=config)
        result = agent.step()
        assert isinstance(result, dict)
        assert "running" in result or "error" in result
