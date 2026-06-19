"""
API网关测试。

覆盖：初始化、路由注册、请求处理、404、500、列表、关闭。
"""

import pytest

from agent_core.common.api_gateway import ApiGateway


class TestApiGateway:
    """ApiGateway测试类。"""

    @pytest.fixture
    def gateway(self):
        """创建网关实例。"""
        return ApiGateway()

    @pytest.mark.asyncio
    async def test_initialize(self, gateway):
        """测试初始化成功。"""
        result = await gateway.initialize({})
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check(self, gateway):
        """测试健康检查。"""
        await gateway.initialize({})
        health = await gateway.health_check()
        assert health["status"] == "healthy"

    def test_version(self, gateway):
        """测试版本号。"""
        assert gateway.version == "1.0.0"

    def test_module_name(self, gateway):
        """测试模块名称。"""
        assert gateway.module_name == "ApiGateway"

    def test_register_and_handle(self, gateway):
        """测试注册路由并处理请求。"""
        gateway.register_route("/test", lambda body: {"echo": body})
        result = gateway.handle_request("/test", {"msg": "hi"})
        assert result["status"] == 200
        assert result["data"] == {"echo": {"msg": "hi"}}

    def test_handle_not_found(self, gateway):
        """测试未注册路由返回404。"""
        result = gateway.handle_request("/missing", {})
        assert result["status"] == 404

    def test_handle_error(self, gateway):
        """测试处理器异常返回500。"""
        gateway.register_route("/fail", lambda body: (_ for _ in ()).throw(ValueError("boom")))
        result = gateway.handle_request("/fail", {})
        assert result["status"] == 500
        assert "boom" in result["error"]

    def test_list_routes(self, gateway):
        """测试列出路由。"""
        gateway.register_route("/a", lambda b: b)
        gateway.register_route("/b", lambda b: b)
        routes = gateway.list_routes()
        assert "/a" in routes
        assert "/b" in routes

    @pytest.mark.asyncio
    async def test_shutdown(self, gateway):
        """测试关闭清空路由。"""
        gateway.register_route("/a", lambda b: b)
        await gateway.shutdown()
        assert gateway.list_routes() == []
