"""
安全事件关联引擎。

关联跨模块安全事件，检测协同攻击与攻击升级模式。

第一性原理：
- 生物适应性免疫系统通过抗原呈递细胞（APC）收集多源信号，
  在淋巴结汇聚分析，识别单一信号无法发现的感染模式
- 安全事件的时序与空间相关性揭示攻击意图
- 威胁升级检测：从侦察→渗透→提权→持久化的攻击链

设计要点：
- 事件收集：各模块上报安全事件
- 时间窗口关联：滑动窗口内的事件聚合
- 攻击模式匹配：预定义攻击链模式
- 威胁等级动态升降：基于事件密度与严重度
- 自动响应：达到阈值时触发封锁/告警
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Deque, Dict, List, Optional

from agent_core.common.logger import get_logger

# 事件保留窗口（秒）
_EVENT_WINDOW = 300.0
# 清理周期
_CLEANUP_INTERVAL = 60.0


class ThreatLevel(IntEnum):
    """威胁等级。"""

    NORMAL = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class SecurityEvent:
    """安全事件。"""

    timestamp: float
    source: str  # 来源模块
    event_type: str  # 事件类型
    severity: float  # 0.0-1.0
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


# 威胁等级阈值（窗口内加权事件分数）
_LEVEL_THRESHOLDS: Dict[ThreatLevel, float] = {
    ThreatLevel.NORMAL: 0.0,
    ThreatLevel.LOW: 0.2,
    ThreatLevel.MEDIUM: 0.8,
    ThreatLevel.HIGH: 2.5,
    ThreatLevel.CRITICAL: 5.0,
}

# 攻击链模式：(事件类型序列, 最小匹配数)
_ATTACK_CHAINS: List[tuple] = [
    # 侦察→渗透→提权
    (
        ("recon", "intrusion", "privilege_escalation"),
        3,
    ),
    # 暴力破解→成功登录
    (
        ("brute_force", "auth_success"),
        2,
    ),
    # 沙箱逃逸尝试→代码执行
    (
        ("sandbox_bypass", "code_execution"),
        2,
    ),
    # 提示注入→数据外泄
    (
        ("prompt_injection", "data_exfiltration"),
        2,
    ),
]


class SecurityCorrelator:
    """
    安全事件关联引擎。

    收集多源安全事件，时序关联，检测攻击链与威胁升级。
    """

    def __init__(
        self,
        window_seconds: float = _EVENT_WINDOW,
    ) -> None:
        self._window = window_seconds
        self._logger = get_logger()
        self._lock = threading.Lock()
        self._events: Deque[SecurityEvent] = deque()
        self._source_threat: Dict[str, ThreatLevel] = defaultdict(
            lambda: ThreatLevel.NORMAL
        )
        self._blocked_sources: set = set()
        self._handlers: List[Callable[[SecurityEvent, ThreatLevel], None]] = []
        self._last_cleanup = time.monotonic()
        self._global_threat_level = ThreatLevel.NORMAL

    def report(
        self,
        source: str,
        event_type: str,
        severity: float,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ThreatLevel:
        """
        上报安全事件。

        Args:
            source: 来源模块名。
            event_type: 事件类型。
            severity: 严重度 0.0-1.0。
            description: 描述。
            metadata: 附加元数据。

        Returns:
            当前全局威胁等级。
        """
        event = SecurityEvent(
            timestamp=time.monotonic(),
            source=source,
            event_type=event_type,
            severity=max(0.0, min(1.0, severity)),
            description=description,
            metadata=metadata or {},
        )
        with self._lock:
            self._maybe_cleanup()
            self._events.append(event)
            self._update_threat_levels()
            self._detect_attack_chains()
            self._dispatch(event, self._global_threat_level)
            return self._global_threat_level

    def add_handler(
        self,
        handler: Callable[[SecurityEvent, ThreatLevel], None],
    ) -> None:
        """注册事件处理器。"""
        with self._lock:
            self._handlers.append(handler)

    def get_threat_level(self) -> ThreatLevel:
        """获取当前全局威胁等级。"""
        with self._lock:
            return self._global_threat_level

    def get_source_threat(self, source: str) -> ThreatLevel:
        """获取指定来源的威胁等级。"""
        with self._lock:
            return self._source_threat.get(source, ThreatLevel.NORMAL)

    def is_blocked(self, source: str) -> bool:
        """来源是否被封锁。"""
        with self._lock:
            return source in self._blocked_sources

    def block_source(self, source: str) -> None:
        """封锁来源。"""
        with self._lock:
            self._blocked_sources.add(source)
            self._logger.warning(
                f"[SecurityCorrelator] Source '{source}' blocked"
            )

    def unblock_source(self, source: str) -> None:
        """解除封锁。"""
        with self._lock:
            self._blocked_sources.discard(source)

    def get_recent_events(
        self, limit: int = 50
    ) -> List[SecurityEvent]:
        """获取最近的事件。"""
        with self._lock:
            return list(self._events)[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息。"""
        with self._lock:
            source_counts: Dict[str, int] = defaultdict(int)
            type_counts: Dict[str, int] = defaultdict(int)
            for ev in self._events:
                source_counts[ev.source] += 1
                type_counts[ev.event_type] += 1
            return {
                "total_events": len(self._events),
                "global_threat_level": self._global_threat_level.name,
                "blocked_sources": list(self._blocked_sources),
                "events_by_source": dict(source_counts),
                "events_by_type": dict(type_counts),
            }

    def reset(self) -> None:
        """重置关联引擎。"""
        with self._lock:
            self._events.clear()
            self._source_threat.clear()
            self._blocked_sources.clear()
            self._global_threat_level = ThreatLevel.NORMAL

    def _update_threat_levels(self) -> None:
        """更新威胁等级。"""
        now = time.monotonic()
        # 按来源聚合窗口内事件
        source_scores: Dict[str, float] = defaultdict(float)
        for ev in self._events:
            if now - ev.timestamp <= self._window:
                # 严重度加权 + 时间衰减
                age = now - ev.timestamp
                decay = max(0.1, 1.0 - age / self._window)
                source_scores[ev.source] += ev.severity * decay

        # 重置不在窗口内的来源为NORMAL
        active_sources = set(source_scores.keys())
        for src in list(self._source_threat.keys()):
            if src not in active_sources:
                self._source_threat[src] = ThreatLevel.NORMAL

        # 更新来源威胁等级
        for source, score in source_scores.items():
            level = ThreatLevel.NORMAL
            for lvl in sorted(
                _LEVEL_THRESHOLDS.keys(),
                key=lambda x: x.value,
                reverse=True,
            ):
                if score >= _LEVEL_THRESHOLDS[lvl]:
                    level = lvl
                    break
            self._source_threat[source] = level

        # 全局威胁等级 = 最高来源等级
        if source_scores:
            self._global_threat_level = max(
                self._source_threat[s] for s in source_scores
            )
        else:
            self._global_threat_level = ThreatLevel.NORMAL

        # 自动封锁达到CRITICAL的来源
        for source, level in self._source_threat.items():
            if level >= ThreatLevel.CRITICAL:
                self._blocked_sources.add(source)

    def _detect_attack_chains(self) -> None:
        """检测攻击链模式。"""
        now = time.monotonic()
        # 按来源分组事件类型序列
        source_types: Dict[str, List[str]] = defaultdict(list)
        for ev in self._events:
            if now - ev.timestamp <= self._window:
                source_types[ev.source].append(ev.event_type)

        for source, type_seq in source_types.items():
            for chain, min_match in _ATTACK_CHAINS:
                matched = self._match_subsequence(type_seq, list(chain))
                if matched >= min_match:
                    self._logger.warning(
                        f"[SecurityCorrelator] Attack chain detected: "
                        f"{chain} (matched {matched}) from '{source}'"
                    )
                    # 攻击链检测提升全局威胁等级
                    if self._global_threat_level < ThreatLevel.HIGH:
                        self._global_threat_level = ThreatLevel.HIGH
                    # 攻击链来源自动封锁
                    self._blocked_sources.add(source)
                    # 提升来源威胁等级
                    if self._source_threat.get(source, ThreatLevel.NORMAL) < ThreatLevel.HIGH:
                        self._source_threat[source] = ThreatLevel.HIGH

    @staticmethod
    def _match_subsequence(
        sequence: List[str], pattern: List[str]
    ) -> int:
        """匹配子序列，返回匹配长度。"""
        if not pattern:
            return 0
        best = 0
        for i in range(len(sequence)):
            match_len = 0
            j = 0
            while (
                i + j < len(sequence)
                and j < len(pattern)
                and sequence[i + j] == pattern[j]
            ):
                match_len += 1
                j += 1
            best = max(best, match_len)
        return best

    def _dispatch(
        self, event: SecurityEvent, level: ThreatLevel
    ) -> None:
        """分发事件到处理器。"""
        for handler in self._handlers:
            try:
                handler(event, level)
            except Exception as exc:
                self._logger.error(
                    f"[SecurityCorrelator] Handler failed: {exc}"
                )

    def _maybe_cleanup(self) -> None:
        """清理过期事件。"""
        now = time.monotonic()
        if now - self._last_cleanup < _CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        cutoff = now - self._window
        while self._events and self._events[0].timestamp < cutoff:
            self._events.popleft()
