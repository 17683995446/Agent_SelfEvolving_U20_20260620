"""
分布式Agent协作模块。

支持多Agent实例间的状态同步与协作决策。

第一性原理：
- 社会性动物通过信息素协调群体行为
- 分布式共识避免单点故障
- 局部决策 + 全局协调
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from agent_core.common.data_contracts import DriveSignals, EnvironmentState
from agent_core.common.logger import get_logger
from agent_core.common.message_bus import get_message_bus
from agent_core.memory.agent_main import SelfEvolvingAgent
from agent_core.memory.social_intelligence import (
    CoalitionManager,
    GameTheoreticStrategy,
    ReputationTracker,
)


class DistributedAgent:
    """
    分布式Agent节点。

    通过消息总线与其他Agent协作。
    """

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id
        self._agent = SelfEvolvingAgent()
        self._bus = get_message_bus()
        self._neighbors: Dict[str, Dict[str, Any]] = {}
        self._logger = get_logger()
        self._running = False
        self._state_version = 0
        self._heartbeat_timeout = 10.0
        self._reputation = ReputationTracker()
        self._coalition = CoalitionManager()
        self._game_strategy = GameTheoreticStrategy()

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """
        初始化分布式Agent。

        Args:
            config: 配置字典。

        Returns:
            初始化成功返回True。
        """
        self._logger.info(
            f"[DistributedAgent:{self._agent_id}] Initializing..."
        )
        result = await self._agent.initialize(config)
        self._bus.subscribe("agent_state", self._on_state_received)
        self._bus.subscribe("agent_decision", self._on_decision_received)
        return result

    def _on_state_received(self, message: Dict[str, Any]) -> None:
        """接收邻居状态，带版本向量校验。"""
        sender_id = message.get("agent_id")
        if sender_id == self._agent_id:
            return
        incoming_version = message.get("version", 0)
        current = self._neighbors.get(sender_id, {})
        current_version = current.get("version", 0)
        if incoming_version < current_version:
            self._logger.debug(
                f"[DistributedAgent:{self._agent_id}] "
                f"Ignored stale state from {sender_id}"
            )
            return
        self._neighbors[sender_id] = {
            "state": message,
            "timestamp": time.time(),
            "version": incoming_version,
        }
        self._logger.debug(
            f"[DistributedAgent:{self._agent_id}] "
            f"Received state v{incoming_version} from {sender_id}"
        )

    def _on_decision_received(self, message: Dict[str, Any]) -> None:
        """接收邻居决策，更新信誉。"""
        sender_id = message.get("agent_id")
        if sender_id == self._agent_id:
            return
        cooperated = message.get("cooperated", True)
        self._reputation.record_interaction(sender_id, cooperated)
        self._logger.debug(
            f"[DistributedAgent:{self._agent_id}] "
            f"Received decision from {sender_id}: {message.get('task_name')}"
        )

    async def run(self, interval_seconds: float) -> None:
        """
        运行分布式Agent循环。

        Args:
            interval_seconds: 循环间隔秒数。
        """
        self._running = True
        while self._running:
            try:
                env_state = await self._agent.perception.perceive()
                drive_signals = await self._agent.drive_engine.compute(
                    env_state
                )
                self._state_version += 1
                self._bus.publish(
                    "agent_state",
                    {
                        "agent_id": self._agent_id,
                        "version": self._state_version,
                        "state": {
                            "cpu": env_state.raw_sensors.get(
                                "cpu", {}
                            ).get("percent"),
                            "memory": env_state.raw_sensors.get(
                                "memory", {}
                            ).get("percent"),
                        },
                        "drives": {
                            "safety": drive_signals.safety_reward,
                            "gain": drive_signals.gain_reward,
                            "efficiency": drive_signals.efficiency_reward,
                        },
                    },
                )
                # 基于邻居状态调整权重
                adjusted_drives = self._adjust_drives_by_neighbors(
                    drive_signals
                )
                prediction = self._agent.predictor.predict_all(
                    env_state.feature_vector
                )
                error = self._agent.error_evaluator.evaluate(
                    prediction.ensemble, env_state.feature_vector
                )
                tasks = self._agent.task_generator.generate(
                    adjusted_drives, error
                )
                if tasks:
                    selected = self._agent.decision_engine.select(
                        tasks, adjusted_drives
                    )
                    if selected:
                        self._bus.publish(
                            "agent_decision",
                            {
                                "agent_id": self._agent_id,
                                "task_name": selected.name,
                                "task_type": selected.task_type,
                            },
                        )
                        result = await self._agent.task_executor.execute(
                            selected
                        )
                        self._logger.info(
                            f"[DistributedAgent:{self._agent_id}] "
                            f"Executed {selected.name}, "
                            f"reward={result.get('reward', 0):.3f}"
                        )
                await asyncio.sleep(interval_seconds)
            except Exception as exc:
                self._logger.error(
                    f"[DistributedAgent:{self._agent_id}] Error: {exc}"
                )
                await asyncio.sleep(interval_seconds)

    def _prune_stale_neighbors(self) -> None:
        """清理超时的邻居节点。"""
        now = time.time()
        stale = [
            nid for nid, info in self._neighbors.items()
            if now - info.get("timestamp", 0) > self._heartbeat_timeout
        ]
        for nid in stale:
            del self._neighbors[nid]
            self._logger.info(
                f"[DistributedAgent:{self._agent_id}] "
                f"Pruned stale neighbor {nid}"
            )

    def _adjust_drives_by_neighbors(
        self, drives: DriveSignals
    ) -> DriveSignals:
        """根据邻居状态调整驱力。"""
        self._prune_stale_neighbors()
        if not self._neighbors:
            return drives
        neighbor_safety = []
        for neighbor in self._neighbors.values():
            neighbor_drives = neighbor.get("state", {}).get("drives", {})
            safety = neighbor_drives.get("safety", 0.5)
            neighbor_safety.append(safety)
        avg_safety = sum(neighbor_safety) / len(neighbor_safety)
        if avg_safety < 0.3:
            new_weights = {
                "safety": 0.6,
                "gain": 0.2,
                "efficiency": 0.2,
            }
            return DriveSignals(
                safety_reward=drives.safety_reward,
                gain_reward=drives.gain_reward,
                efficiency_reward=drives.efficiency_reward,
                safety_gap=drives.safety_gap,
                gain_gap=drives.gain_gap,
                efficiency_gap=drives.efficiency_gap,
                weights=new_weights,
                total_reward=drives.total_reward,
            )
        return drives

    async def stop(self) -> None:
        """
        停止分布式Agent。
        """
        self._running = False
        await self._agent.stop()
        self._logger.info(
            f"[DistributedAgent:{self._agent_id}] Stopped"
        )

    def get_neighbor_count(self) -> int:
        """
        获取邻居数量。

        Returns:
            邻居数量。
        """
        return len(self._neighbors)
