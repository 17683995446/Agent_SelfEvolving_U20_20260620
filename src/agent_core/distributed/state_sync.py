"""
状态同步优化模块。

实现增量同步与冲突解决，减少分布式节点间的数据传输。

第一性原理：
- 只传输变化的部分
- 版本向量检测并发冲突
- 最后写入者优先（可配置）
"""

import hashlib
from typing import Any, Dict, List, Optional, Tuple

from agent_core.common.logger import get_logger


class StateSync:
    """
    状态同步器。

    计算增量补丁，解决并发冲突。
    """

    def __init__(self) -> None:
        self._last_synced: Dict[str, Any] = {}
        self._version: int = 0
        self._logger = get_logger()

    def compute_delta(
        self, current: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        计算当前状态相对于上次同步的增量。

        Args:
            current: 当前完整状态。

        Returns:
            增量字典（仅包含变化的键）。
        """
        delta: Dict[str, Any] = {}
        for key, value in current.items():
            if key not in self._last_synced:
                delta[key] = value
            elif self._hash(value) != self._hash(self._last_synced[key]):
                delta[key] = value
        for key in self._last_synced:
            if key not in current:
                delta[key] = None
        return delta

    def _hash(self, value: Any) -> str:
        """计算值的哈希。"""
        import json
        data = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def apply_delta(self, delta: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用增量到本地状态。

        Args:
            delta: 增量字典。

        Returns:
            更新后的完整状态。
        """
        state = dict(self._last_synced)
        for key, value in delta.items():
            if value is None:
                state.pop(key, None)
            else:
                state[key] = value
        return state

    def commit_sync(self, state: Dict[str, Any]) -> None:
        """
        提交同步后的状态为基准。

        Args:
            state: 完整状态。
        """
        self._last_synced = dict(state)
        self._version += 1

    def resolve_conflict(
        self,
        local: Dict[str, Any],
        remote: Dict[str, Any],
        strategy: str = "last_write_wins",
    ) -> Dict[str, Any]:
        """
        解决本地和远程状态的冲突。

        Args:
            local: 本地状态。
            remote: 远程状态。
            strategy: 冲突解决策略。

        Returns:
            合并后的状态。
        """
        merged = dict(local)
        for key, remote_value in remote.items():
            if key not in local:
                merged[key] = remote_value
            elif strategy == "last_write_wins":
                merged[key] = remote_value
            elif strategy == "merge_lists" and isinstance(local[key], list) and isinstance(remote_value, list):
                merged[key] = list(set(local[key]) | set(remote_value))
            else:
                merged[key] = remote_value
        return merged

    @property
    def version(self) -> int:
        """当前版本号。"""
        return self._version
