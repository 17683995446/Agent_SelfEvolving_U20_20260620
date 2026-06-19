"""
环境感知模块单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import asyncio
import unittest

import numpy as np

from agent_core.common.data_contracts import EnvironmentState
from agent_core.perception.perception_module import EnvironmentPerception
from agent_core.perception.sensor import (
    CPUSensor,
    DiskSensor,
    MemorySensor,
    NetworkSensor,
    ProcessSensor,
)
from agent_core.perception.state_normalizer import StateNormalizer


class TestCPUSensor(unittest.TestCase):
    """测试CPU传感器。"""

    def test_normal_read(self) -> None:
        """正常值入参测试。"""
        sensor = CPUSensor(interval_seconds=0.1)
        data = asyncio.run(sensor.read())
        self.assertIn("percent", data)
        self.assertIn("count", data)
        self.assertGreaterEqual(data["percent"], 0.0)

    def test_empty_interval(self) -> None:
        """边界极值测试：间隔为0。"""
        sensor = CPUSensor(interval_seconds=0.0)
        data = asyncio.run(sensor.read())
        self.assertIn("percent", data)


class TestMemorySensor(unittest.TestCase):
    """测试内存传感器。"""

    def test_normal_read(self) -> None:
        """正常值入参测试。"""
        sensor = MemorySensor()
        data = asyncio.run(sensor.read())
        self.assertIn("percent", data)
        self.assertIn("total", data)
        self.assertGreater(data["total"], 0)


class TestDiskSensor(unittest.TestCase):
    """测试磁盘传感器。"""

    def test_normal_read(self) -> None:
        """正常值入参测试。"""
        sensor = DiskSensor(paths=["/"])
        data = asyncio.run(sensor.read())
        self.assertIn("partitions", data)
        self.assertGreater(len(data["partitions"]), 0)

    def test_empty_paths(self) -> None:
        """空入参测试：空路径列表。"""
        sensor = DiskSensor(paths=[])
        data = asyncio.run(sensor.read())
        self.assertEqual(data["partitions"], [])

    def test_invalid_path(self) -> None:
        """非法格式测试：不存在的路径。"""
        sensor = DiskSensor(paths=["/nonexistent_path_12345"])
        data = asyncio.run(sensor.read())
        self.assertEqual(data["partitions"], [])


class TestNetworkSensor(unittest.TestCase):
    """测试网络传感器。"""

    def test_normal_read(self) -> None:
        """正常值入参测试。"""
        sensor = NetworkSensor()
        data = asyncio.run(sensor.read())
        self.assertIn("bytes_sent", data)
        self.assertIn("bytes_recv", data)


class TestProcessSensor(unittest.TestCase):
    """测试进程传感器。"""

    def test_normal_read(self) -> None:
        """正常值入参测试。"""
        sensor = ProcessSensor()
        data = asyncio.run(sensor.read())
        self.assertIn("total_processes", data)
        self.assertGreater(data["total_processes"], 0)


class TestStateNormalizer(unittest.TestCase):
    """测试状态标准化器。"""

    def test_normalize_range(self) -> None:
        """正常值入参测试：输出范围验证。"""
        normalizer = StateNormalizer(feature_dimensions=10)
        sensor_data = {
            "cpu": {"percent": 50.0, "load_avg_1m": 2.0},
            "memory": {"percent": 60.0, "swap_percent": 10.0},
            "disk": {"partitions": [{"percent": 70.0}]},
            "network": {"packets_recv": 1000, "errin": 10, "errout": 5},
            "log": {"error_count": 2, "warning_count": 5},
            "process": {"total_processes": 200},
        }
        features = normalizer.normalize(sensor_data)
        self.assertEqual(len(features), 10)
        self.assertTrue(np.all(features >= 0.0))
        self.assertTrue(np.all(features <= 1.0))

    def test_empty_sensor_data(self) -> None:
        """空入参测试：缺失传感器数据。"""
        normalizer = StateNormalizer(feature_dimensions=10)
        features = normalizer.normalize({})
        self.assertEqual(len(features), 10)
        self.assertTrue(np.all(features >= 0.0))

    def test_boundary_values(self) -> None:
        """边界极值测试：最大使用率。"""
        normalizer = StateNormalizer(feature_dimensions=10)
        sensor_data = {
            "cpu": {"percent": 100.0, "load_avg_1m": 20.0},
            "memory": {"percent": 100.0, "swap_percent": 100.0},
            "disk": {"partitions": [{"percent": 100.0}]},
            "network": {"packets_recv": 1, "errin": 100, "errout": 100},
            "log": {"error_count": 100, "warning_count": 100},
            "process": {"total_processes": 10000},
        }
        features = normalizer.normalize(sensor_data)
        self.assertTrue(np.all(features >= 0.0))
        self.assertTrue(np.all(features <= 1.0))


class TestEnvironmentPerception(unittest.TestCase):
    """测试环境感知模块。"""

    def test_initialization(self) -> None:
        """正常值入参测试：初始化。"""
        perception = EnvironmentPerception()
        result = asyncio.run(perception.initialize({}))
        self.assertTrue(result)
        self.assertEqual(perception.version, "1.0.0")

    def test_perceive(self) -> None:
        """正常值入参测试：感知流程。"""
        perception = EnvironmentPerception()
        asyncio.run(perception.initialize({}))
        state = asyncio.run(perception.perceive())
        self.assertIsInstance(state, EnvironmentState)
        self.assertEqual(len(state.feature_vector), 10)
        self.assertIn("cpu", state.raw_sensors)

    def test_state_history(self) -> None:
        """正常值入参测试：状态历史。"""
        perception = EnvironmentPerception()
        asyncio.run(perception.initialize({}))
        asyncio.run(perception.perceive())
        history = perception.get_state_history(history_size=10)
        self.assertGreaterEqual(len(history), 1)

    def test_perceive_without_init(self) -> None:
        """非法格式测试：未初始化调用感知。"""
        perception = EnvironmentPerception()
        with self.assertRaises(Exception):
            asyncio.run(perception.perceive())


if __name__ == "__main__":
    unittest.main()
