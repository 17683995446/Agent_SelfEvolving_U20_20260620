"""
健康检查体系模块测试。

覆盖：存活检查、就绪检查、深度检查、模块异常、自定义检查。
"""

import pytest

from agent_core.common.health_probe import HealthProbe, ProbeLevel
from agent_core.common.interfaces import ModuleInterface


class FakeModule(ModuleInterface):
    """Fake module for health tests."""

    def __init__(self, healthy: bool = True) -> None:
        self._healthy = healthy

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "FakeModule"

    async def initialize(self, config: dict) -> bool:
        return True

    async def health_check(self) -> dict:
        status = "healthy" if self._healthy else "unhealthy"
        return {"status": status, "metrics": {}}

    async def shutdown(self) -> None:
        pass


class TestHealthProbe:
    """HealthProbe测试类。"""

    @pytest.fixture
    def probe(self):
        """创建健康探针实例。"""
        return HealthProbe()

    @pytest.mark.asyncio
    async def test_liveness(self, probe):
        """测试存活检查极轻量。"""
        result = await probe.liveness()
        assert result["status"] == "alive"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_readiness_healthy(self, probe):
        """测试就绪检查健康模块。"""
        probe.register_module("mod", FakeModule(healthy=True))
        result = await probe.readiness()
        assert result["status"] == "healthy"
        assert result["checks"]["mod"]["healthy"] is True

    @pytest.mark.asyncio
    async def test_readiness_unhealthy(self, probe):
        """测试就绪检查不健康模块。"""
        probe.register_module("mod", FakeModule(healthy=False))
        result = await probe.readiness()
        assert result["status"] == "unhealthy"
        assert result["checks"]["mod"]["healthy"] is False

    @pytest.mark.asyncio
    async def test_readiness_exception(self, probe):
        """测试模块异常时标记为不健康。"""
        class BadModule(FakeModule):
            async def health_check(self) -> dict:
                raise RuntimeError("fail")
        probe.register_module("mod", BadModule())
        result = await probe.readiness()
        assert result["status"] == "unhealthy"
        assert "fail" in result["checks"]["mod"]["error"]

    @pytest.mark.asyncio
    async def test_deep_check_custom(self, probe):
        """测试深度检查包含自定义检查。"""
        async def custom_check() -> bool:
            return True
        probe.register_custom_check("disk", custom_check)
        result = await probe.deep_check()
        assert result["checks"]["disk"]["healthy"] is True

    @pytest.mark.asyncio
    async def test_deep_check_custom_fail(self, probe):
        """测试自定义检查失败。"""
        async def custom_check() -> bool:
            return False
        probe.register_custom_check("disk", custom_check)
        result = await probe.deep_check()
        assert result["status"] == "unhealthy"
        assert result["checks"]["disk"]["healthy"] is False
