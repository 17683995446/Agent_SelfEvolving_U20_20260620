"""
短期记忆系统

第一性原理：人脑短期记忆容量有限（7±2个组块），持续时间短（秒到分钟）。
ShortTermMemory模拟这种有限容量、快速访问的记忆存储。
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from core import MemoryEntry, MemoryLevel, MemoryType
from core.interfaces import IMemory


class ShortTermMemory(IMemory):
    """
    短期记忆系统
    
    内存缓存 + SQLite持久化，支持价值评估和自动淘汰。
    """
    
    def __init__(self,
                 max_size: int = 10000,
                 db_path: str = "./data/memory.db",
                 max_db_rows: int = 50000,
                 cleanup_interval: int = 1000):
        """
        Args:
            max_size: 内存缓存最大条数
            db_path: SQLite数据库路径
            max_db_rows: SQLite最大行数（阶段7：防止磁盘无限增长）
            cleanup_interval: 每N次store触发一次清理
        """
        self.max_size = max_size
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_db_rows = max_db_rows
        self.cleanup_interval = cleanup_interval
        self._store_count = 0

        self._cache: Dict[str, MemoryEntry] = {}
        self._lock = threading.RLock()

        # 初始化数据库
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接（统一入口，便于排查连接泄漏）"""
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        """初始化SQLite数据库"""
        conn = None
        try:
            conn = self._get_conn()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS experiences (
                    id TEXT PRIMARY KEY,
                    content TEXT,
                    memory_type TEXT,
                    timestamp REAL,
                    value_score REAL,
                    access_count INTEGER,
                    tags TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON experiences(timestamp)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_value ON experiences(value_score)
            """)
            conn.commit()
        except Exception:
            pass
        finally:
            if conn is not None:
                conn.close()
    
    def store(self, entry: MemoryEntry) -> str:
        """存储记忆"""
        with self._lock:
            # 如果缓存已满，淘汰低价值记忆
            if len(self._cache) >= self.max_size:
                self._evict_lowest_value()

            self._cache[entry.id] = entry

            # 异步持久化到数据库
            self._persist_async(entry)

            # 阶段7：定期清理SQLite旧记录，防止磁盘无限增长
            self._store_count += 1
            if self._store_count >= self.cleanup_interval:
                self._store_count = 0
                self._cleanup_old_records()

            return entry.id
    
    def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        """检索记忆"""
        with self._lock:
            entry = self._cache.get(entry_id)
            if entry:
                entry.access_count += 1
                entry.last_accessed = time.time()
            return entry
    
    def retrieve_by_tags(self, tags: List[str], limit: int = 10) -> List[MemoryEntry]:
        """按标签检索"""
        with self._lock:
            results = []
            for entry in self._cache.values():
                if any(tag in entry.tags for tag in tags):
                    results.append(entry)
            
            # 按价值分数排序
            results.sort(key=lambda e: e.value_score, reverse=True)
            return results[:limit]
    
    def retrieve_high_value(self, threshold: float = 0.5, limit: int = 100) -> List[MemoryEntry]:
        """检索高价值记忆"""
        with self._lock:
            results = [
                entry for entry in self._cache.values()
                if entry.value_score >= threshold
            ]
            results.sort(key=lambda e: e.value_score, reverse=True)
            return results[:limit]
    
    def update_value(self, entry_id: str, value_score: float) -> bool:
        """更新记忆价值"""
        with self._lock:
            entry = self._cache.get(entry_id)
            if entry:
                entry.value_score = value_score
                return True
            return False
    
    def _evict_lowest_value(self) -> None:
        """淘汰最低价值的记忆"""
        if not self._cache:
            return
        
        lowest_id = min(self._cache.keys(), 
                       key=lambda k: self._cache[k].value_score)
        del self._cache[lowest_id]
    
    def _persist_async(self, entry: MemoryEntry) -> None:
        """异步持久化（简化版：直接同步写入）"""
        conn = None
        try:
            conn = self._get_conn()
            conn.execute("""
                INSERT OR REPLACE INTO experiences
                (id, content, memory_type, timestamp, value_score, access_count, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.id,
                str(entry.content)[:1000],  # 限制长度
                entry.memory_type.value,
                entry.timestamp,
                entry.value_score,
                entry.access_count,
                ','.join(entry.tags),
            ))
            conn.commit()
        except Exception:
            # 持久化失败不应影响主流程
            pass
        finally:
            if conn is not None:
                conn.close()

    def _cleanup_old_records(self) -> None:
        """清理SQLite旧记录（阶段7：防止磁盘无限增长）

        当行数超过 max_db_rows 时，按时间戳删除最旧的记录。
        """
        conn = None
        try:
            conn = self._get_conn()
            cursor = conn.execute("SELECT COUNT(*) FROM experiences")
            count = cursor.fetchone()[0]
            if count > self.max_db_rows:
                # 删除最旧的 (count - max_db_rows) 条记录
                excess = count - self.max_db_rows
                conn.execute("""
                    DELETE FROM experiences WHERE id IN (
                        SELECT id FROM experiences
                        ORDER BY timestamp ASC
                        LIMIT ?
                    )
                """, (excess,))
                conn.commit()
        except Exception:
            pass
        finally:
            if conn is not None:
                conn.close()

    def clear(self) -> None:
        """清空记忆"""
        with self._lock:
            self._cache.clear()
            conn = None
            try:
                conn = self._get_conn()
                conn.execute("DELETE FROM experiences")
                conn.commit()
            except Exception:
                pass
            finally:
                if conn is not None:
                    conn.close()
    
    def __len__(self) -> int:
        return len(self._cache)
