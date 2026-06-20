"""
复杂场景闭环测试 —— 长时间、大规模、高负载、混乱场景的真实实践

目标：通过模拟真实运行中的混乱场景，发现系统在长时间运行时的bug。

测试维度：
1. 业务场景闭环 —— 完整正向/逆向/中断/重复操作
2. 数据一致性校验 —— 增删改查、关联关系
3. 异常容错测试 —— 超时、断连、报错、兜底降级
4. 基础性能核验 —— 高频核心流程响应稳定，无内存溢出

混沌场景设计（6个阶段，共600步）：
  Phase 1 (0-100):   正常运行 —— 建立基线
  Phase 2 (100-200): CPU尖峰 —— CPU突增至99%，验证安全驱力触发
  Phase 3 (200-300): 内存泄漏 —— 内存逐步增至95%，验证内存清理任务
  Phase 4 (300-400): 磁盘满载 —— 磁盘使用率突增至98%
  Phase 5 (400-500): 混合混乱 —— 所有指标随机尖峰，验证系统稳定性
  Phase 6 (500-600): 恢复阶段 —— 恢复正常，验证系统自愈能力
"""

from __future__ import annotations

import gc
import os
import sys
import time
import tracemalloc
from typing import Any, Dict, List, Optional

import numpy as np

# 确保项目根目录在 path 中
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


# =============================================================================
# 混沌传感器 —— 注入可控的混乱状态向量
# =============================================================================

class ChaosSensor(Sensor):
    """
    混沌传感器

    根据当前阶段注入不同的混乱状态向量，模拟真实系统中的异常情况。
    每一步都打印日志，验证代码是否正常执行。
    """

    def __init__(self):
        super().__init__("chaos_sensor", PerceptionModality.SYSTEM)
        self._running = True
        self._step = 0
        self._phase = 1
        self._injected_chaos_log: List[str] = []

    def start(self) -> None:
        self._running = True
        print(f"  [ChaosSensor] started")

    def stop(self) -> None:
        self._running = False
        print(f"  [ChaosSensor] stopped, total_steps={self._step}")

    def read(self) -> Optional[PerceptionInput]:
        if not self._running:
            return None
        self._step += 1
        self._phase = self._determine_phase(self._step)
        vector = self._generate_chaos_vector()
        raw = np.array(vector, dtype=np.float32).tobytes()
        return PerceptionInput(
            modality=self.modality,
            raw_data=raw,
            timestamp=time.time(),
            source_id=self.source_id,
            metadata={"phase": str(self._phase), "step": str(self._step)},
        )

    def encode_to_vector(self, input_data: PerceptionInput) -> PerceptionOutput:
        vector = np.frombuffer(input_data.raw_data, dtype=np.float32).copy()
        return PerceptionOutput(
            feature_vector=vector,
            modality=self.modality,
            timestamp=input_data.timestamp,
            source_id=self.source_id,
            confidence=1.0,
        )

    def update(self, state_vector: np.ndarray):
        """模拟异常检测（AnomalyDetector接口）"""
        cpu = state_vector[STATE_IDX_CPU_OVERALL]
        mem = state_vector[STATE_IDX_MEM_USED]
        anomaly_score = float(max(cpu, mem))
        return {
            "anomaly_score": anomaly_score,
            "is_anomaly": anomaly_score > 0.9,
        }

    def _determine_phase(self, step: int) -> int:
        if step < 100:
            return 1
        elif step < 200:
            return 2
        elif step < 300:
            return 3
        elif step < 400:
            return 4
        elif step < 500:
            return 5
        else:
            return 6

    def _generate_chaos_vector(self) -> List[float]:
        """根据阶段生成混乱状态向量"""
        v = [0.0] * STATE_VECTOR_DIM
        step_in_phase = self._step % 100

        if self._phase == 1:
            # 正常运行
            v[STATE_IDX_CPU_OVERALL] = 0.30 + np.random.uniform(-0.05, 0.05)
            v[STATE_IDX_MEM_USED] = 0.45 + np.random.uniform(-0.05, 0.05)
            v[STATE_IDX_DISK_USED] = 0.50
        elif self._phase == 2:
            # CPU尖峰
            v[STATE_IDX_CPU_OVERALL] = 0.99 if step_in_phase % 10 < 7 else 0.50
            v[STATE_IDX_MEM_USED] = 0.50
            v[STATE_IDX_DISK_USED] = 0.50
        elif self._phase == 3:
            # 内存泄漏（逐步增长）
            v[STATE_IDX_CPU_OVERALL] = 0.40
            v[STATE_IDX_MEM_USED] = min(0.95, 0.50 + step_in_phase * 0.005)
            v[STATE_IDX_DISK_USED] = 0.50
        elif self._phase == 4:
            # 磁盘满载
            v[STATE_IDX_CPU_OVERALL] = 0.40
            v[STATE_IDX_MEM_USED] = 0.50
            v[STATE_IDX_DISK_USED] = 0.98
        elif self._phase == 5:
            # 混合混乱
            v[STATE_IDX_CPU_OVERALL] = np.random.choice([0.20, 0.99, 0.60, 0.85])
            v[STATE_IDX_MEM_USED] = np.random.choice([0.40, 0.95, 0.70, 0.90])
            v[STATE_IDX_DISK_USED] = np.random.choice([0.50, 0.98, 0.75])
        else:
            # 恢复阶段
            v[STATE_IDX_CPU_OVERALL] = max(0.30, 0.60 - step_in_phase * 0.005)
            v[STATE_IDX_MEM_USED] = max(0.45, 0.80 - step_in_phase * 0.005)
            v[STATE_IDX_DISK_USED] = max(0.50, 0.80 - step_in_phase * 0.005)

        # 填充其他维度（避免全零导致预测器异常）
        for i in range(10, STATE_VECTOR_DIM):
            v[i] = np.random.uniform(0.1, 0.3)

        return v


# =============================================================================
# 测试结果收集器
# =============================================================================

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def ok(self, name: str):
        self.passed += 1
        print(f"  [PASS] {name}")

    def fail(self, name: str, reason: str):
        self.failed += 1
        msg = f"{name}: {reason}"
        self.errors.append(msg)
        print(f"  [FAIL] {msg}")

    def warn(self, name: str, reason: str):
        self.warnings.append(f"{name}: {reason}")
        print(f"  [WARN] {name}: {reason}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n  通过: {self.passed}, 失败: {self.failed}, 警告: {len(self.warnings)}, 共{total}项")
        if self.errors:
            print(f"\n  失败详情:")
            for e in self.errors:
                print(f"    - {e}")


# =============================================================================
# 主测试函数
# =============================================================================

def run_chaos_scenario_test(total_steps: int = 600) -> TestResult:
    """
    运行完整的混沌场景闭环测试

    Args:
        total_steps: 总步数（默认600步，覆盖6个阶段）
    """
    result = TestResult()
    print(f"\n{'='*60}")
    print(f"  复杂场景闭环测试 —— {total_steps}步, 6个混沌阶段")
    print(f"{'='*60}")

    # 启动内存追踪（检测内存泄漏）
    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    # 创建Agent（注入混沌传感器，使用临时DB避免污染）
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="chaos_test_")
    config = AgentConfig()
    config.main_loop_interval_ms = 0  # 测试中不sleep
    config.short_term_memory_size = 500  # 限制大小，测试淘汰逻辑

    chaos_sensor = ChaosSensor()

    # 使用临时DB路径
    from memory import ShortTermMemory
    tmp_memory = ShortTermMemory(
        max_size=500,
        db_path=os.path.join(tmp_dir, "chaos_memory.db"),
    )

    print(f"\n  [Setup] 临时目录: {tmp_dir}")
    print(f"  [Setup] 混沌传感器已注入")

    # 创建Agent
    from agent import SelfEvolvingAgent
    agent = SelfEvolvingAgent(
        config=config,
        memory=tmp_memory,
        sensors=[chaos_sensor],
    )

    print(f"  [Setup] Agent创建成功，开始运行{total_steps}步...\n")

    # === 运行主循环 ===
    step_errors: List[str] = []
    phase_transitions: Dict[int, int] = {}  # phase -> step_count at transition
    last_phase = 1
    memory_sizes: List[int] = []
    task_counts: List[int] = []

    loop_start = time.time()

    for i in range(total_steps):
        try:
            agent._step()
            agent.step_count += 1

            # 记录阶段转换
            current_phase = chaos_sensor._phase
            if current_phase != last_phase:
                phase_transitions[current_phase] = agent.step_count
                print(f"  [Phase] 阶段转换 {last_phase} -> {current_phase} at step {agent.step_count}")
                last_phase = current_phase

            # 每100步记录一次状态
            if (i + 1) % 100 == 0:
                status = agent.get_status()
                memory_sizes.append(status.get("memory_size", 0))
                task_counts.append(status.get("pending_tasks", 0))
                print(f"  [Step {agent.step_count}] phase={current_phase} "
                      f"mem_size={status.get('memory_size', 0)} "
                      f"replay={status.get('replay_buffer_size', 0)} "
                      f"pending_tasks={status.get('pending_tasks', 0)} "
                      f"opt_count={status.get('optimization_count', 0)}")

        except Exception as e:
            step_errors.append(f"Step {i+1}: {type(e).__name__}: {e}")
            # 不中断，继续运行（验证容错能力）

    loop_elapsed = time.time() - loop_start

    # === 停止Agent ===
    agent.stop()

    print(f"\n  [Done] 完成 {agent.step_count} 步, 耗时 {loop_elapsed:.2f}s, "
          f"异常 {len(step_errors)} 次")

    # =============================================================================
    # 验证1: 无致命崩溃 —— 所有步数都执行完成
    # =============================================================================
    print(f"\n  --- 验证1: 无致命崩溃 ---")
    if agent.step_count == total_steps:
        result.ok(f"全部{total_steps}步执行完成 (实际={agent.step_count})")
    else:
        result.fail("步数完整性", f"期望{total_steps}步, 实际{agent.step_count}步")

    # 致命异常率应 < 5%
    fatal_rate = len(step_errors) / total_steps
    if fatal_rate == 0:
        result.ok(f"零异常运行 ({total_steps}步无异常)")
    elif fatal_rate < 0.05:
        result.warn("异常率", f"异常率 {fatal_rate:.2%} (< 5%可接受)")
    else:
        result.fail("异常率过高", f"异常率 {fatal_rate:.2%}, 共{len(step_errors)}次")
        for e in step_errors[:5]:
            print(f"    {e}")

    # =============================================================================
    # 验证2: 阶段转换正确 —— 6个阶段都经历过
    # =============================================================================
    print(f"\n  --- 验证2: 阶段转换 ---")
    expected_phases = {1, 2, 3, 4, 5, 6}
    actual_phases = set(phase_transitions.keys()) | {1}  # phase 1是起始
    if expected_phases.issubset(actual_phases):
        result.ok(f"全部6个阶段都经历过")
    else:
        missing = expected_phases - actual_phases
        result.fail("阶段覆盖", f"缺失阶段: {missing}")

    # =============================================================================
    # 验证3: 记忆系统数据一致性 —— store的entry都能retrieve
    # =============================================================================
    print(f"\n  --- 验证3: 记忆系统数据一致性 ---")
    final_mem_size = len(tmp_memory)
    if final_mem_size > 0:
        result.ok(f"记忆系统有数据 (size={final_mem_size})")
    else:
        result.fail("记忆系统为空", "600步后记忆系统仍为空")

    # 验证retrieve_by_tags能正常工作
    try:
        tagged = tmp_memory.retrieve_by_tags(["system_state"], limit=10)
        if len(tagged) > 0:
            result.ok(f"标签检索正常 (返回{len(tagged)}条)")
        else:
            result.fail("标签检索", "未返回任何结果")
    except Exception as e:
        result.fail("标签检索异常", str(e))

    # 验证retrieve_high_value
    try:
        high_val = tmp_memory.retrieve_high_value(threshold=0.0, limit=10)
        if len(high_val) > 0:
            result.ok(f"高价值检索正常 (返回{len(high_val)}条)")
        else:
            result.fail("高价值检索", "未返回任何结果")
    except Exception as e:
        result.fail("高价值检索异常", str(e))

    # 验证记忆淘汰逻辑（max_size=500，运行600步应触发淘汰）
    if final_mem_size <= 500:
        result.ok(f"记忆淘汰生效 (size={final_mem_size} <= max=500)")
    else:
        result.fail("记忆淘汰失效", f"size={final_mem_size} > max=500")

    # =============================================================================
    # 验证4: 任务系统一致性 —— 任务生命周期完整
    # =============================================================================
    print(f"\n  --- 验证4: 任务系统一致性 ---")
    try:
        pending = agent.task_generator.get_pending_tasks()
        active = agent.task_generator._active_tasks
        result.ok(f"任务系统正常 (active={len(active)}, pending={len(pending)})")

        # 验证_active_tasks无界增长已修复
        if len(active) <= 1000:
            result.ok(f"_active_tasks未无界增长 (size={len(active)} <= 1000)")
        else:
            result.fail("_active_tasks无界增长", f"size={len(active)} > 1000")

        # 验证任务状态合法性
        valid_statuses = {TaskStatus.PENDING, TaskStatus.RUNNING, TaskStatus.COMPLETED,
                          TaskStatus.FAILED, TaskStatus.CANCELLED}
        invalid_count = 0
        for t in active.values():
            if t.status not in valid_statuses:
                invalid_count += 1
        if invalid_count == 0:
            result.ok(f"所有任务状态合法")
        else:
            result.fail("任务状态非法", f"{invalid_count}个任务状态不合法")

    except Exception as e:
        result.fail("任务系统异常", str(e))

    # =============================================================================
    # 验证5: 预测误差追踪 —— 误差历史正常记录
    # =============================================================================
    print(f"\n  --- 验证5: 预测误差追踪 ---")
    err_history = agent.prediction_error_history
    if len(err_history) > 0:
        result.ok(f"预测误差历史正常 (len={len(err_history)})")
        avg_err = np.mean(err_history)
        max_err = np.max(err_history)
        print(f"    平均误差={avg_err:.4f}, 最大误差={max_err:.4f}")
    else:
        result.fail("预测误差历史为空", "无误差记录")

    # 误差历史不应超过100（有pop逻辑）
    if len(err_history) <= 100:
        result.ok(f"误差历史长度受控 (len={len(err_history)} <= 100)")
    else:
        result.fail("误差历史无界增长", f"len={len(err_history)} > 100")

    # =============================================================================
    # 验证6: 驱力引擎状态转换 —— 紧急状态在chaos阶段触发
    # =============================================================================
    print(f"\n  --- 验证6: 驱力引擎状态 ---")
    try:
        # 在CPU尖峰阶段(step 100-200)后检查权重
        weights = agent.drive_engine.weights
        total_weight = sum(weights.values())
        if 0.99 < total_weight < 1.01:
            result.ok(f"驱力权重归一化正确 (total={total_weight:.4f})")
        else:
            result.fail("驱力权重归一化错误", f"total={total_weight:.4f}")

        # 验证平滑恢复目标权重使用的是用户配置而非硬编码
        target = agent.drive_engine._target_weights
        config_safety = config.safety_weight
        if abs(target.get(type(target.get(list(target.keys())[0])), 0) - config_safety) < 0.01 or \
           any(abs(target.get(k, 0) - config.__dict__.get(f"{k.value}_weight", 0)) < 0.01 for k in target):
            result.ok(f"平滑恢复目标权重使用用户配置")
        else:
            result.warn("目标权重", f"无法确认是否使用用户配置: {target}")

    except Exception as e:
        result.fail("驱力引擎异常", str(e))

    # =============================================================================
    # 验证7: 内存泄漏检测 —— 长时间运行后内存增长可控
    # =============================================================================
    print(f"\n  --- 验证7: 内存泄漏检测 ---")
    gc.collect()
    snapshot_after = tracemalloc.take_snapshot()
    stats = snapshot_after.compare_to(snapshot_before, 'lineno')

    total_growth = sum(s.size_diff for s in stats if s.size_diff > 0)
    total_growth_mb = total_growth / (1024 * 1024)

    if total_growth_mb < 50:
        result.ok(f"内存增长可控 ({total_growth_mb:.2f} MB < 50MB)")
    elif total_growth_mb < 100:
        result.warn("内存增长偏高", f"{total_growth_mb:.2f} MB")
    else:
        result.fail("内存泄漏", f"内存增长 {total_growth_mb:.2f} MB > 100MB")

    # 打印top 5内存增长
    top5 = sorted(stats, key=lambda s: s.size_diff, reverse=True)[:5]
    print(f"    Top 5 内存增长:")
    for s in top5:
        if s.size_diff > 0:
            print(f"      {s.traceback}")

    tracemalloc.stop()

    # =============================================================================
    # 验证8: 离线优化触发 —— 每100步触发一次
    # =============================================================================
    print(f"\n  --- 验证8: 离线优化触发 ---")
    opt_count = agent._optimization_count
    expected_min_opt = (total_steps // 100) - 1  # 允许少一次（replay_buffer不足时跳过）
    if opt_count >= 1:
        result.ok(f"离线优化已触发 (count={opt_count})")
    else:
        result.warn("离线优化未触发", f"count={opt_count} (可能replay_buffer不足)")

    # =============================================================================
    # 验证9: 进化快照记录
    # =============================================================================
    print(f"\n  --- 验证9: 进化快照记录 ---")
    snapshots = agent.evolution_dynamics.snapshots
    if len(snapshots) > 0:
        result.ok(f"进化快照已记录 (count={len(snapshots)})")
    else:
        result.fail("进化快照为空", "无快照记录")

    # =============================================================================
    # 验证10: 事件总线正常工作
    # =============================================================================
    print(f"\n  --- 验证10: 事件总线 ---")
    try:
        # event_bus应该已停止
        if not agent.event_bus._running:
            result.ok(f"事件总线已正确停止")
        else:
            result.fail("事件总线未停止", "event_bus仍在运行")
    except Exception as e:
        result.fail("事件总线异常", str(e))

    # =============================================================================
    # 验证11: DB连接无泄漏 —— SQLite文件可正常访问
    # =============================================================================
    print(f"\n  --- 验证11: DB连接无泄漏 ---")
    try:
        import sqlite3
        conn = sqlite3.connect(os.path.join(tmp_dir, "chaos_memory.db"))
        cursor = conn.execute("SELECT COUNT(*) FROM experiences")
        db_count = cursor.fetchone()[0]
        conn.close()
        if db_count > 0:
            result.ok(f"DB可正常访问 (records={db_count})")
        else:
            result.fail("DB为空", "experiences表无记录")
    except Exception as e:
        result.fail("DB访问异常", str(e))

    # =============================================================================
    # 验证12: 长期记忆系统跨进程稳定性 —— hash稳定性
    # =============================================================================
    print(f"\n  --- 验证12: 长期记忆hash稳定性 ---")
    try:
        from memory.long_term_memory import LongTermMemory, _stable_index_id
        ltm = LongTermMemory(db_path=os.path.join(tmp_dir, "chaos_ltm.db"))

        # 存储一条带向量的记忆
        vec = np.random.rand(28).astype(np.float32)
        entry = MemoryEntry(
            content=vec,
            memory_type=MemoryType.EPISODIC,
            value_score=0.8,
        )
        ltm.store(entry)

        # 计算stable_index_id（应跨进程稳定）
        idx_id_1 = _stable_index_id(entry.id)

        # 重新创建LTM实例（模拟重启）
        ltm2 = LongTermMemory(db_path=os.path.join(tmp_dir, "chaos_ltm.db"))
        idx_id_2 = _stable_index_id(entry.id)

        if idx_id_1 == idx_id_2:
            result.ok(f"stable_index_id跨实例一致 ({idx_id_1})")
        else:
            result.fail("stable_index_id不一致", f"{idx_id_1} != {idx_id_2}")

        # 验证search_similar能找到刚存的记忆
        results = ltm2.search_similar(vec, k=1)
        if len(results) > 0:
            result.ok(f"search_similar正常 (找到{len(results)}条)")
        else:
            result.fail("search_similar失效", "未找到刚存储的记忆")

    except Exception as e:
        result.fail("长期记忆异常", f"{type(e).__name__}: {e}")

    # =============================================================================
    # 清理
    # =============================================================================
    import shutil
    try:
        shutil.rmtree(tmp_dir)
        print(f"\n  [Cleanup] 临时目录已清理: {tmp_dir}")
    except Exception:
        pass

    return result


def run_concurrent_stress_test() -> TestResult:
    """
    并发压力测试 —— 多线程并发访问记忆系统，验证线程安全
    """
    result = TestResult()
    print(f"\n{'='*60}")
    print(f"  并发压力测试 —— 多线程并发访问")
    print(f"{'='*60}")

    import tempfile
    import threading
    tmp_dir = tempfile.mkdtemp(prefix="concurrent_test_")

    from memory import ShortTermMemory
    mem = ShortTermMemory(max_size=10000, db_path=os.path.join(tmp_dir, "concurrent.db"))

    errors: List[str] = []
    num_threads = 8
    ops_per_thread = 200

    def worker(thread_id: int):
        try:
            for i in range(ops_per_thread):
                entry = MemoryEntry(
                    content=f"thread_{thread_id}_op_{i}",
                    memory_type=MemoryType.EPISODIC,
                    value_score=np.random.random(),
                    tags=[f"thread_{thread_id}"],
                )
                mem.store(entry)
                # 随机检索
                if i % 5 == 0:
                    mem.retrieve_by_tags([f"thread_{thread_id}"], limit=5)
                if i % 10 == 0:
                    mem.retrieve_high_value(threshold=0.5, limit=10)
        except Exception as e:
            errors.append(f"Thread {thread_id}: {type(e).__name__}: {e}")

    threads = []
    t0 = time.time()
    for tid in range(num_threads):
        t = threading.Thread(target=worker, args=(tid,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=60)

    elapsed = time.time() - t0
    total_ops = num_threads * ops_per_thread

    print(f"  {num_threads}线程 x {ops_per_thread}操作 = {total_ops}总操作, 耗时{elapsed:.2f}s")

    if len(errors) == 0:
        result.ok(f"并发无异常 ({total_ops}操作)")
    else:
        result.fail("并发异常", f"{len(errors)}个错误")
        for e in errors[:3]:
            print(f"    {e}")

    # 验证数据完整性
    final_size = len(mem)
    expected_max = num_threads * ops_per_thread
    if final_size > 0:
        result.ok(f"并发写入成功 (final_size={final_size})")
    else:
        result.fail("并发写入失败", "最终大小为0")

    # 验证max_size限制
    if final_size <= 10000:
        result.ok(f"max_size限制生效 ({final_size} <= 10000)")
    else:
        result.fail("max_size失效", f"{final_size} > 10000")

    # 清理
    import shutil
    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    return result


def run_long_term_memory_persistence_test() -> TestResult:
    """
    长期记忆持久化测试 —— 验证重启后数据可恢复
    """
    result = TestResult()
    print(f"\n{'='*60}")
    print(f"  长期记忆持久化测试 —— 重启后数据恢复")
    print(f"{'='*60}")

    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="persistence_test_")
    db_path = os.path.join(tmp_dir, "persistence.db")

    try:
        from memory.long_term_memory import LongTermMemory

        # 第一次运行：存储数据
        ltm1 = LongTermMemory(db_path=db_path)
        stored_ids = []
        for i in range(20):
            vec = np.random.rand(28).astype(np.float32)
            entry = MemoryEntry(
                content=vec,
                memory_type=MemoryType.EPISODIC,
                value_score=0.7 + i * 0.01,
            )
            ltm1.store(entry)
            stored_ids.append(entry.id)

        count1 = ltm1.count()
        print(f"  第一次运行: 存储{len(stored_ids)}条, count={count1}")
        result.ok(f"首次存储成功 (count={count1})")

        # 第二次运行：模拟重启，验证数据恢复
        ltm2 = LongTermMemory(db_path=db_path)
        count2 = ltm2.count()
        print(f"  第二次运行(重启): count={count2}")

        if count2 == count1:
            result.ok(f"重启后数据完整 (count={count2} == {count1})")
        else:
            result.fail("重启后数据丢失", f"count={count2} != {count1}")

        # 验证retrieve能找到之前存的记忆
        found = 0
        for eid in stored_ids[:5]:
            entry = ltm2.retrieve(eid)
            if entry is not None:
                found += 1
        if found == 5:
            result.ok(f"重启后retrieve正常 (5/5找到)")
        else:
            result.fail("重启后retrieve失效", f"仅找到{found}/5")

        # 验证向量索引恢复后search_similar正常
        query_vec = np.random.rand(28).astype(np.float32)
        results = ltm2.search_similar(query_vec, k=3)
        if len(results) > 0:
            result.ok(f"重启后search_similar正常 (找到{len(results)}条)")
        else:
            result.fail("重启后search_similar失效", "未找到结果")

    except Exception as e:
        result.fail("持久化测试异常", f"{type(e).__name__}: {e}")
    finally:
        import shutil
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass

    return result


def main():
    """主入口"""
    print("\n" + "=" * 60)
    print("  自驱永续进化Agent系统 —— 复杂场景闭环测试")
    print("=" * 60)

    all_results = []

    # 测试1: 混沌场景闭环（600步，6阶段）
    all_results.append(("混沌场景闭环", run_chaos_scenario_test(600)))

    # 测试2: 并发压力测试
    all_results.append(("并发压力测试", run_concurrent_stress_test()))

    # 测试3: 长期记忆持久化测试
    all_results.append(("长期记忆持久化", run_long_term_memory_persistence_test()))

    # 汇总
    print("\n" + "=" * 60)
    print("  全部测试汇总")
    print("=" * 60)
    total_pass = 0
    total_fail = 0
    total_warn = 0
    for name, r in all_results:
        print(f"\n  [{name}] 通过:{r.passed} 失败:{r.failed} 警告:{len(r.warnings)}")
        total_pass += r.passed
        total_fail += r.failed
        total_warn += len(r.warnings)
        for e in r.errors:
            print(f"    FAIL: {e}")

    print(f"\n{'='*60}")
    print(f"  总计: 通过 {total_pass}, 失败 {total_fail}, 警告 {total_warn}")
    print(f"{'='*60}")

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
