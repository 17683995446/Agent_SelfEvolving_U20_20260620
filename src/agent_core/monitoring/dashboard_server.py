"""
Web Dashboard服务器模块。

使用标准库http.server实现零依赖实时监控。

第一性原理：
- 监控是系统的"外感受"通道，必须低侵入
- 使用标准库避免额外依赖，降低复杂度
- 状态快照即时生成，不存储历史数据
"""

import cProfile
import io
import json
import pstats
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, Optional

from agent_core.common.logger import get_logger

_HTML_TEMPLATE = (
    "<!DOCTYPE html>"
    '<html lang="zh-CN">'
    "<head>"
    '<meta charset="UTF-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
    "<title>Agent Dashboard</title>"
    "<style>"
    "body{font-family:monospace;margin:20px;background:#1e1e1e;color:#d4d4d4}"
    "h1{color:#4ec9b0}"
    ".card{background:#252526;border-radius:8px;padding:16px;margin:12px 0}"
    ".label{color:#9cdcfe}"
    ".value{color:#ce9178}"
    "pre{background:#1e1e1e;padding:8px;border-radius:4px;overflow:auto}"
    "</style>"
    "</head>"
    "<body>"
    "<h1>自驱永续进化Agent Dashboard</h1>"
    '<div class="card">'
    "<p class=\"label\">状态API:</p>"
    '<p class="value"><a href="/api/status" style="color:#ce9178">/api/status</a></p>'
    "</div>"
    '<div class="card">'
    "<p class=\"label\">自动刷新:</p>"
    '<pre id="status">加载中...</pre>'
    "</div>"
    "<script>"
    "async function fetchStatus(){"
    "try{"
    "const r=await fetch('/api/status');"
    "const d=await r.json();"
    "document.getElementById('status').textContent=JSON.stringify(d,null,2);"
    "}catch(e){"
    "document.getElementById('status').textContent='Error: '+e;"
    "}"
    "}"
    "fetchStatus();"
    "setInterval(fetchStatus,2000);"
    "</script>"
    "</body>"
    "</html>"
)


class DashboardHandler(BaseHTTPRequestHandler):
    """Dashboard请求处理器。"""

    _state_provider: Optional[Callable[[], Dict[str, Any]]] = None

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/":
            self._serve_dashboard()
        elif self.path == "/api/status":
            self._serve_api()
        elif self.path == "/metrics":
            self._serve_metrics()
        elif self.path == "/profile":
            self._serve_profile()
        else:
            self._send_404()

    def _serve_dashboard(self) -> None:
        html = _HTML_TEMPLATE
        self._send_response(200, "text/html", html.encode("utf-8"))

    def _serve_api(self) -> None:
        data = self._fetch_state()
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self._send_response(200, "application/json", body)

    def _serve_metrics(self) -> None:
        data = self._fetch_state()
        body = self._format_prometheus(data).encode("utf-8")
        self._send_response(200, "text/plain; version=0.0.4", body)

    def _format_prometheus(self, data: Dict[str, Any]) -> str:
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, (int, float)):
                lines.append(f"# TYPE agent_{key} gauge")
                lines.append(f"agent_{key} {value}")
        return "\n".join(lines) + "\n"

    def _serve_profile(self) -> None:
        data = self._fetch_state()
        body = self._capture_profile(data).encode("utf-8")
        self._send_response(200, "text/plain", body)

    def _capture_profile(self, data: Dict[str, Any]) -> str:
        pr = cProfile.Profile()
        pr.enable()
        _ = json.dumps(data, ensure_ascii=False, default=str)
        pr.disable()
        s = io.StringIO()
        ps = pstats.Stats(pr, stream=s).sort_stats(pstats.SortKey.CUMULATIVE)
        ps.print_stats(20)
        return s.getvalue()

    def _fetch_state(self) -> Dict[str, Any]:
        provider = DashboardHandler._state_provider
        if provider is not None:
            return provider()
        return {"status": "not_initialized"}

    def _send_response(self, code: int, content_type: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_404(self) -> None:
        body = b"Not Found"
        self.send_response(404)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ReusableHTTPServer(HTTPServer):
    """Bug25修复：在bind前生效SO_REUSEADDR，避免重启时端口占用。"""
    allow_reuse_address = True


class DashboardServer:
    """
    Dashboard服务器。

    单例模式，后台线程运行HTTP服务。
    """

    _instance: Optional["DashboardServer"] = None

    def __new__(cls) -> "DashboardServer":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup()
        return cls._instance

    def _setup(self) -> None:
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._state_provider: Optional[Callable[[], Dict[str, Any]]] = None
        self._logger = get_logger()
        self._port: int = 8080

    def register_state_provider(
        self, provider: Callable[[], Dict[str, Any]]
    ) -> None:
        """注册状态提供者。"""
        self._state_provider = provider
        DashboardHandler._state_provider = provider
        self._logger.info("[DashboardServer] State provider registered")

    def start(self, port: int = 8080) -> None:
        """启动Dashboard服务器。"""
        self._port = port
        if self._server is not None:
            self._logger.warning("[DashboardServer] Already running")
            return
        self._server = self._create_server(port)
        self._thread = self._create_thread()
        self._thread.start()
        self._logger.info(f"[DashboardServer] Started on port {port}")

    def _create_server(self, port: int) -> HTTPServer:
        # Bug25修复：使用ReusableHTTPServer在bind前生效SO_REUSEADDR
        return ReusableHTTPServer(("127.0.0.1", port), DashboardHandler)

    def _create_thread(self) -> threading.Thread:
        return threading.Thread(target=self._server.serve_forever, daemon=True)

    def stop(self) -> None:
        """停止Dashboard服务器。"""
        if self._server is None:
            return
        self._server.shutdown()
        # Bug25修复：必须调用server_close()释放监听socket，否则端口泄漏
        self._server.server_close()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None
        self._logger.info("[DashboardServer] Stopped")

    def is_running(self) -> bool:
        """检查服务器是否运行中。"""
        return self._server is not None

    @classmethod
    def reset_for_testing(cls) -> None:
        """重置单例，用于测试隔离。"""
        if cls._instance is not None:
            try:
                cls._instance.stop()
            except Exception:
                pass
        cls._instance = None
        DashboardHandler._state_provider = None


def get_dashboard_server() -> DashboardServer:
    """获取Dashboard服务器实例。"""
    return DashboardServer()
