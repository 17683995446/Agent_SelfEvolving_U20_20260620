"""
进度指示器工具模块。

为长时间运行的操作提供进度反馈，降低用户等待焦虑。

第一性原理：
- 生物需要反馈来确认"系统在工作"，无反馈的等待引发焦虑
- 进度指示器是"心跳"，让用户知道操作正在进行
- 简单、非侵入式：不干扰正常输出，可禁用

设计要点：
- ProgressBar: 已知总量的进度条
- Spinner: 未知总量的旋转指示器
- TTY检测：非TTY环境自动降级为静默
- 线程安全：可在后台线程更新
"""

import sys
import threading
import time
from typing import Any, Optional


class ProgressBar:
    """
    进度条。

    用于已知总量的操作，显示百分比和进度条。

    用法:
        bar = ProgressBar(total=100, description="Processing")
        for i in range(100):
            bar.update(i + 1)
        bar.finish()
    """

    def __init__(
        self,
        total: int,
        description: str = "",
        width: int = 30,
        enabled: Optional[bool] = None,
    ) -> None:
        """
        初始化进度条。

        Args:
            total: 总量。
            description: 描述文字。
            width: 进度条宽度（字符数）。
            enabled: 是否启用（None时自动检测TTY）。
        """
        self._total = max(total, 1)
        self._current = 0
        self._description = description
        self._width = width
        self._enabled = enabled if enabled is not None else sys.stdout.isatty()
        self._start_time = time.time()
        self._lock = threading.Lock()

    def update(self, current: int) -> None:
        """
        更新进度。

        Args:
            current: 当前进度值。
        """
        with self._lock:
            self._current = min(current, self._total)
            if self._enabled:
                self._render()

    def increment(self, step: int = 1) -> None:
        """
        增加进度。

        Args:
            step: 增加量。
        """
        self.update(self._current + step)

    def _render(self) -> None:
        """渲染进度条。"""
        percent = self._current / self._total
        filled = int(self._width * percent)
        bar = "=" * filled + "-" * (self._width - filled)

        elapsed = time.time() - self._start_time
        if self._current > 0 and percent > 0:
            eta = elapsed / percent * (1 - percent)
            eta_str = f"ETA: {eta:.1f}s"
        else:
            eta_str = "ETA: --"

        desc = f"{self._description} " if self._description else ""
        sys.stdout.write(
            f"\r{desc}[{bar}] {percent*100:.1f}% "
            f"({self._current}/{self._total}) {eta_str}"
        )
        sys.stdout.flush()

    def finish(self) -> None:
        """完成进度条。"""
        with self._lock:
            self._current = self._total
            if self._enabled:
                self._render()
                sys.stdout.write("\n")
                sys.stdout.flush()


class Spinner:
    """
    旋转指示器。

    用于未知总量的操作，显示旋转动画。

    用法:
        spinner = Spinner(description="Loading")
        spinner.start()
        # ... do work ...
        spinner.stop()
    """

    _FRAMES = ["|", "/", "-", "\\"]

    def __init__(
        self,
        description: str = "",
        enabled: Optional[bool] = None,
    ) -> None:
        """
        初始化旋转指示器。

        Args:
            description: 描述文字。
            enabled: 是否启用（None时自动检测TTY）。
        """
        self._description = description
        self._enabled = enabled if enabled is not None else sys.stdout.isatty()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._frame_idx = 0

    def start(self) -> None:
        """启动旋转指示器。"""
        if not self._enabled:
            return
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _spin(self) -> None:
        """旋转动画循环。"""
        while self._running:
            frame = self._FRAMES[self._frame_idx % len(self._FRAMES)]
            desc = f"{self._description} " if self._description else ""
            sys.stdout.write(f"\r{desc}{frame}")
            sys.stdout.flush()
            self._frame_idx += 1
            time.sleep(0.15)

    def stop(self, message: Optional[str] = None) -> None:
        """
        停止旋转指示器。

        Args:
            message: 停止后显示的消息。
        """
        if not self._enabled:
            if message:
                print(message)
            return
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        # 清除旋转字符
        sys.stdout.write("\r" + " " * (len(self._description) + 2) + "\r")
        if message:
            print(message)
        sys.stdout.flush()


class ProgressContext:
    """
    进度上下文管理器。

    自动管理进度条的生命周期。

    用法:
        with ProgressContext(total=100, description="Processing") as bar:
            for i in range(100):
                bar.increment()
    """

    def __init__(
        self,
        total: int,
        description: str = "",
        enabled: Optional[bool] = None,
    ) -> None:
        self._bar = ProgressBar(
            total=total, description=description, enabled=enabled
        )

    def __enter__(self) -> ProgressBar:
        return self._bar

    def __exit__(self, *args) -> None:
        self._bar.finish()


def show_progress(
    total: int,
    description: str = "",
    enabled: Optional[bool] = None,
) -> ProgressContext:
    """
    创建进度上下文管理器。

    Args:
        total: 总量。
        description: 描述文字。
        enabled: 是否启用。

    Returns:
        ProgressContext上下文管理器。
    """
    return ProgressContext(
        total=total, description=description, enabled=enabled
    )
