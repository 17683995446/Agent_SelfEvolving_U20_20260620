"""
记忆系统模块。

经验存储与离线复盘，支持优先级采样。
"""

import asyncio
from typing import Any, Dict, List

import numpy as np

from agent_core.common.data_contracts import Experience
from agent_core.common.interfaces import IMemorySystem, IMultiLayerPredictor
from agent_core.common.exceptions import ModuleNotInitializedException
from agent_core.common.constants import MEMORY_CAPACITY_DEFAULT
from agent_core.common.logger import get_logger
from agent_core.memory.persistence import PersistenceManager

_PRIORITY_BASE = 1.0
_PRIORITY_DECAY = 0.9
_PRIORITY_SMOOTHING = 0.01
_BATCH_SIZE_MAX = 100


_BATCH_FLUSH_SIZE = 100
# Bug27修复：待持久化经验上限，防止持续失败时内存无限增长
_MAX_PENDING_EXPERIENCES = 1000


class MemorySystem(IMemorySystem):
    """
    记忆系统实现。
    """

    def __init__(self) -> None:
        self._capacity = MEMORY_CAPACITY_DEFAULT
        self._experiences: List[Experience] = []
        self._priorities: np.ndarray = np.zeros(0, dtype=np.float32)
        self._position = 0
        self._initialized = False
        self._config: Dict[str, Any] = {}
        self._logger = get_logger()
        self._pending_experiences: List[Experience] = []
        self._id_to_index: Dict[int, int] = {}
        # Bug39修复：asyncio.Lock保护并发异步操作（在线store与离线review并发）
        self._lock: asyncio.Lock = asyncio.Lock()

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "MemorySystem"

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化记忆系统。"""
        self._config = config
        self._capacity = config.get("memory_capacity", MEMORY_CAPACITY_DEFAULT)
        db_path = config.get("db_path", "agent_memory.db")
        self._persistence = PersistenceManager(db_path=db_path)
        self._experiences = []
        self._priorities = np.zeros(self._capacity, dtype=np.float32)
        self._position = 0
        self._initialized = True
        self._logger.info("[MemorySystem] Initialized")
        return True

    async def store(self, experience: Experience) -> None:
        """存储经验。"""
        if not self._initialized:
            self._logger.warning("[MemorySystem] Not initialized, skip store")
            return
        # Bug39修复：用asyncio.Lock保护，避免在线store与离线review并发修改_experiences
        async with self._lock:
            priority = self._compute_priority(experience)
            self._insert_experience(experience, priority)
            self._pending_experiences.append(experience)
            # Bug27修复：限制待持久化队列上限，持续失败时丢弃最旧经验避免OOM
            if len(self._pending_experiences) > _MAX_PENDING_EXPERIENCES:
                overflow = len(self._pending_experiences) - _MAX_PENDING_EXPERIENCES
                del self._pending_experiences[:overflow]
                self._logger.warning(
                    f"[MemorySystem] Pending overflow, dropped {overflow} old experiences"
                )
            if len(self._pending_experiences) >= _BATCH_FLUSH_SIZE:
                await self._flush_pending()
            self._logger.debug(
                f"[MemorySystem] Stored experience, count={len(self._experiences)}"
            )

    async def _flush_pending(self) -> None:
        """批量写入待持久化经验，失败时保留数据。"""
        if not self._pending_experiences:
            return
        try:
            self._persistence.save_experiences(
                self._pending_experiences
            )
            self._pending_experiences.clear()
        except Exception as exc:
            self._logger.warning(
                f"[MemorySystem] Batch save failed: {exc}"
            )

    def _insert_experience(self, experience: Experience, priority: float) -> None:
        if len(self._experiences) < self._capacity:
            index = len(self._experiences)
            self._experiences.append(experience)
            self._priorities[index] = priority
            self._id_to_index[id(experience)] = index
        else:
            old_exp = self._experiences[self._position]
            del self._id_to_index[id(old_exp)]
            self._experiences[self._position] = experience
            self._priorities[self._position] = priority
            self._id_to_index[id(experience)] = self._position
            self._position = (self._position + 1) % self._capacity

    def _compute_priority(self, experience: Experience) -> float:
        priority = _PRIORITY_BASE
        # Bug23修复：对NaN做兜底，避免NaN永久污染_priorities
        mae = experience.error_metrics.mae
        if not np.isfinite(mae):
            mae = 0.0
        reward = experience.drive_signals.total_reward
        if not np.isfinite(reward):
            reward = 0.0
        exp_priority = experience.priority
        if not np.isfinite(exp_priority):
            exp_priority = 0.0
        priority += mae
        priority += reward
        priority += exp_priority
        if not np.isfinite(priority):
            priority = _PRIORITY_BASE
        return priority

    async def sample_experiences(self, sample_size: int) -> List[Experience]:
        """采样经验。"""
        if not self._initialized or not self._experiences:
            return []
        # Bug39修复：用asyncio.Lock保护，避免采样时_experiences被并发修改
        async with self._lock:
            if not self._experiences:
                return []
            n = min(sample_size, len(self._experiences))
            probs = self._compute_probs()
            indices = np.random.choice(
                len(self._experiences), size=n, replace=False, p=probs
            )
            return [self._experiences[i] for i in indices]

    def _compute_probs(self) -> np.ndarray:
        valid = self._priorities[: len(self._experiences)]
        valid = valid + _PRIORITY_SMOOTHING
        # Bug23修复：过滤NaN/inf，避免np.random.choice(p=NaN)抛错
        valid = np.nan_to_num(valid, nan=_PRIORITY_SMOOTHING, posinf=_PRIORITY_BASE, neginf=_PRIORITY_SMOOTHING)
        total = np.sum(valid)
        if not np.isfinite(total) or total < 1e-10:
            # 全部异常时均匀分布
            return np.ones(len(valid)) / len(valid)
        return valid / total

    async def offline_review(self, predictor: IMultiLayerPredictor) -> None:
        """离线复盘。"""
        # Bug39修复：用asyncio.Lock保护，避免与在线store并发修改_experiences/_priorities
        async with self._lock:
            if not self._experiences:
                self._logger.debug("[MemorySystem] No experiences to review")
                return
            # 直接内部采样，避免再次获取锁（asyncio.Lock不可重入）
            batch = self._sample_batch_sync()
            self._logger.info(f"[MemorySystem] Reviewing {len(batch)} experiences")
            self._train_predictor(predictor, batch)
            self._decay_priorities(batch)
            self._logger.info("[MemorySystem] Offline review completed")

    def _sample_batch_sync(self) -> List[Experience]:
        """同步采样批量经验（调用方已持锁）。"""
        if not self._experiences:
            return []
        batch_size = min(_BATCH_SIZE_MAX, len(self._experiences))
        n = min(batch_size, len(self._experiences))
        probs = self._compute_probs()
        indices = np.random.choice(
            len(self._experiences), size=n, replace=False, p=probs
        )
        return [self._experiences[i] for i in indices]

    def _train_predictor(
        self, predictor: IMultiLayerPredictor, batch: List[Experience]
    ) -> None:
        for exp in batch:
            previous_state = exp.prediction.ensemble
            actual_state = exp.state.feature_vector
            if previous_state.shape != actual_state.shape:
                self._logger.warning(
                    f"[MemorySystem] Shape mismatch in training: "
                    f"prediction={previous_state.shape}, "
                    f"actual={actual_state.shape}, skip"
                )
                continue
            predictor.update_all(previous_state, actual_state)

    def _decay_priorities(self, batch: List[Experience]) -> None:
        for exp in batch:
            idx = self._id_to_index.get(id(exp))
            if idx is not None:
                self._priorities[idx] *= _PRIORITY_DECAY

    async def health_check(self) -> Dict[str, Any]:
        """健康检查。"""
        status = "healthy" if self._initialized else "unhealthy"
        return {
            "status": status,
            "metrics": {
                "experience_count": len(self._experiences),
                "capacity": self._capacity,
            },
        }

    async def shutdown(self) -> None:
        """优雅关闭，仅 flush 未持久化的经验。"""
        # Bug39修复：用asyncio.Lock保护，避免与并发store/review冲突
        async with self._lock:
            self._initialized = False
            await self._flush_pending()
            self._experiences.clear()
            self._priorities = np.zeros(0, dtype=np.float32)
            self._pending_experiences.clear()
        self._id_to_index.clear()
        self._logger.info("[MemorySystem] Shutdown")
