"""
极端边界场景测试 —— 更高难度、更混乱的场景

针对系统在极端条件下的鲁棒性进行深度测试，发现隐藏的bug。

测试维度：
1. NaN/Inf 状态向量 —— 预测器/驱力引擎对非法数值的处理
2. 传感器异常 —— read()返回None / 抛出异常 / 返回错误格式
3. 并发step()调用 —— 多线程同时调用agent._step()
4. DB损坏/缺失 —— SQLite文件不存在或损坏时的容错
5. 超大值/超小值 —— 状态向量含极端值（1e30, -1e30, 1e-30）
6. 零向量/全一向量 —— 边界输入
7. 快速启停 —— 反复start/stop的竞态条件
8. 记忆系统满载 —— 超过max_size后的淘汰正确性
9. 长期记忆压缩 —— 大量相似向量的压缩效率
10. 任务生成器去重 —— 高频生成同名任务的去重
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
from typing import Any, List, Optional

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import (
    AgentConfig,
    MemoryEntry,
    MemoryType,
    TaskStatus,
    STATE_VECTOR_DIM,
    STATE_IDX_CPU_OVERALL,
    STATE_IDX_MEM_USED,
    STATE_IDX_DISK_USED,
)
from core.types import PerceptionInput, PerceptionOutput, PerceptionModality
from perception.sensor import Sensor


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors: List[str] = []

    def ok(self, name: str):
        self.passed += 1
        print(f"  [PASS] {name}")

    def fail(self, name: str, reason: str):
        self.failed += 1
        msg = f"{name}: {reason}"
        self.errors.append(msg)
        print(f"  [FAIL] {msg}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n  通过: {self.passed}, 失败: {self.failed}, 共{total}项")
        if self.errors:
            for e in self.errors:
                print(f"    - {e}")


# =============================================================================
# 极端传感器 —— 注入各种极端/非法状态向量
# =============================================================================

class ExtremeSensor(Sensor):
    """注入极端状态向量的传感器"""

    def __init__(self, vector_provider=None):
        super().__init__("extreme_sensor", PerceptionModality.SYSTEM)
        self._running = True
        self._vector_provider = vector_provider or (lambda: np.zeros(STATE_VECTOR_DIM, dtype=np.float32))
        self._call_count = 0

    def start(self): self._running = True
    def stop(self): self._running = False

    def read(self) -> Optional[PerceptionInput]:
        if not self._running:
            return None
        self._call_count += 1
        vec = self._vector_provider()
        if vec is None:
            return None
        raw = np.array(vec, dtype=np.float32).tobytes()
        return PerceptionInput(
            modality=self.modality,
            raw_data=raw,
            timestamp=time.time(),
            source_id=self.source_id,
            metadata={},
        )

    def encode_to_vector(self, input_data: PerceptionInput) -> PerceptionOutput:
        vec = np.frombuffer(input_data.raw_data, dtype=np.float32).copy()
        return PerceptionOutput(
            feature_vector=vec,
            modality=self.modality,
            timestamp=input_data.timestamp,
            source_id=self.source_id,
            confidence=1.0,
        )

    def update(self, state_vector):
        return {"anomaly_score": 0.0, "is_anomaly": False}


class ThrowingSensor(Sensor):
    """read()抛出异常的传感器"""

    def __init__(self):
        super().__init__("throwing_sensor", PerceptionModality.SYSTEM)
        self._running = True

    def start(self): self._running = True
    def stop(self): self._running = False

    def read(self) -> Optional[PerceptionInput]:
        raise RuntimeError("模拟传感器硬件故障")

    def encode_to_vector(self, input_data: PerceptionInput) -> PerceptionOutput:
        return PerceptionOutput(
            feature_vector=np.zeros(STATE_VECTOR_DIM),
            modality=self.modality,
            timestamp=time.time(),
            source_id=self.source_id,
        )

    def update(self, state_vector):
        return {"anomaly_score": 0.0, "is_anomaly": False}


class NoneSensor(Sensor):
    """read()返回None的传感器"""

    def __init__(self):
        super().__init__("none_sensor", PerceptionModality.SYSTEM)
        self._running = True

    def start(self): self._running = True
    def stop(self): self._running = False

    def read(self) -> Optional[PerceptionInput]:
        return None

    def encode_to_vector(self, input_data: PerceptionInput) -> PerceptionOutput:
        return PerceptionOutput(
            feature_vector=np.zeros(STATE_VECTOR_DIM),
            modality=self.modality,
            timestamp=time.time(),
            source_id=self.source_id,
        )

    def update(self, state_vector):
        return {"anomaly_score": 0.0, "is_anomaly": False}


# =============================================================================
# 测试用例
# =============================================================================

def test_nan_inf_state_vector(result: TestResult):
    """测试1: NaN/Inf状态向量"""
    print(f"\n  --- 测试1: NaN/Inf状态向量 ---")

    tmp_dir = tempfile.mkdtemp(prefix="nan_test_")
    try:
        from agent import SelfEvolvingAgent
        from memory import ShortTermMemory

        # NaN向量
        nan_vec = np.zeros(STATE_VECTOR_DIM, dtype=np.float32)
        nan_vec[STATE_IDX_CPU_OVERALL] = np.nan
        nan_vec[STATE_IDX_MEM_USED] = np.inf

        sensor = ExtremeSensor(vector_provider=lambda: nan_vec)
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        mem = ShortTermMemory(max_size=100, db_path=os.path.join(tmp_dir, "nan.db"))

        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[sensor])

        # 运行10步，验证不崩溃
        crashed = False
        error_msg = ""
        for i in range(10):
            try:
                agent._step()
                agent.step_count += 1
            except Exception as e:
                crashed = True
                error_msg = f"{type(e).__name__}: {e}"
                break

        if not crashed:
            result.ok(f"NaN/Inf向量未导致崩溃 (10步完成)")
        else:
            result.fail("NaN/Inf崩溃", error_msg)

        # 验证预测误差不含NaN（如果有NaN会污染后续计算）
        if agent.prediction_error_history:
            has_nan = any(np.isnan(e) or np.isinf(e) for e in agent.prediction_error_history)
            if not has_nan:
                result.ok(f"预测误差无NaN/Inf污染")
            else:
                result.fail("预测误差被NaN污染", f"history={agent.prediction_error_history[:5]}")
        else:
            result.ok("预测误差历史为空（首步无误差）")

        agent.stop()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_throwing_sensor(result: TestResult):
    """测试2: 传感器抛异常"""
    print(f"\n  --- 测试2: 传感器抛异常 ---")

    tmp_dir = tempfile.mkdtemp(prefix="throw_test_")
    try:
        from agent import SelfEvolvingAgent
        from memory import ShortTermMemory

        sensor = ThrowingSensor()
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        mem = ShortTermMemory(max_size=100, db_path=os.path.join(tmp_dir, "throw.db"))

        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[sensor])

        crashed = False
        for i in range(10):
            try:
                agent._step()
                agent.step_count += 1
            except Exception:
                crashed = True
                break

        # 传感器异常应被agent._step()的try/except捕获，不应崩溃
        if not crashed:
            result.ok(f"传感器异常被正确捕获 (10步完成)")
        else:
            result.fail("传感器异常导致崩溃", "异常未被捕获")

        agent.stop()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_none_sensor(result: TestResult):
    """测试3: 传感器返回None"""
    print(f"\n  --- 测试3: 传感器返回None ---")

    tmp_dir = tempfile.mkdtemp(prefix="none_test_")
    try:
        from agent import SelfEvolvingAgent
        from memory import ShortTermMemory

        sensor = NoneSensor()
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        mem = ShortTermMemory(max_size=100, db_path=os.path.join(tmp_dir, "none.db"))

        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[sensor])

        crashed = False
        for i in range(10):
            try:
                agent._step()
                agent.step_count += 1
            except Exception as e:
                crashed = True
                break

        # None传感器应被正确处理（state_vector为None时直接return）
        if not crashed:
            result.ok(f"None传感器被正确处理 (10步完成)")
        else:
            result.fail("None传感器导致崩溃", "异常")

        agent.stop()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_concurrent_step(result: TestResult):
    """测试4: 并发step()调用"""
    print(f"\n  --- 测试4: 并发step()调用 ---")

    tmp_dir = tempfile.mkdtemp(prefix="conc_test_")
    try:
        from agent import SelfEvolvingAgent
        from memory import ShortTermMemory

        normal_vec = np.random.rand(STATE_VECTOR_DIM).astype(np.float32) * 0.5
        sensor = ExtremeSensor(vector_provider=lambda: normal_vec.copy())
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        mem = ShortTermMemory(max_size=10000, db_path=os.path.join(tmp_dir, "conc.db"))

        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[sensor])

        errors = []
        num_threads = 4
        steps_per_thread = 50

        def worker():
            for _ in range(steps_per_thread):
                try:
                    agent._step()
                    agent.step_count += 1
                except Exception as e:
                    errors.append(f"{type(e).__name__}: {e}")

        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        total_expected = num_threads * steps_per_thread
        if len(errors) == 0:
            result.ok(f"并发step()无异常 ({total_expected}次调用)")
        else:
            result.fail("并发step()异常", f"{len(errors)}个错误: {errors[0]}")

        # 验证step_count正确（可能有竞态，但应接近预期值）
        if agent.step_count > 0:
            result.ok(f"step_count > 0 (实际={agent.step_count})")
        else:
            result.fail("step_count为0", "并发执行失败")

        agent.stop()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_missing_db(result: TestResult):
    """测试5: DB文件不存在时的初始化"""
    print(f"\n  --- 测试5: DB文件不存在 ---")

    tmp_dir = tempfile.mkdtemp(prefix="missing_db_")
    try:
        from memory import ShortTermMemory

        db_path = os.path.join(tmp_dir, "nonexistent", "subdir", "memory.db")
        # 父目录不存在，ShortTermMemory应自动创建
        mem = ShortTermMemory(max_size=100, db_path=db_path)

        # 存储一条记忆
        entry = MemoryEntry(
            content="test",
            memory_type=MemoryType.EPISODIC,
            value_score=0.5,
        )
        mem.store(entry)

        if len(mem) == 1:
            result.ok(f"DB自动创建并存储成功")
        else:
            result.fail("DB创建失败", f"len={len(mem)}")

        # 验证可检索
        retrieved = mem.retrieve(entry.id)
        if retrieved is not None:
            result.ok(f"DB检索成功")
        else:
            result.fail("DB检索失败", "未找到刚存储的entry")

        mem.clear()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_extreme_values(result: TestResult):
    """测试6: 超大/超小值"""
    print(f"\n  --- 测试6: 超大/超小值 ---")

    tmp_dir = tempfile.mkdtemp(prefix="extreme_val_")
    try:
        from agent import SelfEvolvingAgent
        from memory import ShortTermMemory

        # 超大值向量
        extreme_vec = np.full(STATE_VECTOR_DIM, 1e30, dtype=np.float32)
        extreme_vec[0] = -1e30
        extreme_vec[1] = 1e-30

        sensor = ExtremeSensor(vector_provider=lambda: extreme_vec.copy())
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        mem = ShortTermMemory(max_size=100, db_path=os.path.join(tmp_dir, "extreme.db"))

        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[sensor])

        crashed = False
        for i in range(5):
            try:
                agent._step()
                agent.step_count += 1
            except Exception as e:
                crashed = True
                break

        if not crashed:
            result.ok(f"超大/超小值未导致崩溃 (5步完成)")
        else:
            result.fail("超大值崩溃", "异常")

        agent.stop()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_rapid_start_stop(result: TestResult):
    """测试7: 快速启停"""
    print(f"\n  --- 测试7: 快速启停 ---")

    tmp_dir = tempfile.mkdtemp(prefix="startstop_")
    try:
        from agent import SelfEvolvingAgent
        from memory import ShortTermMemory

        normal_vec = np.random.rand(STATE_VECTOR_DIM).astype(np.float32) * 0.3
        sensor = ExtremeSensor(vector_provider=lambda: normal_vec.copy())
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        mem = ShortTermMemory(max_size=100, db_path=os.path.join(tmp_dir, "ss.db"))

        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[sensor])

        # 反复start/stop
        errors = []
        for i in range(20):
            try:
                agent.running = True
                agent.event_bus.start()
                for s in agent.sensors:
                    if hasattr(s, 'start'):
                        s.start()
                agent.safety_monitor.start()
                # 执行几步
                for _ in range(3):
                    agent._step()
                    agent.step_count += 1
                agent.stop()
            except Exception as e:
                errors.append(f"iter {i}: {type(e).__name__}: {e}")

        if len(errors) == 0:
            result.ok(f"快速启停无异常 (20次循环)")
        else:
            result.fail("快速启停异常", f"{len(errors)}个错误: {errors[0]}")

        if agent.step_count > 0:
            result.ok(f"启停后step_count > 0 (={agent.step_count})")
        else:
            result.fail("step_count为0", "启停后无有效步数")
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_memory_eviction_correctness(result: TestResult):
    """测试8: 记忆淘汰正确性"""
    print(f"\n  --- 测试8: 记忆淘汰正确性 ---")

    tmp_dir = tempfile.mkdtemp(prefix="evict_")
    try:
        from memory import ShortTermMemory

        mem = ShortTermMemory(max_size=10, db_path=os.path.join(tmp_dir, "evict.db"))

        # 存储20条记忆（超过max_size=10）
        stored_ids = []
        for i in range(20):
            entry = MemoryEntry(
                content=f"item_{i}",
                memory_type=MemoryType.EPISODIC,
                value_score=i * 0.05,  # 递增价值
                tags=[f"tag_{i}"],
            )
            mem.store(entry)
            stored_ids.append(entry.id)

        # 验证缓存大小不超过max_size
        if len(mem) == 10:
            result.ok(f"淘汰后大小正确 (10 == max_size)")
        else:
            result.fail("淘汰后大小错误", f"len={len(mem)}, 期望10")

        # 验证淘汰的是低价值记忆（value_score最低的被淘汰）
        # 存入的value_score: 0, 0.05, 0.10, ..., 0.95
        # 淘汰后应保留value_score最高的10个: 0.50 ~ 0.95
        remaining = []
        for eid in stored_ids:
            entry = mem.retrieve(eid)
            if entry is not None:
                remaining.append(entry.value_score)

        if len(remaining) == 10:
            min_remaining = min(remaining)
            if min_remaining >= 0.45:  # 应保留高价值的
                result.ok(f"淘汰了低价值记忆 (min_remaining={min_remaining:.2f})")
            else:
                result.fail("淘汰了高价值记忆", f"min_remaining={min_remaining:.2f}")
        else:
            result.fail("剩余数量错误", f"remaining={len(remaining)}, 期望10")

        mem.clear()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_ltm_compress(result: TestResult):
    """测试9: 长期记忆压缩"""
    print(f"\n  --- 测试9: 长期记忆压缩 ---")

    tmp_dir = tempfile.mkdtemp(prefix="compress_")
    try:
        from memory.long_term_memory import LongTermMemory

        ltm = LongTermMemory(db_path=os.path.join(tmp_dir, "compress.db"))

        # 存储20条高度相似的记忆（应被压缩）
        base_vec = np.random.rand(28).astype(np.float32)
        for i in range(20):
            # 添加微小扰动
            noisy_vec = base_vec + np.random.randn(28).astype(np.float32) * 0.001
            entry = MemoryEntry(
                content=noisy_vec,
                memory_type=MemoryType.EPISODIC,
                value_score=0.8,
            )
            ltm.store(entry)

        count_before = ltm.count()
        print(f"    压缩前: {count_before}条")

        # 执行压缩（threshold=0.95，高度相似的会被删除）
        deleted = ltm.compress(threshold=0.95)
        count_after = ltm.count()
        print(f"    压缩后: {count_after}条, 删除{deleted}条")

        if deleted > 0:
            result.ok(f"压缩生效 (删除{deleted}条冗余)")
        else:
            result.fail("压缩未生效", "未删除任何冗余记忆")

        if count_after < count_before:
            result.ok(f"压缩后数量减少 ({count_before} -> {count_after})")
        else:
            result.fail("压缩后数量未减少", f"{count_before} -> {count_after}")

    except Exception as e:
        result.fail("压缩异常", f"{type(e).__name__}: {e}")
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_task_dedup(result: TestResult):
    """测试10: 任务生成器去重"""
    print(f"\n  --- 测试10: 任务生成器去重 ---")

    try:
        from task import TaskGenerator
        from core import DriveType, Drive, DriveState

        tg = TaskGenerator()

        # 构造一个会触发安全任务的驱力状态
        drive = Drive(
            drive_type=DriveType.SAFETY,
            intensity=0.8,
            priority=1,
        )
        drive_state = DriveState(
            drives={DriveType.SAFETY: drive},
            weights={DriveType.SAFETY: 1.0},
        )

        # 构造高CPU状态向量
        state_vec = np.zeros(STATE_VECTOR_DIM, dtype=np.float32)
        state_vec[STATE_IDX_CPU_OVERALL] = 0.99  # CPU > 0.9 触发cpu_throttle任务

        # 第一次生成
        tasks1 = tg.generate(drive_state, state_vec)
        # 第二次生成（应被去重）
        tasks2 = tg.generate(drive_state, state_vec)
        # 第三次
        tasks3 = tg.generate(drive_state, state_vec)

        if len(tasks1) > 0:
            result.ok(f"首次生成任务成功 ({len(tasks1)}个)")
        else:
            result.fail("首次生成失败", "未生成任何任务")

        if len(tasks2) == 0:
            result.ok(f"重复任务被去重 (第2次返回0个)")
        else:
            result.fail("去重失效", f"第2次返回{len(tasks2)}个重复任务")

        if len(tasks3) == 0:
            result.ok(f"重复任务被去重 (第3次返回0个)")
        else:
            result.fail("去重失效", f"第3次返回{len(tasks3)}个重复任务")

        # 完成任务后，再次生成应能生成新任务
        if tasks1:
            tg.complete_task(tasks1[0].id, reward=0.5)
            tasks4 = tg.generate(drive_state, state_vec)
            if len(tasks4) > 0:
                result.ok(f"完成后可重新生成 ({len(tasks4)}个)")
            else:
                result.fail("完成后无法重新生成", "去重逻辑未正确清除")

    except Exception as e:
        result.fail("去重测试异常", f"{type(e).__name__}: {e}")


def test_drive_engine_emergency_recovery(result: TestResult):
    """测试11: 驱力引擎紧急状态恢复"""
    print(f"\n  --- 测试11: 驱力引擎紧急状态恢复 ---")

    try:
        from drive import DriveEngine

        # 使用自定义权重（验证_smooth_weights不硬编码）
        engine = DriveEngine(
            config_or_safety_weight=0.6,  # 自定义安全权重
            gain_weight=0.3,
            efficiency_weight=0.1,
        )

        # 正常状态
        normal_vec = np.zeros(STATE_VECTOR_DIM, dtype=np.float32)
        normal_vec[STATE_IDX_CPU_OVERALL] = 0.3
        normal_vec[STATE_IDX_MEM_USED] = 0.4
        normal_vec[STATE_IDX_DISK_USED] = 0.5

        state1 = engine.compute(normal_vec, prediction_error=0.1)
        w1 = engine.weights.copy()

        # 紧急状态（CPU > 0.95）
        emergency_vec = normal_vec.copy()
        emergency_vec[STATE_IDX_CPU_OVERALL] = 0.99
        state2 = engine.compute(emergency_vec, prediction_error=0.1)
        w2 = engine.weights.copy()

        if state2.emergency:
            result.ok(f"紧急状态正确检测")
        else:
            result.fail("紧急状态未检测", "emergency=False")

        # 紧急时安全权重应为0.9
        from core import DriveType
        if w2.get(DriveType.SAFETY, 0) >= 0.8:  # safety weight high
            result.ok(f"紧急时安全权重提升")
        else:
            result.fail("紧急权重错误", f"weights={w2}")

        # 恢复正常状态，权重应平滑恢复到用户配置
        for _ in range(20):
            state3 = engine.compute(normal_vec, prediction_error=0.1)

        w3 = engine.weights.copy()
        safety_w = w3.get(DriveType.SAFETY, 0)

        # 权重应向用户配置(0.6/0.3/0.1)收敛，而非硬编码(0.4/0.4/0.2)
        if 0.5 < safety_w < 0.7:
            result.ok(f"权重恢复到用户配置 (safety={safety_w:.3f}, 目标=0.6)")
        elif 0.35 < safety_w < 0.45:
            result.fail("权重恢复到硬编码值", f"safety={safety_w:.3f} (接近0.4而非0.6)")
        else:
            result.warn("权重恢复", f"safety={safety_w:.3f} (未明确收敛)")

    except Exception as e:
        result.fail("驱力恢复测试异常", f"{type(e).__name__}: {e}")


def test_long_run_stability(result: TestResult, steps: int = 1000):
    """测试12: 长时间运行稳定性（1000步）"""
    print(f"\n  --- 测试12: 长时间运行稳定性 ({steps}步) ---")

    tmp_dir = tempfile.mkdtemp(prefix="longrun_")
    try:
        from agent import SelfEvolvingAgent
        from memory import ShortTermMemory

        # 混合正常和异常向量
        counter = [0]
        def mixed_vector():
            counter[0] += 1
            if counter[0] % 50 == 0:
                # 每50步注入一次异常
                v = np.zeros(STATE_VECTOR_DIM, dtype=np.float32)
                v[STATE_IDX_CPU_OVERALL] = 0.99
                v[STATE_IDX_MEM_USED] = 0.95
                return v
            else:
                v = np.random.rand(STATE_VECTOR_DIM).astype(np.float32) * 0.4
                return v

        sensor = ExtremeSensor(vector_provider=mixed_vector)
        config = AgentConfig()
        config.main_loop_interval_ms = 0
        config.short_term_memory_size = 200
        mem = ShortTermMemory(max_size=200, db_path=os.path.join(tmp_dir, "longrun.db"))

        agent = SelfEvolvingAgent(config=config, memory=mem, sensors=[sensor])

        errors = []
        t0 = time.time()
        for i in range(steps):
            try:
                agent._step()
                agent.step_count += 1
            except Exception as e:
                errors.append(f"Step {i}: {type(e).__name__}: {e}")
                if len(errors) > 10:
                    break

        elapsed = time.time() - t0

        if agent.step_count == steps:
            result.ok(f"全部{steps}步完成 (耗时{elapsed:.1f}s)")
        else:
            result.fail("步数不完整", f"期望{steps}, 实际{agent.step_count}")

        if len(errors) == 0:
            result.ok(f"零异常运行 ({steps}步)")
        else:
            result.fail("运行异常", f"{len(errors)}个错误, 首个: {errors[0]}")

        # 验证性能稳定（平均每步 < 50ms）
        avg_per_step_ms = (elapsed / max(agent.step_count, 1)) * 1000
        if avg_per_step_ms < 50:
            result.ok(f"性能稳定 (avg={avg_per_step_ms:.2f}ms/step < 50ms)")
        else:
            result.warn("性能偏高", f"avg={avg_per_step_ms:.2f}ms/step")

        # 验证记忆系统未溢出
        if len(mem) <= 200:
            result.ok(f"记忆系统受控 (len={len(mem)} <= 200)")
        else:
            result.fail("记忆系统溢出", f"len={len(mem)} > 200")

        # 验证优化器触发
        if agent._optimization_count > 0:
            result.ok(f"离线优化触发 (count={agent._optimization_count})")
        else:
            result.warn("离线优化未触发", "可能replay_buffer不足")

        agent.stop()
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    print("\n" + "=" * 60)
    print("  极端边界场景测试 —— 更高难度、更混乱")
    print("=" * 60)

    result = TestResult()

    test_nan_inf_state_vector(result)
    test_throwing_sensor(result)
    test_none_sensor(result)
    test_concurrent_step(result)
    test_missing_db(result)
    test_extreme_values(result)
    test_rapid_start_stop(result)
    test_memory_eviction_correctness(result)
    test_ltm_compress(result)
    test_task_dedup(result)
    test_drive_engine_emergency_recovery(result)
    test_long_run_stability(result, steps=1000)

    print("\n" + "=" * 60)
    result.summary()
    print("=" * 60)

    return 0 if result.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
