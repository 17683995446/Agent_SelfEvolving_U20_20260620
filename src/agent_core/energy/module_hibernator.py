"""
模块休眠管理器。

将空闲模块置于休眠状态以节省资源，按需唤醒。

第一性原理：
- 生物冬眠/蛰伏（hibernation/torpor）：在资源匮乏或无活动需求时
  降低代谢率至最低，维持生存但减少消耗
- 神经系统的睡眠-觉醒周期：非活跃脑区进入低功耗状态
- 按需唤醒：检测到相关刺激时快速恢复

设计要点：
- 活动追踪：记录模块最后活跃时间
- 休眠阈值：超过空闲时间则休眠
- 分级休眠：浅休眠（快速唤醒）→深休眠（完全卸载）
- 唤醒机制：显式唤醒或活动检测自动唤醒
- 线程安全
"""

import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable, Dict, List, Optional

from agent_core.common.logger import get_logger

# 默认浅休眠阈值（秒）
_DEFAULT_LIGHT_SLEEP_THRESHOLD = 30.0
# 默认深休眠阈值（秒）
_DEFAULT_DEEP_SLEEP_THRESHOLD = 120.0
# 唤醒回调超时（秒）
_WAKEUP_CALLBACK_TIMEOUT = 5.0
# 清理周期（秒）
_CLEANUP_INTERVAL = 60.0


class ModuleState(IntEnum):
    """模块状态。"""

    ACTIVE = 0  # 活跃
    LIGHT_SLEEP = 1  # 浅休眠（快速唤醒）
    DEEP_SLEEP = 2  # 深休眠（需重新初始化）


@dataclass
class _ModuleTracker:
    """模块追踪器。"""

    name: str
    state: ModuleState
    last_active: float
    activation_count: int = 0
    sleep_count: int = 0
    total_active_time: float = 0.0
    total_sleep_time: float = 0.0
    last_state_change: float = 0.0
    wakeup_callback: Optional[Callable[[], None]] = None
    sleep_callback: Optional[Callable[[], None]] = None


class ModuleHibernator:
    """
    模块休眠管理器。

    追踪模块活动，自动休眠空闲模块，按需唤醒。
    """

    def __init__(
        self,
        light_sleep_threshold: float = _DEFAULT_LIGHT_SLEEP_THRESHOLD,
        deep_sleep_threshold: float = _DEFAULT_DEEP_SLEEP_THRESHOLD,
    ) -> None:
        if light_sleep_threshold <= 0:
            raise ValueError("light_sleep_threshold must be positive")
        if deep_sleep_threshold <= light_sleep_threshold:
            raise ValueError(
                "deep_sleep_threshold must be greater than light_sleep_threshold"
            )
        self._light_threshold = light_sleep_threshold
        self._deep_threshold = deep_sleep_threshold
        self._logger = get_logger()
        self._lock = threading.Lock()
        self._modules: Dict[str, _ModuleTracker] = {}
        self._last_cleanup = time.monotonic()

    def register(
        self,
        name: str,
        wakeup_callback: Optional[Callable[[], None]] = None,
        sleep_callback: Optional[Callable[[], None]] = None,
    ) -> None:
        """注册模块。"""
        with self._lock:
            if name in self._modules:
                return
            now = time.monotonic()
            self._modules[name] = _ModuleTracker(
                name=name,
                state=ModuleState.ACTIVE,
                last_active=now,
                last_state_change=now,
                wakeup_callback=wakeup_callback,
                sleep_callback=sleep_callback,
            )

    def unregister(self, name: str) -> None:
        """注销模块。"""
        with self._lock:
            self._modules.pop(name, None)

    def touch(self, name: str) -> None:
        """标记模块活跃（更新最后活跃时间）。"""
        with self._lock:
            tracker = self._modules.get(name)
            if tracker is None:
                return
            now = time.monotonic()
            # 如果从休眠中恢复，执行唤醒
            if tracker.state != ModuleState.ACTIVE:
                self._wakeup(tracker, now)
            tracker.last_active = now
            tracker.activation_count += 1

    def check_and_hibernate(self) -> List[str]:
        """
        检查所有模块并休眠空闲模块。

        Returns:
            本次新休眠的模块列表。
        """
        now = time.monotonic()
        newly_slept: List[str] = []
        with self._lock:
            self._maybe_cleanup(now)
            for tracker in self._modules.values():
                idle = now - tracker.last_active
                if tracker.state == ModuleState.ACTIVE:
                    if idle >= self._deep_threshold:
                        self._sleep(tracker, ModuleState.DEEP_SLEEP, now)
                        newly_slept.append(tracker.name)
                    elif idle >= self._light_threshold:
                        self._sleep(tracker, ModuleState.LIGHT_SLEEP, now)
                        newly_slept.append(tracker.name)
                elif tracker.state == ModuleState.LIGHT_SLEEP:
                    if idle >= self._deep_threshold:
                        self._sleep(tracker, ModuleState.DEEP_SLEEP, now)
                        newly_slept.append(tracker.name)
            return newly_slept

    def wake_up(self, name: str) -> bool:
        """
        显式唤醒模块。

        Returns:
            是否成功唤醒（模块存在且之前在休眠）。
        """
        with self._lock:
            tracker = self._modules.get(name)
            if tracker is None:
                return False
            if tracker.state == ModuleState.ACTIVE:
                return False
            self._wakeup(tracker, time.monotonic())
            return True

    def get_state(self, name: str) -> Optional[ModuleState]:
        """获取模块状态。"""
        with self._lock:
            tracker = self._modules.get(name)
            if tracker is None:
                return None
            return tracker.state

    def is_active(self, name: str) -> bool:
        """模块是否活跃。"""
        state = self.get_state(name)
        return state == ModuleState.ACTIVE

    def get_idle_time(self, name: str) -> Optional[float]:
        """获取模块空闲时间（秒）。"""
        with self._lock:
            tracker = self._modules.get(name)
            if tracker is None:
                return None
            return time.monotonic() - tracker.last_active

    def get_stats(self, name: str) -> Optional[Dict[str, Any]]:
        """获取模块统计。"""
        with self._lock:
            tracker = self._modules.get(name)
            if tracker is None:
                return None
            now = time.monotonic()
            return {
                "name": tracker.name,
                "state": tracker.state.name,
                "last_active": tracker.last_active,
                "idle_time": now - tracker.last_active,
                "activation_count": tracker.activation_count,
                "sleep_count": tracker.sleep_count,
            }

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """获取所有模块统计。"""
        with self._lock:
            now = time.monotonic()
            result = {}
            for name, tracker in self._modules.items():
                result[name] = {
                    "state": tracker.state.name,
                    "idle_time": now - tracker.last_active,
                    "activation_count": tracker.activation_count,
                    "sleep_count": tracker.sleep_count,
                }
            return result

    def set_thresholds(
        self,
        light: Optional[float] = None,
        deep: Optional[float] = None,
    ) -> None:
        """设置休眠阈值。"""
        with self._lock:
            if light is not None:
                self._light_threshold = light
            if deep is not None:
                self._deep_threshold = deep

    def reset(self) -> None:
        """重置所有模块状态。"""
        with self._lock:
            self._modules.clear()

    def _sleep(
        self,
        tracker: _ModuleTracker,
        state: ModuleState,
        now: float,
    ) -> None:
        """执行休眠。"""
        old_state = tracker.state
        tracker.state = state
        tracker.sleep_count += 1
        tracker.last_state_change = now
        # 执行休眠回调
        if tracker.sleep_callback:
            try:
                tracker.sleep_callback()
            except Exception as exc:
                self._logger.error(
                    f"[Hibernator] Sleep callback failed for "
                    f"'{tracker.name}': {exc}"
                )
        self._logger.info(
            f"[Hibernator] '{tracker.name}' -> {state.name} "
            f"(was {old_state.name})"
        )

    def _wakeup(self, tracker: _ModuleTracker, now: float) -> None:
        """执行唤醒。"""
        old_state = tracker.state
        tracker.state = ModuleState.ACTIVE
        tracker.last_active = now
        tracker.last_state_change = now
        # 执行唤醒回调
        if tracker.wakeup_callback:
            try:
                tracker.wakeup_callback()
            except Exception as exc:
                self._logger.error(
                    f"[Hibernator] Wakeup callback failed for "
                    f"'{tracker.name}': {exc}"
                )
        self._logger.info(
            f"[Hibernator] '{tracker.name}' -> ACTIVE "
            f"(was {old_state.name})"
        )

    def _maybe_cleanup(self, now: float) -> None:
        """清理深休眠过久的模块。"""
        if now - self._last_cleanup < _CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        # 深休眠超过1小时的模块可注销（由调用方决定）
        cutoff = now - 3600.0
        to_remove = [
            name
            for name, tracker in self._modules.items()
            if tracker.state == ModuleState.DEEP_SLEEP
            and tracker.last_active < cutoff
        ]
        for name in to_remove:
            del self._modules[name]
        if to_remove:
            self._logger.info(
                f"[Hibernator] Cleaned up {len(to_remove)} "
                f"long-sleeping modules"
            )
