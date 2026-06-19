"""
API网关模块。

提供RESTful接口，允许外部系统查询状态、提交任务、获取结果。

第一性原理：
- 外部交互必须标准化
- 接口是无状态的，可水平扩展
- 输入输出严格遵循数据契约
"""

import json
from typing import Any, Callable, Dict, List, Optional

from agent_core.common.interfaces import ModuleInterface
from agent_core.common.logger import get_logger


class ApiGateway(ModuleInterface):
    """
    API网关。

    封装HTTP请求处理，路由到内部模块。
    """

    def __init__(self) -> None:
        self._routes: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self._logger = get_logger()
        self._initialized = False

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "ApiGateway"

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化网关。"""
        self._initialized = True
        self._logger.info("[ApiGateway] Initialized")
        return True

    async def health_check(self) -> Dict[str, Any]:
        """健康检查。"""
        return {
            "status": "healthy",
            "metrics": {"routes": list(self._routes.keys())},
        }

    async def shutdown(self) -> None:
        """优雅关闭。"""
        self._initialized = False
        self._routes.clear()

    def register_route(
        self,
        path: str,
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        """
        注册路由处理器。

        Args:
            path: 路由路径。
            handler: 处理函数。
        """
        self._routes[path] = handler
        self._logger.info(f"[ApiGateway] Registered route: {path}")

    def handle_request(
        self, path: str, body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        处理HTTP请求。

        Args:
            path: 请求路径。
            body: 请求体。

        Returns:
            响应字典。
        """
        handler = self._routes.get(path)
        if handler is None:
            return {"status": 404, "error": "Not found"}
        try:
            result = handler(body)
            return {"status": 200, "data": result}
        except Exception as exc:
            self._logger.error(f"[ApiGateway] Handler error: {exc}")
            return {"status": 500, "error": str(exc)}

    def list_routes(self) -> List[str]:
        """列出所有注册路由。"""
        return list(self._routes.keys())
