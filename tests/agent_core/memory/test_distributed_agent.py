"""
分布式Agent单元测试。

覆盖初始化、状态接收、驱力调整的四类用例。
"""

import asyncio
import time
import unittest
from typing import Any, Dict

from agent_core.memory.distributed_agent import DistributedAgent
from agent_core.common.data_contracts import DriveSignals


class TestDistributedAgent(unittest.IsolatedAsyncioTestCase):
    """测试分布式Agent。"""

    async def test_initialize(self) -> None:
        """正常值测试：初始化成功。"""
        agent = DistributedAgent("agent_1")
        config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {},
            "task_generator": {},
            "decision_engine": {},
            "memory": {},
            "dashboard_port": 0,
        }
        result = await agent.initialize(config)
        self.assertTrue(result)
        await agent.stop()

    async def test_on_state_received(self) -> None:
        """正常值测试：接收邻居状态。"""
        agent = DistributedAgent("agent_1")
        message = {
            "agent_id": "agent_2",
            "state": {"cpu": 50},
            "drives": {"safety": 0.5},
        }
        agent._on_state_received(message)
        self.assertIn("agent_2", agent._neighbors)

    async def test_on_state_received_self(self) -> None:
        """边界测试：忽略自身状态。"""
        agent = DistributedAgent("agent_1")
        message = {
            "agent_id": "agent_1",
            "state": {"cpu": 50},
        }
        agent._on_state_received(message)
        self.assertEqual(len(agent._neighbors), 0)

    async def test_on_decision_received(self) -> None:
        """正常值测试：接收邻居决策。"""
        agent = DistributedAgent("agent_1")
        message = {
            "agent_id": "agent_2",
            "task_name": "test_task",
            "task_type": "safety",
        }
        agent._on_decision_received(message)

    async def test_on_decision_received_self(self) -> None:
        """边界测试：忽略自身决策。"""
        agent = DistributedAgent("agent_1")
        message = {
            "agent_id": "agent_1",
            "task_name": "test_task",
        }
        agent._on_decision_received(message)

    async def test_adjust_drives_no_neighbors(self) -> None:
        """空值测试：无邻居时不调整。"""
        agent = DistributedAgent("agent_1")
        drives = DriveSignals(
            safety_reward=0.1,
            gain_reward=0.2,
            efficiency_reward=0.3,
            safety_gap=0.1,
            gain_gap=0.1,
            efficiency_gap=0.1,
            weights={"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
            total_reward=0.6,
        )
        adjusted = agent._adjust_drives_by_neighbors(drives)
        self.assertIs(adjusted, drives)

    async def test_adjust_drives_low_safety(self) -> None:
        """正常值测试：邻居安全低时调整权重。"""
        agent = DistributedAgent("agent_1")
        agent._neighbors["agent_2"] = {
            "state": {"drives": {"safety": 0.1}},
            "timestamp": time.time(),
        }
        drives = DriveSignals(
            safety_reward=0.1,
            gain_reward=0.2,
            efficiency_reward=0.3,
            safety_gap=0.1,
            gain_gap=0.1,
            efficiency_gap=0.1,
            weights={"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
            total_reward=0.6,
        )
        adjusted = agent._adjust_drives_by_neighbors(drives)
        self.assertEqual(adjusted.weights["safety"], 0.6)

    async def test_adjust_drives_safe_neighbors(self) -> None:
        """边界测试：邻居安全正常时不调整。"""
        agent = DistributedAgent("agent_1")
        agent._neighbors["agent_2"] = {
            "state": {"drives": {"safety": 0.5}},
            "timestamp": time.time(),
        }
        drives = DriveSignals(
            safety_reward=0.1,
            gain_reward=0.2,
            efficiency_reward=0.3,
            safety_gap=0.1,
            gain_gap=0.1,
            efficiency_gap=0.1,
            weights={"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
            total_reward=0.6,
        )
        adjusted = agent._adjust_drives_by_neighbors(drives)
        self.assertIs(adjusted, drives)

    async def test_get_neighbor_count(self) -> None:
        """正常值测试：获取邻居数量。"""
        agent = DistributedAgent("agent_1")
        self.assertEqual(agent.get_neighbor_count(), 0)
        agent._neighbors["a"] = {}
        self.assertEqual(agent.get_neighbor_count(), 1)

    async def test_stop(self) -> None:
        """正常值测试：停止分布式Agent。"""
        agent = DistributedAgent("agent_1")
        await agent.stop()
        self.assertFalse(agent._running)


if __name__ == "__main__":
    unittest.main()
