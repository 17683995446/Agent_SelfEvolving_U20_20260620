"""
生命周期管理模块。

处理系统信号，实现优雅启停和状态保存。

第一性原理：
- 进程退出前必须完成正在进行的任务
- 状态必须持久化，重启后可恢复
- 信号处理是操作系统与进程的契约
"""

import signal
import sys
from typing import Any, Callable, Coroutine, Dict, List, Optional

from agent_core.common.logger import get_logger


class LifecycleManager:
    """
    生命周期管理器。

    注册信号处理器，协调优雅关闭流程。
    """

    def __init__(self) -> None:
        self._shutdown_hooks: List[Callable[[], Coroutine[Any, Any, None]]] = []
        self._logger = get_logger()
        self._shutting_down = False
        self._pending_tasks: List[Any] = []

    def register_shutdown_hook(
        self, hook: Callable[[], Coroutine[Any, Any, None]]
    ) -> None:
        """
        注册关闭钩子。

        Args:
            hook: 异步关闭函数。
        """
        self._shutdown_hooks.append(hook)
        self._logger.info("[LifecycleManager] Shutdown hook registered")

    def setup_signal_handlers(self) -> None:
        """设置信号处理器。"""
        try:
            signal.signal(signal.SIGTERM, self._on_signal)
            signal.signal(signal.SIGINT, self._on_signal)
            self._logger.info("[LifecycleManager] Signal handlers installed")
        except ValueError:
            self._logger.warning(
                "[LifecycleManager] Signals not supported in this environment"
            )

    def _on_signal(self, signum: int, frame: Any) -> None:
        """信号回调。"""
        self._logger.info(
            f"[LifecycleManager] Received signal {signum}, shutting down"
        )
        self._shutting_down = True
        self._run_shutdown_sync()
        sys.exit(0)

    def _run_shutdown_sync(self) -> None:
        """同步执行所有关闭钩子。"""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                for hook in self._shutdown_hooks:
                    task = asyncio.create_task(hook())
                    self._pending_tasks.append(task)
            else:
                loop.run_until_complete(self._run_hooks())
        except RuntimeError:
            pass

    async def _run_hooks(self) -> None:
        """按顺序执行关闭钩子。"""
        for hook in self._shutdown_hooks:
            try:
                await hook()
            except Exception as exc:
                self._logger.error(
                    f"[LifecycleManager] Hook error: {exc}"
                )

    async def graceful_shutdown(self) -> None:
        """手动触发优雅关闭。"""
        if self._shutting_down:
            return
        self._shutting_down = True
        self._logger.info("[LifecycleManager] Graceful shutdown started")
        await self._run_hooks()
        self._logger.info("[LifecycleManager] Graceful shutdown complete")

    @property
    def is_shutting_down(self) -> bool:
        """是否正在关闭。"""
        return self._shutting_down
