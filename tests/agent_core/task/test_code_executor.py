"""
代码执行器测试。

覆盖：初始化、各类任务执行、代码验证、自动修复、健康检查、关闭。
"""

import pytest

from agent_core.task.code_executor import CodeExecutor
from agent_core.common.data_contracts import Task


class TestCodeExecutor:
    """CodeExecutor测试类。"""

    @pytest.fixture
    def executor(self):
        """创建执行器实例。"""
        return CodeExecutor()

    @pytest.fixture
    def initialized_executor(self, executor):
        """创建已初始化的执行器实例。"""
        return executor

    @pytest.mark.asyncio
    async def test_initialize(self, executor):
        """测试初始化成功。"""
        result = await executor.initialize({
            "llm": {"api_key": "test-key"}
        })
        assert result is True
        assert executor._initialized is True
        assert executor._llm is not None

    @pytest.mark.asyncio
    async def test_initialize_no_key(self, executor):
        """测试无密钥时初始化失败。"""
        result = await executor.initialize({"llm": {}})
        assert result is False

    @pytest.mark.asyncio
    async def test_execute_unknown_task(self, executor):
        """测试未知任务类型返回失败。"""
        task = Task(
            task_id="t1",
            name="unknown",
            task_type="unknown_type",
            priority=1.0,
            expected_reward=0.5,
            expected_cost=0.1,
            novelty_score=0.5,
            params={},
        )
        result = await executor.execute(task)
        assert result["status"] == "unknown_task_type"
        assert result["reward"] == 0.0

    @pytest.mark.asyncio
    async def test_execute_generation_no_llm(self, executor):
        """测试未初始化时代码生成失败。"""
        task = Task(
            task_id="t1",
            name="gen",
            task_type="code_generation",
            priority=1.0,
            expected_reward=0.5,
            expected_cost=0.1,
            novelty_score=0.5,
            params={"prompt": "test"},
        )
        result = await executor.execute(task)
        assert result["status"] == "llm_not_ready"

    @pytest.mark.asyncio
    async def test_execute_review_no_llm(self, executor):
        """测试未初始化时代码审查失败。"""
        task = Task(
            task_id="t1",
            name="review",
            task_type="code_review",
            priority=1.0,
            expected_reward=0.3,
            expected_cost=0.1,
            novelty_score=0.3,
            params={"code": "def f(): pass"},
        )
        result = await executor.execute(task)
        assert result["status"] == "llm_not_ready"

    @pytest.mark.asyncio
    async def test_execute_fix_no_llm(self, executor):
        """测试未初始化时代码修复失败。"""
        task = Task(
            task_id="t1",
            name="fix",
            task_type="code_fix",
            priority=1.0,
            expected_reward=0.6,
            expected_cost=0.1,
            novelty_score=0.3,
            params={"code": "def f(): pass", "error_message": "err"},
        )
        result = await executor.execute(task)
        assert result["status"] == "llm_not_ready"

    @pytest.mark.asyncio
    async def test_execute_test_gen_no_llm(self, executor):
        """测试未初始化时测试生成失败。"""
        task = Task(
            task_id="t1",
            name="test_gen",
            task_type="test_generation",
            priority=1.0,
            expected_reward=0.4,
            expected_cost=0.1,
            novelty_score=0.3,
            params={"code": "def f(): pass"},
        )
        result = await executor.execute(task)
        assert result["status"] == "llm_not_ready"

    @pytest.mark.asyncio
    async def test_validate_code_valid(self, executor):
        """测试有效代码验证通过。"""
        valid = await executor._validate_code("def f(): return 1")
        assert valid is True

    @pytest.mark.asyncio
    async def test_validate_code_invalid(self, executor):
        """测试无效代码验证失败。"""
        valid = await executor._validate_code("def f(: pass")
        assert valid is False

    @pytest.mark.asyncio
    async def test_auto_fix_valid_code(self, executor):
        """测试自动修复对有效代码返回原代码。"""
        code = "def f(): return 1"
        fixed = await executor._auto_fix(code)
        assert fixed == code

    @pytest.mark.asyncio
    async def test_auto_fix_no_llm(self, executor):
        """测试无LLM时自动修复返回None。"""
        fixed = await executor._auto_fix("def f(: pass")
        assert fixed is None

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, executor):
        """测试未初始化时健康检查。"""
        health = await executor.health_check()
        assert health["status"] == "unhealthy"

    @pytest.mark.asyncio
    async def test_shutdown(self, executor):
        """测试关闭后状态重置。"""
        await executor.initialize({"llm": {"api_key": "test-key"}})
        await executor.shutdown()
        assert executor._initialized is False

    def test_version(self, executor):
        """测试版本号。"""
        assert executor.version == "1.0.0"

    def test_module_name(self, executor):
        """测试模块名称。"""
        assert executor.module_name == "CodeExecutor"
