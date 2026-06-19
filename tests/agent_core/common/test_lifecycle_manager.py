"""
生命周期管理模块测试。

覆盖：钩子注册、手动关闭、关闭状态、钩子执行顺序、异常处理。
"""

import pytest

from agent_core.common.lifecycle_manager import LifecycleManager


class TestLifecycleManager:
    """LifecycleManager测试类。"""

    @pytest.fixture
    def manager(self):
        """创建生命周期管理器实例。"""
        return LifecycleManager()

    @pytest.mark.asyncio
    async def test_register_and_shutdown(self, manager):
        """测试注册钩子并关闭。"""
        calls = []
        async def hook():
            calls.append(1)
        manager.register_shutdown_hook(hook)
        await manager.graceful_shutdown()
        assert calls == [1]
        assert manager.is_shutting_down is True

    @pytest.mark.asyncio
    async def test_multiple_hooks(self, manager):
        """测试多个钩子按顺序执行。"""
        calls = []
        async def hook1():
            calls.append(1)
        async def hook2():
            calls.append(2)
        manager.register_shutdown_hook(hook1)
        manager.register_shutdown_hook(hook2)
        await manager.graceful_shutdown()
        assert calls == [1, 2]

    @pytest.mark.asyncio
    async def test_hook_error_continues(self, manager):
        """测试钩子错误不影响后续钩子。"""
        calls = []
        async def bad_hook():
            raise ValueError("boom")
        async def good_hook():
            calls.append(1)
        manager.register_shutdown_hook(bad_hook)
        manager.register_shutdown_hook(good_hook)
        await manager.graceful_shutdown()
        assert calls == [1]

    @pytest.mark.asyncio
    async def test_double_shutdown_idempotent(self, manager):
        """测试重复关闭是幂等的。"""
        calls = []
        async def hook():
            calls.append(1)
        manager.register_shutdown_hook(hook)
        await manager.graceful_shutdown()
        await manager.graceful_shutdown()
        assert calls == [1]

    def test_setup_signals_no_crash(self, manager):
        """测试信号设置不崩溃。"""
        manager.setup_signal_handlers()

    def test_initial_state(self, manager):
        """测试初始状态。"""
        assert manager.is_shutting_down is False
