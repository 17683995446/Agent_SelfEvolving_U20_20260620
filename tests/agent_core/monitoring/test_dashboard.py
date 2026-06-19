"""
Dashboard服务器单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import socket
import time
import unittest
import urllib.request

from agent_core.monitoring.dashboard_server import DashboardServer, get_dashboard_server


def _find_free_port() -> int:
    """查找可用端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class TestDashboardServer(unittest.TestCase):
    """测试Dashboard服务器。"""

    def setUp(self) -> None:
        """每个用例前重置单例。"""
        DashboardServer._instance = None
        from agent_core.monitoring.dashboard_server import DashboardHandler
        DashboardHandler._state_provider = None
        self.server = DashboardServer()
        self._port = _find_free_port()

    def tearDown(self) -> None:
        """每个用例后停止服务器并等待端口释放。"""
        if self.server.is_running():
            self.server.stop()
            time.sleep(0.3)

    def test_singleton(self) -> None:
        """正常值入参测试：单例模式。"""
        another = DashboardServer()
        self.assertIs(self.server, another)

    def test_get_dashboard_server(self) -> None:
        """正常值入参测试：获取实例。"""
        srv = get_dashboard_server()
        self.assertIsInstance(srv, DashboardServer)

    def test_start_and_stop(self) -> None:
        """正常值入参测试：启动与停止。"""
        self.server.start(port=self._port)
        self.assertTrue(self.server.is_running())
        self.server.stop()
        self.assertFalse(self.server.is_running())

    def test_api_status_not_initialized(self) -> None:
        """正常值入参测试：未注册状态提供者。"""
        self.server.start(port=self._port)
        time.sleep(0.1)
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self._port}/api/status"
        ) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            self.assertIn("not_initialized", body)

    def test_api_status_with_provider(self) -> None:
        """正常值入参测试：注册状态提供者后。"""
        self.server.register_state_provider(
            lambda: {"agent": "test", "cycles": 5}
        )
        self.server.start(port=self._port)
        time.sleep(0.1)
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self._port}/api/status"
        ) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            self.assertIn("test", body)
            self.assertIn("5", body)

    def test_dashboard_html(self) -> None:
        """正常值入参测试：Dashboard页面。"""
        self.server.start(port=self._port)
        time.sleep(0.1)
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self._port}/"
        ) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            self.assertIn("Agent Dashboard", body)
            self.assertIn("/api/status", body)

    def test_404(self) -> None:
        """正常值入参测试：非法路径。"""
        self.server.start(port=self._port)
        time.sleep(0.1)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(
                f"http://127.0.0.1:{self._port}/unknown"
            )
        self.assertEqual(ctx.exception.code, 404)

    def test_register_provider_after_start(self) -> None:
        """正常值入参测试：启动后注册提供者。"""
        self.server.start(port=self._port)
        time.sleep(0.1)
        self.server.register_state_provider(lambda: {"updated": True})
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self._port}/api/status"
        ) as resp:
            body = resp.read().decode("utf-8")
            self.assertIn("updated", body)

    def test_empty_state_provider(self) -> None:
        """空入参测试：空状态提供者。"""
        self.server.register_state_provider(lambda: {})
        self.server.start(port=self._port)
        time.sleep(0.1)
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self._port}/api/status"
        ) as resp:
            self.assertEqual(resp.status, 200)

    def test_large_state_provider(self) -> None:
        """边界极值测试：大量数据。"""
        big_data = {"items": list(range(1000))}
        self.server.register_state_provider(lambda: big_data)
        self.server.start(port=self._port)
        time.sleep(0.1)
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self._port}/api/status"
        ) as resp:
            self.assertEqual(resp.status, 200)
            body = resp.read().decode("utf-8")
            self.assertIn("999", body)

    def test_double_start(self) -> None:
        """正常值入参测试：重复启动。"""
        self.server.start(port=self._port)
        self.server.start(port=self._port + 1)
        self.assertTrue(self.server.is_running())


if __name__ == "__main__":
    unittest.main()
