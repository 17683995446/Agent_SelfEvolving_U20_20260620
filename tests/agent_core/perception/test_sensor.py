"""
传感器模块单元测试。

覆盖各类传感器的四类用例。
"""

import asyncio
import unittest
from typing import Any, Dict

from agent_core.perception.sensor import (
    ISensor,
    CPUSensor,
    MemorySensor,
    DiskSensor,
    NetworkSensor,
    LogSensor,
    ProcessSensor,
)


class TestCPUSensor(unittest.IsolatedAsyncioTestCase):
    """测试CPU传感器。"""

    async def test_read(self) -> None:
        """正常值测试：读取CPU数据。"""
        sensor = CPUSensor(interval_seconds=0.1)
        data = await sensor.read()
        self.assertIn("percent", data)
        self.assertIn("count", data)
        self.assertIn("load_avg_1m", data)

    async def test_sensor_type(self) -> None:
        """正常值测试：传感器类型。"""
        sensor = CPUSensor(interval_seconds=0.1)
        self.assertEqual(sensor.sensor_type, "cpu")


class TestMemorySensor(unittest.IsolatedAsyncioTestCase):
    """测试内存传感器。"""

    async def test_read(self) -> None:
        """正常值测试：读取内存数据。"""
        sensor = MemorySensor()
        data = await sensor.read()
        self.assertIn("percent", data)
        self.assertIn("total", data)
        self.assertIn("swap_percent", data)

    async def test_sensor_type(self) -> None:
        """正常值测试：传感器类型。"""
        sensor = MemorySensor()
        self.assertEqual(sensor.sensor_type, "memory")


class TestDiskSensor(unittest.IsolatedAsyncioTestCase):
    """测试磁盘传感器。"""

    async def test_read_default_path(self) -> None:
        """正常值测试：读取默认路径。"""
        sensor = DiskSensor(paths=None)
        data = await sensor.read()
        self.assertIn("partitions", data)

    async def test_read_custom_path(self) -> None:
        """正常值测试：读取自定义路径。"""
        sensor = DiskSensor(paths=["/tmp"])
        data = await sensor.read()
        self.assertIn("partitions", data)

    async def test_read_nonexistent_path(self) -> None:
        """边界测试：路径不存在。"""
        sensor = DiskSensor(paths=["/nonexistent_path_12345"])
        data = await sensor.read()
        self.assertEqual(data["partitions"], [])

    async def test_sensor_type(self) -> None:
        """正常值测试：传感器类型。"""
        sensor = DiskSensor(paths=None)
        self.assertEqual(sensor.sensor_type, "disk")


class TestNetworkSensor(unittest.IsolatedAsyncioTestCase):
    """测试网络传感器。"""

    async def test_read(self) -> None:
        """正常值测试：读取网络数据。"""
        sensor = NetworkSensor()
        data = await sensor.read()
        self.assertIn("bytes_sent", data)
        self.assertIn("bytes_recv", data)

    async def test_sensor_type(self) -> None:
        """正常值测试：传感器类型。"""
        sensor = NetworkSensor()
        self.assertEqual(sensor.sensor_type, "network")


class TestLogSensor(unittest.IsolatedAsyncioTestCase):
    """测试日志传感器。"""

    async def test_read_empty_paths(self) -> None:
        """空值测试：空日志路径。"""
        sensor = LogSensor(log_paths=[], max_lines=10)
        data = await sensor.read()
        self.assertEqual(data["error_count"], 0)
        self.assertEqual(data["warning_count"], 0)

    async def test_read_nonexistent_file(self) -> None:
        """边界测试：文件不存在。"""
        sensor = LogSensor(
            log_paths=["/nonexistent_log_12345"], max_lines=10
        )
        data = await sensor.read()
        self.assertEqual(data["error_count"], 0)

    async def test_read_with_content(self) -> None:
        """正常值测试：读取有内容的日志。"""
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".log"
        ) as f:
            f.write("ERROR: something wrong\n")
            f.write("WARNING: be careful\n")
            f.write("INFO: normal\n")
            path = f.name
        try:
            sensor = LogSensor(log_paths=[path], max_lines=10)
            data = await sensor.read()
            self.assertEqual(data["error_count"], 1)
            self.assertEqual(data["warning_count"], 1)
            self.assertEqual(data["total_issues"], 2)
        finally:
            os.unlink(path)

    async def test_sensor_type(self) -> None:
        """正常值测试：传感器类型。"""
        sensor = LogSensor(log_paths=[], max_lines=10)
        self.assertEqual(sensor.sensor_type, "log")


class TestProcessSensor(unittest.IsolatedAsyncioTestCase):
    """测试进程传感器。"""

    async def test_read(self) -> None:
        """正常值测试：读取进程数据。"""
        sensor = ProcessSensor()
        data = await sensor.read()
        self.assertIn("total_processes", data)
        self.assertIn("zombie_count", data)
        self.assertIn("thread_count", data)

    async def test_sensor_type(self) -> None:
        """正常值测试：传感器类型。"""
        sensor = ProcessSensor()
        self.assertEqual(sensor.sensor_type, "process")


class TestISensor(unittest.TestCase):
    """测试传感器接口。"""

    def test_isensor_is_abc(self) -> None:
        """正常值测试：ISensor是ABC。"""
        from abc import ABC

        self.assertTrue(issubclass(ISensor, ABC))

    def test_cannot_instantiate(self) -> None:
        """非法测试：不能直接实例化。"""
        with self.assertRaises(TypeError):
            ISensor()


if __name__ == "__main__":
    unittest.main()
