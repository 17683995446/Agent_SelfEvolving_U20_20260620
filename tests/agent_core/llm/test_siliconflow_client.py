"""
硅基流动LLM客户端测试。

覆盖：初始化、代码生成、代码审查、代码修复、测试生成、健康检查、关闭。
"""

import pytest

from agent_core.llm.siliconflow_client import SiliconFlowClient


class TestSiliconFlowClient:
    """SiliconFlowClient测试类。"""

    @pytest.fixture
    def client(self):
        """创建客户端实例。"""
        return SiliconFlowClient()

    @pytest.mark.asyncio
    async def test_initialize_without_key(self, client):
        """测试无API密钥时初始化失败。"""
        result = await client.initialize({})
        assert result is False
        assert client._initialized is False

    @pytest.mark.asyncio
    async def test_initialize_with_key(self, client):
        """测试有API密钥时初始化成功。"""
        result = await client.initialize({"api_key": "test-key"})
        assert result is True
        assert client._initialized is True
        assert client._api_key == "test-key"

    @pytest.mark.asyncio
    async def test_initialize_custom_model(self, client):
        """测试自定义模型配置。"""
        result = await client.initialize({
            "api_key": "test-key",
            "model": "custom-model",
            "base_url": "https://custom.api.com",
        })
        assert result is True
        assert client._model == "custom-model"
        assert client._base_url == "https://custom.api.com"

    @pytest.mark.asyncio
    async def test_request_not_initialized(self, client):
        """测试未初始化时请求返回None。"""
        result = await client._request([{"role": "user", "content": "hi"}])
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_code_not_initialized(self, client):
        """测试未初始化时代码生成返回None。"""
        result = await client.generate_code("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_review_code_not_initialized(self, client):
        """测试未初始化时代码审查返回None。"""
        result = await client.review_code("def f(): pass")
        assert result is None

    @pytest.mark.asyncio
    async def test_fix_code_not_initialized(self, client):
        """测试未初始化时代码修复返回None。"""
        result = await client.fix_code("def f(): pass", "error")
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_tests_not_initialized(self, client):
        """测试未初始化时测试生成返回None。"""
        result = await client.generate_tests("def f(): pass")
        assert result is None

    @pytest.mark.asyncio
    async def test_generate_docs_not_initialized(self, client):
        """测试未初始化时文档生成返回None。"""
        result = await client.generate_docs("def f(): pass")
        assert result is None

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, client):
        """测试未初始化时健康检查返回unhealthy。"""
        health = await client.health_check()
        assert health["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, client):
        """测试初始化后健康检查返回healthy。"""
        await client.initialize({"api_key": "test-key"})
        health = await client.health_check()
        assert health["status"] == "healthy"
        assert health["metrics"]["model"] == "deepseek-ai/DeepSeek-V3"

    @pytest.mark.asyncio
    async def test_shutdown(self, client):
        """测试关闭后状态重置。"""
        await client.initialize({"api_key": "test-key"})
        await client.shutdown()
        assert client._initialized is False

    def test_version(self, client):
        """测试版本号。"""
        assert client.version == "1.0.0"

    def test_module_name(self, client):
        """测试模块名称。"""
        assert client.module_name == "SiliconFlowClient"
