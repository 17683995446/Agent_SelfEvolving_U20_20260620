"""
审计日志模块。

记录所有关键操作的不可篡改审计轨迹。

第一性原理：
- 审计日志是安全事件追溯的唯一依据
- 日志一旦写入不可修改
- 包含操作者、操作类型、时间、结果、影响范围
"""

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent_core.common.logger import get_logger


@dataclass
class AuditEvent:
    """审计事件。"""

    timestamp: float
    actor: str
    action: str
    resource: str
    result: str
    details: Dict[str, Any]
    event_hash: str = ""


class AuditLogger:
    """
    审计日志记录器。

    将关键操作记录为结构化审计事件，支持链式哈希防篡改。
    """

    def __init__(self) -> None:
        self._logger = get_logger()
        self._events: List[AuditEvent] = []
        self._last_hash: str = "0" * 64

    def log(
        self,
        actor: str,
        action: str,
        resource: str,
        result: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        记录审计事件。

        Args:
            actor: 操作者标识。
            action: 操作类型。
            resource: 被操作资源。
            result: 操作结果。
            details: 详细参数。
        """
        event = AuditEvent(
            timestamp=time.monotonic(),
            actor=actor,
            action=action,
            resource=resource,
            result=result,
            details=details or {},
            event_hash="",
        )
        self._events.append(event)
        self._last_hash = self._compute_hash(event)
        event.event_hash = self._last_hash
        self._logger.info(
            f"[Audit] {actor} {action} {resource} -> {result}"
        )

    def _compute_hash(self, event: AuditEvent) -> str:
        """计算事件哈希（包含前一条哈希，形成链）。"""
        payload = {
            "timestamp": event.timestamp,
            "actor": event.actor,
            "action": event.action,
            "resource": event.resource,
            "result": event.result,
            "details": event.details,
            "prev_hash": self._last_hash,
        }
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def get_events(
        self,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """
        查询审计事件。

        Args:
            actor: 按操作者过滤。
            action: 按操作类型过滤。
            limit: 最大返回数量。

        Returns:
            审计事件列表。
        """
        results = self._events
        if actor is not None:
            results = [e for e in results if e.actor == actor]
        if action is not None:
            results = [e for e in results if e.action == action]
        return results[-limit:]

    def verify_integrity(self) -> bool:
        """
        验证审计链完整性。

        Returns:
            未被篡改返回True。
        """
        prev_hash = "0" * 64
        for event in self._events:
            expected = self._compute_hash_at(event, prev_hash)
            if expected != event.event_hash:
                return False
            prev_hash = expected
        return True

    def _compute_hash_at(
        self, event: AuditEvent, prev_hash: str
    ) -> str:
        """计算指定事件的哈希。"""
        payload = {
            "timestamp": event.timestamp,
            "actor": event.actor,
            "action": event.action,
            "resource": event.resource,
            "result": event.result,
            "details": event.details,
            "prev_hash": prev_hash,
        }
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def export_json(self, file_path: str) -> bool:
        """
        导出审计日志为JSON文件。

        Args:
            file_path: 输出路径。

        Returns:
            成功返回True。
        """
        data = [
            {
                "timestamp": e.timestamp,
                "actor": e.actor,
                "action": e.action,
                "resource": e.resource,
                "result": e.result,
                "details": e.details,
            }
            for e in self._events
        ]
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except OSError as exc:
            self._logger.error(f"[AuditLogger] Export failed: {exc}")
            return False
