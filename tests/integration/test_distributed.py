"""
分布式协作集成测试。

验证多Agent状态同步与协作决策。
"""

import asyncio
import unittest

from agent_core.common.message_bus import get_message_bus
from agent_core.memory.distributed_agent import DistributedAgent


class TestDistributedAgent(unittest.TestCase):
    """测试分布式Agent。"""

    def setUp(self) -> None:
        """设置测试环境。"""
        self.config = {
            "perception": {"cpu_interval_seconds": 0.0},
            "drive_engine": {},
            "predictor": {"feature_dimensions": 10},
            "task_generator": {"exploration_rate": 0.0},
            "decision_engine": {"epsilon": 0.0},
            "memory": {"memory_capacity": 100},
        }

    def test_initialization(self) -> None:
        """正常值入参测试：初始化。"""
        agent = DistributedAgent(agent_id="agent_1")
        result = asyncio.run(agent.initialize(self.config))
        self.assertTrue(result)
        asyncio.run(agent.stop())

    def test_state_broadcast(self) -> None:
        """正常值入参测试：状态广播。"""
        bus = get_message_bus()
        agent = DistributedAgent(agent_id="agent_1")
        asyncio.run(agent.initialize(self.config))
        bus.publish(
            "agent_state",
            {
                "agent_id": "agent_2",
                "state": {
                    "cpu": 50.0,
                    "memory": 60.0,
                },
                "drives": {
                    "safety": 0.8,
                    "gain": 0.5,
                    "efficiency": 0.6,
                },
            },
        )
        self.assertEqual(agent.get_neighbor_count(), 1)
        asyncio.run(agent.stop())

    def test_neighbor_adjustment(self) -> None:
        """正常值入参测试：邻居状态调整驱力。"""
        from agent_core.common.data_contracts import DriveSignals

        agent = DistributedAgent(agent_id="agent_1")
        asyncio.run(agent.initialize(self.config))
        bus = get_message_bus()
        bus.publish(
            "agent_state",
            {
                "agent_id": "agent_2",
                "state": {
                    "cpu": 90.0,
                    "memory": 95.0,
                },
                "drives": {
                    "safety": 0.1,
                    "gain": 0.5,
                    "efficiency": 0.5,
                },
            },
        )
        drives = DriveSignals(
            safety_reward=0.5,
            gain_reward=0.5,
            efficiency_reward=0.5,
            safety_gap=0.5,
            gain_gap=0.5,
            efficiency_gap=0.5,
            weights={"safety": 0.33, "gain": 0.33, "efficiency": 0.34},
            total_reward=0.5,
        )
        adjusted = agent._adjust_drives_by_neighbors(drives)
        self.assertEqual(adjusted.weights["safety"], 0.6)
        asyncio.run(agent.stop())

    def test_no_neighbor(self) -> None:
        """空入参测试：无邻居时不调整。"""
        from agent_core.common.data_contracts import DriveSignals

        agent = DistributedAgent(agent_id="agent_1")
        asyncio.run(agent.initialize(self.config))
        drives = DriveSignals(
            safety_reward=0.5,
            gain_reward=0.5,
            efficiency_reward=0.5,
            safety_gap=0.5,
            gain_gap=0.5,
            efficiency_gap=0.5,
            weights={"safety": 0.33, "gain": 0.33, "efficiency": 0.34},
            total_reward=0.5,
        )
        adjusted = agent._adjust_drives_by_neighbors(drives)
        self.assertEqual(adjusted.weights["safety"], 0.33)
        asyncio.run(agent.stop())

    def test_self_message_ignored(self) -> None:
        """正常值入参测试：忽略自身消息。"""
        agent = DistributedAgent(agent_id="agent_1")
        asyncio.run(agent.initialize(self.config))
        bus = get_message_bus()
        bus.publish(
            "agent_state",
            {
                "agent_id": "agent_1",
                "state": {"cpu": 50.0},
                "drives": {"safety": 0.5},
            },
        )
        self.assertEqual(agent.get_neighbor_count(), 0)
        asyncio.run(agent.stop())


if __name__ == "__main__":
    unittest.main()
