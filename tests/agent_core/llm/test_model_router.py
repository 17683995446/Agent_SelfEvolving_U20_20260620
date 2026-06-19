"""
模型路由器测试。

覆盖：初始化、健康检查、主模型路由、降级路由、全部故障、关闭。
"""

import pytest

from agent_core.llm.model_router import ModelHealth, ModelRouter


class FakeClient:
    """Fake LLM client for routing tests."""

    def __init__(self, name: str, fail: bool = False) -> None:
        self._name = name
        self._fail = fail
        self._initialized = True

    @property
    def module_name(self) -> str:
        return self._name

    async def initialize(self, config: dict) -> bool:
        return True

    async def health_check(self) -> dict:
        return {"status": "healthy", "metrics": {}}

    async def shutdown(self) -> None:
        pass

    async def generate_code(self, prompt: str, context=None) -> str:
        if self._fail:
            return None
        return f"code_from_{self._name}"

    async def review_code(self, code: str) -> str:
        if self._fail:
            return None
        return f"review_from_{self._name}"


class TestModelHealth:
    """ModelHealth测试类。"""

    def test_initial_state(self):
        """测试初始状态健康。"""
        h = ModelHealth()
        assert h.is_healthy is True
        assert h.consecutive_failures == 0

    def test_record_success(self):
        """测试记录成功后重置失败计数。"""
        h = ModelHealth()
        h.record_failure()
        h.record_failure()
        h.record_success()
        assert h.is_healthy is True
        assert h.consecutive_failures == 0

    def test_record_failure_threshold(self):
        """测试连续失败达到阈值后不健康。"""
        h = ModelHealth()
        h.record_failure()
        h.record_failure()
        assert h.is_healthy is True
        h.record_failure()
        assert h.is_healthy is False


class TestModelRouter:
    """ModelRouter测试类。"""

    @pytest.fixture
    def router(self):
        """创建路由器实例。"""
        return ModelRouter()

    @pytest.mark.asyncio
    async def test_initialize_no_primary(self, router):
        """测试无主配置时初始化失败。"""
        result = await router.initialize({})
        assert result is False

    def test_version(self, router):
        """测试版本号。"""
        assert router.version == "1.0.0"

    def test_module_name(self, router):
        """测试模块名称。"""
        assert router.module_name == "ModelRouter"

    @pytest.mark.asyncio
    async def test_health_check_empty(self, router):
        """测试空路由器健康检查。"""
        health = await router.health_check()
        assert health["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_select_primary(self, router):
        """测试优先选择主模型。"""
        router._primary = FakeClient("primary")
        router._health["primary"] = ModelHealth()
        selected = router._select_client()
        assert selected is not None
        assert selected.module_name == "primary"

    @pytest.mark.asyncio
    async def test_select_fallback_when_primary_unhealthy(self, router):
        """测试主模型不健康时选择备用。"""
        router._primary = FakeClient("primary")
        router._fallbacks = [FakeClient("fallback")]
        h = ModelHealth()
        h.record_failure()
        h.record_failure()
        h.record_failure()
        router._health["primary"] = h
        router._health["fallback"] = ModelHealth()
        selected = router._select_client()
        assert selected is not None
        assert selected.module_name == "fallback"

    @pytest.mark.asyncio
    async def test_select_none_when_all_unhealthy(self, router):
        """测试全部不健康时返回None。"""
        router._primary = FakeClient("primary")
        h = ModelHealth()
        h.record_failure()
        h.record_failure()
        h.record_failure()
        router._health["primary"] = h
        selected = router._select_client()
        assert selected is None

    @pytest.mark.asyncio
    async def test_execute_with_fallback_primary(self, router):
        """测试主模型成功时直接返回。"""
        router._primary = FakeClient("primary")
        router._health["primary"] = ModelHealth()
        result = await router._execute_with_fallback("generate_code", "prompt")
        assert result == "code_from_primary"

    @pytest.mark.asyncio
    async def test_execute_fallback_on_failure(self, router):
        """测试主模型失败时降级到备用。"""
        router._primary = FakeClient("primary", fail=True)
        router._fallbacks = [FakeClient("fallback")]
        router._health["primary"] = ModelHealth()
        router._health["fallback"] = ModelHealth()
        result = await router._execute_with_fallback("generate_code", "prompt")
        assert result == "code_from_fallback"

    @pytest.mark.asyncio
    async def test_execute_all_failed(self, router):
        """测试全部模型失败返回None。"""
        router._primary = FakeClient("primary", fail=True)
        router._fallbacks = [FakeClient("fallback", fail=True)]
        router._health["primary"] = ModelHealth()
        router._health["fallback"] = ModelHealth()
        result = await router._execute_with_fallback("generate_code", "prompt")
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_code_routing(self, router):
        """测试generate_code路由。"""
        router._primary = FakeClient("primary")
        router._health["primary"] = ModelHealth()
        result = await router.generate_code("test")
        assert result == "code_from_primary"

    @pytest.mark.asyncio
    async def test_review_code_routing(self, router):
        """测试review_code路由。"""
        router._primary = FakeClient("primary")
        router._health["primary"] = ModelHealth()
        result = await router.review_code("def f(): pass")
        assert result == "review_from_primary"

    @pytest.mark.asyncio
    async def test_shutdown(self, router):
        """测试关闭。"""
        router._primary = FakeClient("primary")
        await router.shutdown()
