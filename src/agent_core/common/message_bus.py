"""
消息总线模块。

多Agent协作的核心通信基础设施，支持发布-订阅模式。

第一性原理：
- 大脑皮层通过神经递质广播信号
- 发布-订阅模式解耦发送者与接收者
- 异步消息队列避免阻塞
"""

import asyncio
import json
import sqlite3
import threading
import time
from typing import Any, Callable, Dict, List, Tuple

from agent_core.common.logger import get_logger


class MessageBus:
    """
    消息总线实现。

    单例模式，全局统一消息通道。
    """

    _instance: "MessageBus" = None  # type: ignore[assignment]

    def __new__(cls) -> "MessageBus":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup()
        return cls._instance

    def _setup(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._logger = get_logger()
        self._db_path = "message_bus.db"
        # Bug36修复：_subscribers并发读写需要锁保护
        self._subscribers_lock = threading.RLock()
        # Bug37修复：复用SQLite连接，避免每次操作新建/关闭导致并发锁冲突
        self._db_lock = threading.Lock()
        self._db_conn: sqlite3.Connection = None
        self._init_db()

    def _init_db(self) -> None:
        # Bug37修复：使用持久连接，WAL模式 + busy_timeout
        self._db_conn = sqlite3.connect(
            self._db_path, timeout=5.0, check_same_thread=False
        )
        self._db_conn.execute("PRAGMA journal_mode=WAL")
        self._db_conn.execute("PRAGMA busy_timeout=5000")
        self._db_conn.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "topic TEXT NOT NULL,"
            "payload TEXT NOT NULL,"
            "created_at REAL NOT NULL,"
            "delivered INTEGER DEFAULT 0"
            ")"
        )
        self._db_conn.commit()

    def subscribe(self, topic: str, callback: Callable[[Any], None]) -> None:
        """订阅主题。"""
        # Bug36修复：用锁保护_subscribers写操作
        with self._subscribers_lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            self._subscribers[topic].append(callback)
        self._logger.debug(f"[MessageBus] Subscribed to {topic}")

    def publish(self, topic: str, message: Any) -> None:
        """发布消息，持久化后同步分发并标记已投递。"""
        msg_id = self._persist_message(topic, message)
        self._dispatch_sync(topic, message)
        self._ack_message(msg_id)

    def _dispatch_sync(self, topic: str, message: Any) -> None:
        """同步分发消息给订阅者。"""
        # Bug36修复：用锁保护_subscribers读操作，复制列表避免迭代时修改
        with self._subscribers_lock:
            callbacks = list(self._subscribers.get(topic, []))
        for callback in callbacks:
            try:
                callback(message)
            except Exception as exc:
                self._logger.error(
                    f"[MessageBus] Sync callback error: {exc}"
                )

    def _persist_message(self, topic: str, message: Any) -> int:
        """持久化消息，返回消息 ID。"""
        try:
            payload = json.dumps(message, default=str)
            # Bug37修复：用锁保护数据库写入，复用连接
            with self._db_lock:
                cursor = self._db_conn.execute(
                    "INSERT INTO messages (topic, payload, created_at) "
                    "VALUES (?, ?, ?)",
                    (topic, payload, time.time()),
                )
                self._db_conn.commit()
                msg_id = cursor.lastrowid
            return msg_id
        except Exception as exc:
            self._logger.error(f"[MessageBus] Persist failed: {exc}")
            return -1

    async def start(self) -> None:
        """启动消息分发循环，恢复未消费消息。"""
        self._running = True
        await self._recover_messages()
        self._logger.info("[MessageBus] Started")
        while self._running:
            try:
                msg_id, topic, message = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                await self._dispatch(topic, message)
                self._ack_message(msg_id)
            except asyncio.TimeoutError:
                continue

    async def _recover_messages(self) -> None:
        messages = self._load_pending()
        for msg_id, topic, payload in messages:
            await self._queue.put((msg_id, topic, payload))

    def _load_pending(self) -> List[Tuple[int, str, Any]]:
        try:
            # Bug37修复：用锁保护数据库读取
            with self._db_lock:
                rows = self._db_conn.execute(
                    "SELECT id, topic, payload FROM messages ORDER BY id"
                ).fetchall()
            return [(r[0], r[1], json.loads(r[2])) for r in rows]
        except Exception as exc:
            self._logger.error(f"[MessageBus] Recover failed: {exc}")
            return []

    async def _dispatch(self, topic: str, message: Any) -> None:
        # Bug36修复：用锁保护_subscribers读操作，复制列表避免迭代时修改
        with self._subscribers_lock:
            callbacks = list(self._subscribers.get(topic, []))
        for callback in callbacks:
            try:
                callback(message)
            except Exception as exc:
                self._logger.error(f"[MessageBus] Callback error: {exc}")

    def _ack_message(self, msg_id: int) -> None:
        """按消息 ID 删除已投递消息。"""
        if msg_id < 0:
            return
        try:
            # Bug37修复：用锁保护数据库删除，复用连接
            with self._db_lock:
                self._db_conn.execute(
                    "DELETE FROM messages WHERE id = ?", (msg_id,)
                )
                self._db_conn.commit()
        except Exception as exc:
            self._logger.error(f"[MessageBus] Ack failed: {exc}")

    async def stop(self) -> None:
        """停止消息总线。"""
        self._running = False
        # Bug37修复：关闭持久连接
        if self._db_conn is not None:
            try:
                self._db_conn.close()
            except Exception:
                pass
            self._db_conn = None
        self._logger.info("[MessageBus] Stopped")


def get_message_bus() -> MessageBus:
    """
    获取消息总线实例。

    Returns:
        MessageBus实例。
    """
    return MessageBus()
