"""
轻量级链路追踪模块。

不依赖OpenTelemetry，用标准库实现跨模块span追踪。

第一性原理：
- 追踪的核心是记录"谁在何时做了什么"
- 不需要复杂的外部SDK，上下文传递+计时即可
- 与JSON日志集成，输出结构化trace
"""

import json
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Generator, List, Optional

from agent_core.common.logger import get_logger

_current_trace: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_current_span: ContextVar[Optional[str]] = ContextVar("span_id", default=None)


class Span:
    """追踪片段。"""

    def __init__(self, name: str, trace_id: str, parent_id: Optional[str]) -> None:
        self.name = name
        self.trace_id = trace_id
        self.span_id = str(uuid.uuid4())[:8]
        self.parent_id = parent_id
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.tags: Dict[str, Any] = {}

    def finish(self) -> None:
        self.end_time = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self._duration_ms(),
            "tags": self.tags,
        }

    def _duration_ms(self) -> Optional[float]:
        if self.end_time is None:
            return None
        return round((self.end_time - self.start_time) * 1000, 3)


class Tracer:
    """轻量级追踪器。"""

    def __init__(self) -> None:
        self._spans: List[Span] = []
        self._logger = get_logger()

    @contextmanager
    def span(self, name: str) -> Generator[Span, None, None]:
        trace_id = _current_trace.get() or str(uuid.uuid4())[:8]
        parent_id = _current_span.get()
        _current_trace.set(trace_id)
        s = Span(name, trace_id, parent_id)
        _current_span.set(s.span_id)
        self._spans.append(s)
        try:
            yield s
        finally:
            s.finish()
            self._emit(s)
            _current_span.set(parent_id)

    def _emit(self, s: Span) -> None:
        self._logger.info(json.dumps({"trace": s.to_dict()}, ensure_ascii=False))

    def get_spans(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self._spans if s.end_time is not None]

    def clear(self) -> None:
        self._spans.clear()


_tracer: Optional[Tracer] = None


def get_tracer() -> Tracer:
    global _tracer
    if _tracer is None:
        _tracer = Tracer()
    return _tracer
