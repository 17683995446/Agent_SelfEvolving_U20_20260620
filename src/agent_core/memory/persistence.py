"""
持久化存储模块。

支持经验、配置、运行时状态的序列化与恢复。
使用SQLite避免外部依赖，遵循第一性原理：
- 记忆必须可持久，否则系统重启即失忆
- 简单结构化存储优于复杂数据库
"""

import contextlib
import errno
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import numpy as np

from agent_core.common.data_contracts import (
    DriveSignals,
    EnvironmentState,
    ErrorMetrics,
    Experience,
    PredictionResult,
    Task,
)
from agent_core.common.logger import get_logger


@contextlib.contextmanager
def _db_connection(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

_SQL_CREATE_EXPERIENCES = """
CREATE TABLE IF NOT EXISTS experiences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    feature_vector TEXT NOT NULL,
    raw_sensors TEXT NOT NULL,
    prediction TEXT NOT NULL,
    drives TEXT NOT NULL,
    task TEXT,
    result TEXT NOT NULL,
    error TEXT NOT NULL,
    priority REAL NOT NULL
)
"""
_SQL_CREATE_CONFIG = """
CREATE TABLE IF NOT EXISTS config_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    config TEXT NOT NULL
)
"""
_SQL_CREATE_RUNTIME = """
CREATE TABLE IF NOT EXISTS runtime_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at REAL NOT NULL
)
"""
_SQL_INSERT_EXPERIENCE = """
INSERT INTO experiences
(timestamp, feature_vector, raw_sensors, prediction,
 drives, task, result, error, priority)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
_SQL_SELECT_EXPERIENCES = """
SELECT timestamp, feature_vector, raw_sensors, prediction,
       drives, task, result, error, priority
FROM experiences
ORDER BY timestamp DESC
LIMIT ? OFFSET ?
"""
_SQL_INSERT_CONFIG = """
INSERT INTO config_snapshots (timestamp, config)
VALUES (?, ?)
"""
_SQL_SELECT_LATEST_CONFIG = """
SELECT config FROM config_snapshots
ORDER BY timestamp DESC
LIMIT 1
"""
_SQL_UPSERT_RUNTIME = """
INSERT INTO runtime_state (key, value, updated_at)
VALUES (?, ?, ?)
ON CONFLICT(key) DO UPDATE SET
    value=excluded.value,
    updated_at=excluded.updated_at
"""
_SQL_SELECT_RUNTIME = "SELECT key, value FROM runtime_state"
_SQL_DELETE_ALL = [
    "DELETE FROM experiences",
    "DELETE FROM config_snapshots",
    "DELETE FROM runtime_state",
]


class PersistenceManager:
    """
    持久化管理器。

    负责经验、配置、状态的SQLite持久化。
    """

    def __init__(self, db_path: str = "agent_memory.db") -> None:
        self._db_path = Path(db_path)
        self._logger = get_logger()
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """确保数据库表结构存在。"""
        try:
            with _db_connection(self._db_path) as conn:
                conn.execute(_SQL_CREATE_EXPERIENCES)
                conn.execute(_SQL_CREATE_CONFIG)
                conn.execute(_SQL_CREATE_RUNTIME)
            self._logger.info("[PersistenceManager] Tables ensured")
        except (sqlite3.OperationalError, OSError) as exc:
            self._logger.error(
                f"[PersistenceManager] Cannot ensure tables: {exc}"
            )

    def _handle_disk_error(self, exc: Exception) -> None:
        """处理磁盘相关错误。"""
        if isinstance(exc, sqlite3.OperationalError):
            self._logger.error(
                f"[PersistenceManager] Database error: {exc}"
            )
        elif isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
            self._logger.error(
                "[PersistenceManager] Disk full, writes suspended"
            )
        elif isinstance(exc, OSError) and exc.errno == errno.EACCES:
            self._logger.error(
                "[PersistenceManager] Permission denied"
            )
        else:
            self._logger.error(f"[PersistenceManager] Unexpected: {exc}")

    def save_experiences(self, experiences: List[Experience]) -> None:
        """批量保存经验。

        Raises:
            sqlite3.OperationalError: 数据库操作失败时重新抛出，避免静默数据丢失。
            OSError: 磁盘I/O失败时重新抛出。
        """
        if not experiences:
            return
        rows = self._build_rows(experiences)
        try:
            self._insert_rows(rows)
            self._logger.info(
                f"[PersistenceManager] Saved {len(experiences)} experiences"
            )
        except (sqlite3.OperationalError, OSError) as exc:
            # Bug26修复：记录日志后重新抛出，避免调用方误认为成功而清空内存数据
            self._handle_disk_error(exc)
            raise

    def _build_rows(self, experiences: List[Experience]) -> List[tuple]:
        rows: List[tuple] = []
        for exp in experiences:
            rows.append(self._encode_experience(exp))
        return rows

    def _insert_rows(self, rows: List[tuple]) -> None:
        with _db_connection(self._db_path) as conn:
            conn.executemany(_SQL_INSERT_EXPERIENCE, rows)

    def load_experiences(
        self, limit: int = 1000, offset: int = 0
    ) -> List[Experience]:
        """加载经验。"""
        rows = self._fetch_rows(limit, offset)
        experiences = self._decode_rows(rows)
        self._logger.info(
            f"[PersistenceManager] Loaded {len(experiences)} experiences"
        )
        return experiences

    def _fetch_rows(self, limit: int, offset: int) -> List[tuple]:
        with _db_connection(self._db_path) as conn:
            cursor = conn.execute(_SQL_SELECT_EXPERIENCES, (limit, offset))
            return cursor.fetchall()

    def _decode_rows(self, rows: List[tuple]) -> List[Experience]:
        experiences: List[Experience] = []
        for row in rows:
            experiences.append(_decode_experience(row))
        return experiences

    def save_config(self, config: Dict[str, Any]) -> None:
        """保存配置快照。"""
        payload = json.dumps(config, default=str)
        self._insert_config(payload)
        self._logger.info("[PersistenceManager] Config snapshot saved")

    def _insert_config(self, payload: str) -> None:
        with _db_connection(self._db_path) as conn:
            conn.execute(_SQL_INSERT_CONFIG, (time.time(), payload))

    def load_latest_config(self) -> Optional[Dict[str, Any]]:
        """加载最新配置快照。"""
        row = self._fetch_latest_config()
        if row is None:
            return None
        return json.loads(row)

    def _fetch_latest_config(self) -> Optional[str]:
        with _db_connection(self._db_path) as conn:
            cursor = conn.execute(_SQL_SELECT_LATEST_CONFIG)
            result = cursor.fetchone()
        if result is None:
            return None
        return result[0]

    def save_runtime_state(self, state: Dict[str, Any]) -> None:
        """保存运行时状态。"""
        now = time.time()
        with _db_connection(self._db_path) as conn:
            for key, value in state.items():
                payload = json.dumps(value, default=str)
                conn.execute(_SQL_UPSERT_RUNTIME, (key, payload, now))
        self._logger.debug("[PersistenceManager] Runtime state saved")

    def load_runtime_state(self) -> Dict[str, Any]:
        """加载运行时状态。"""
        with _db_connection(self._db_path) as conn:
            cursor = conn.execute(_SQL_SELECT_RUNTIME)
            rows = cursor.fetchall()
        return self._parse_state_rows(rows)

    def _parse_state_rows(self, rows: List[tuple]) -> Dict[str, Any]:
        state: Dict[str, Any] = {}
        for key, value in rows:
            state[key] = json.loads(value)
        return state

    def clear_all(self) -> None:
        """清空所有持久化数据。"""
        with _db_connection(self._db_path) as conn:
            for sql in _SQL_DELETE_ALL:
                conn.execute(sql)
        self._logger.warning("[PersistenceManager] All data cleared")

    def _encode_experience(self, exp: Experience) -> tuple:
        return (
            exp.timestamp,
            _encode_array(exp.state.feature_vector),
            json.dumps(exp.state.raw_sensors, default=str),
            _encode_prediction(exp.prediction),
            _encode_drives(exp.drive_signals),
            _encode_task(exp.selected_task),
            json.dumps(exp.execution_result, default=str),
            _encode_error(exp.error_metrics),
            exp.priority,
        )


def _encode_array(arr: np.ndarray) -> str:
    """编码numpy数组为JSON字符串。"""
    return json.dumps(arr.tolist())


def _decode_array(data: str) -> np.ndarray:
    """解码JSON字符串为numpy数组。"""
    return np.array(json.loads(data), dtype=np.float32)


def _encode_prediction(pred: PredictionResult) -> str:
    """编码预测结果。"""
    return json.dumps(
        {
            "low_level": pred.low_level.tolist(),
            "mid_level": pred.mid_level.tolist(),
            "high_level": pred.high_level.tolist(),
            "ensemble": pred.ensemble.tolist(),
            "confidence": pred.confidence,
        }
    )


def _encode_drives(drives: DriveSignals) -> str:
    """编码驱力信号。"""
    return json.dumps(
        {
            "safety_reward": drives.safety_reward,
            "gain_reward": drives.gain_reward,
            "efficiency_reward": drives.efficiency_reward,
            "safety_gap": drives.safety_gap,
            "gain_gap": drives.gain_gap,
            "efficiency_gap": drives.efficiency_gap,
            "weights": drives.weights,
            "total_reward": drives.total_reward,
        }
    )


def _encode_task(task: Optional[Task]) -> Optional[str]:
    """编码任务对象。"""
    if task is None:
        return None
    return json.dumps(
        {
            "task_id": task.task_id,
            "name": task.name,
            "task_type": task.task_type,
            "priority": task.priority,
            "expected_reward": task.expected_reward,
            "expected_cost": task.expected_cost,
            "novelty_score": task.novelty_score,
            "params": task.params,
            "created_at": task.created_at,
        }
    )


def _encode_error(error: ErrorMetrics) -> str:
    """编码误差指标。"""
    return json.dumps(
        {
            "mse": error.mse,
            "mae": error.mae,
            "mape": error.mape,
            "direction_accuracy": error.direction_accuracy,
            "error_vector": error.error_vector.tolist(),
        }
    )


def _decode_experience(row: tuple) -> Experience:
    """解码数据库行为经验对象。"""
    (
        timestamp,
        feature_vector,
        raw_sensors,
        prediction,
        drives,
        task,
        result,
        error,
        priority,
    ) = row
    state = _build_state(timestamp, raw_sensors, feature_vector)
    pred = _build_prediction(prediction)
    drive_signals = _build_drives(drives)
    selected_task = _decode_task(task)
    error_metrics = _build_error(error)
    return Experience(
        timestamp=timestamp,
        state=state,
        prediction=pred,
        drive_signals=drive_signals,
        selected_task=selected_task,
        execution_result=json.loads(result),
        error_metrics=error_metrics,
        priority=priority,
    )


def _build_state(
    timestamp: float, raw_sensors: str, feature_vector: str
) -> EnvironmentState:
    return EnvironmentState(
        timestamp=timestamp,
        raw_sensors=json.loads(raw_sensors),
        feature_vector=_decode_array(feature_vector),
    )


def _build_prediction(prediction: str) -> PredictionResult:
    pred_data = json.loads(prediction)
    return PredictionResult(
        low_level=_decode_array(json.dumps(pred_data["low_level"])),
        mid_level=_decode_array(json.dumps(pred_data["mid_level"])),
        high_level=_decode_array(json.dumps(pred_data["high_level"])),
        ensemble=_decode_array(json.dumps(pred_data["ensemble"])),
        confidence=pred_data["confidence"],
    )


def _build_drives(drives: str) -> DriveSignals:
    drives_data = json.loads(drives)
    return DriveSignals(
        safety_reward=drives_data["safety_reward"],
        gain_reward=drives_data["gain_reward"],
        efficiency_reward=drives_data["efficiency_reward"],
        safety_gap=drives_data["safety_gap"],
        gain_gap=drives_data["gain_gap"],
        efficiency_gap=drives_data["efficiency_gap"],
        weights=drives_data["weights"],
        total_reward=drives_data["total_reward"],
    )


def _build_error(error: str) -> ErrorMetrics:
    error_data = json.loads(error)
    return ErrorMetrics(
        mse=error_data["mse"],
        mae=error_data["mae"],
        mape=error_data["mape"],
        direction_accuracy=error_data["direction_accuracy"],
        error_vector=_decode_array(json.dumps(error_data["error_vector"])),
    )


def _decode_task(data: Optional[str]) -> Optional[Task]:
    """解码任务对象。"""
    if data is None:
        return None
    task_data = json.loads(data)
    return Task(
        task_id=task_data["task_id"],
        name=task_data["name"],
        task_type=task_data["task_type"],
        priority=task_data["priority"],
        expected_reward=task_data["expected_reward"],
        expected_cost=task_data["expected_cost"],
        novelty_score=task_data["novelty_score"],
        params=task_data.get("params", {}),
        created_at=task_data.get("created_at", 0.0),
    )
