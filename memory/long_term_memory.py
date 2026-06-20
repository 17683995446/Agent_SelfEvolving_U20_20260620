"""
长期记忆系统（向量数据库）

第一性原理：人脑通过海马体-皮层交互实现记忆的长期存储。
- 海马体：快速索引、模式分离（相似记忆不混淆）
- 皮层：分布式存储、语义压缩（提取共性）

实现：
1. SQLite持久化（皮层存储）
2. 向量索引（HNSW近似最近邻，模拟海马体索引）
3. 记忆压缩（聚类去冗余，模拟睡眠中的记忆重放）
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from core import MemoryEntry, MemoryType


def _stable_index_id(entry_id: str) -> int:
    """
    计算稳定的索引ID。

    使用MD5保证跨进程/跨重启稳定（Python内置hash()受PYTHONHASHSEED影响，
    不同进程对同一字符串会得到不同hash值，导致重启后索引失效）。
    """
    digest = hashlib.md5(str(entry_id).encode("utf-8")).hexdigest()
    return int(digest, 16) % (2**31)


class VectorIndex:
    """
    向量索引（简化版HNSW）

    第一性原理：海马体的CA3区通过循环连接实现模式完成（pattern completion）。
    向量索引支持基于相似性的快速检索，即使查询不完全匹配也能找到相关记忆。
    """

    def __init__(self, dim: int, ef_construction: int = 50, m: int = 8):
        self.dim = dim
        self.ef_construction = ef_construction
        self.m = m

        # 入口点
        self.entry_point: Optional[int] = None

        # 节点：id -> (vector, neighbors)
        self.nodes: Dict[int, Tuple[np.ndarray, List[int]]] = {}

        # 层级（简化：单层图）
        self._lock = threading.RLock()

    def add(self, entry_id: int, vector: np.ndarray) -> None:
        """添加向量到索引"""
        with self._lock:
            vector = vector.copy()
            if entry_id in self.nodes:
                return

            # 找到最近的M个邻居
            neighbors = self._search_neighbors(vector, self.m)

            self.nodes[entry_id] = (vector, neighbors)

            # 双向连接
            for nid in neighbors:
                if nid in self.nodes:
                    nvec, nneighbors = self.nodes[nid]
                    if entry_id not in nneighbors:
                        nneighbors.append(entry_id)
                        if len(nneighbors) > self.m * 2:
                            # 裁剪最远邻居
                            dists = [(n, np.linalg.norm(nvec - self.nodes[n][0])) for n in nneighbors]
                            dists.sort(key=lambda x: x[1])
                            nneighbors[:] = [n for n, _ in dists[:self.m * 2]]

            if self.entry_point is None:
                self.entry_point = entry_id

    def search(self, query: np.ndarray, k: int = 5) -> List[Tuple[int, float]]:
        """
        近似最近邻搜索

        Returns:
            List[(entry_id, distance)]，按距离升序
        """
        with self._lock:
            if not self.nodes:
                return []

            query = query.flatten()

            # 贪心搜索
            visited = set()
            candidates = []

            # 从入口点开始
            if self.entry_point is not None and self.entry_point in self.nodes:
                candidates.append(self.entry_point)

            best = []
            while candidates:
                current = candidates.pop(0)
                if current in visited:
                    continue
                visited.add(current)

                vec, neighbors = self.nodes[current]
                dist = np.linalg.norm(vec - query)
                best.append((current, dist))

                for nid in neighbors:
                    if nid not in visited:
                        candidates.append(nid)

            # 返回最近的k个
            best.sort(key=lambda x: x[1])
            return best[:k]

    def _search_neighbors(self, vector: np.ndarray, k: int) -> List[int]:
        """为新节点找到k个最近邻居"""
        if not self.nodes:
            return []

        dists = []
        for nid, (vec, _) in self.nodes.items():
            d = np.linalg.norm(vec - vector)
            dists.append((nid, d))

        dists.sort(key=lambda x: x[1])
        return [nid for nid, _ in dists[:k]]

    def remove(self, entry_id: int) -> bool:
        """从索引中移除"""
        with self._lock:
            if entry_id not in self.nodes:
                return False
            del self.nodes[entry_id]
            # 清理邻居引用
            for nid, (vec, neighbors) in self.nodes.items():
                if entry_id in neighbors:
                    neighbors.remove(entry_id)
            return True

    def clear(self) -> None:
        """清空索引"""
        with self._lock:
            self.nodes.clear()
            self.entry_point = None


class LongTermMemory:
    """
    长期记忆系统

    结合SQLite持久化和向量索引，支持语义检索。
    """

    def __init__(self, db_path: str = "./data/long_term_memory.db", vector_dim: int = 28):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.vector_dim = vector_dim

        # 向量索引
        self.vector_index = VectorIndex(dim=vector_dim)

        # 数据库连接（线程本地）
        self._local = threading.local()
        self._init_db()

        # 加载现有数据到索引
        self._load_index()

    def _get_conn(self) -> sqlite3.Connection:
        """获取线程本地连接"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path))
        return self._local.conn

    def _init_db(self) -> None:
        """初始化数据库表"""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                memory_type TEXT,
                value_score REAL DEFAULT 0.5,
                timestamp REAL,
                access_count INTEGER DEFAULT 0,
                last_accessed REAL,
                vector BLOB,
                index_id INTEGER
            )
        """)
        # 兼容旧库：若旧表无 index_id 列则补加
        try:
            conn.execute("SELECT index_id FROM memories LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE memories ADD COLUMN index_id INTEGER")
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON memories(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_value ON memories(value_score)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_index_id ON memories(index_id)
        """)
        conn.commit()

    def _load_index(self) -> None:
        """将数据库中的向量加载到索引"""
        conn = self._get_conn()
        cursor = conn.execute("SELECT id, vector FROM memories WHERE vector IS NOT NULL")
        for row in cursor:
            entry_id, vec_blob = row
            vector = np.frombuffer(vec_blob, dtype=np.float32)
            if vector.shape[0] == self.vector_dim:
                self.vector_index.add(_stable_index_id(entry_id), vector)

    def store(self, entry: MemoryEntry) -> str:
        """
        存储记忆到长期记忆

        Precondition:
            - entry.id 不为空
        Postcondition:
            - 记忆被持久化到SQLite
            - 向量被添加到索引
        """
        conn = self._get_conn()

        # 提取向量（如果content是numpy数组）
        vector_blob = None
        if isinstance(entry.content, np.ndarray):
            vector_blob = entry.content.astype(np.float32).tobytes()
            vector = entry.content.astype(np.float32)
        elif isinstance(entry.content, dict) and "state" in entry.content:
            state = entry.content["state"]
            if isinstance(state, list):
                vector = np.array(state, dtype=np.float32)
                vector_blob = vector.tobytes()
            else:
                vector = None
        else:
            vector = None

        # 计算稳定的索引ID（避免hash()跨进程不稳定）
        index_id = _stable_index_id(entry.id)

        conn.execute(
            """
            INSERT OR REPLACE INTO memories
            (id, content, memory_type, value_score, timestamp, access_count, last_accessed, vector, index_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                json.dumps(entry.content, default=str),
                entry.memory_type.value if entry.memory_type else None,
                entry.value_score,
                entry.timestamp,
                0,
                entry.timestamp,
                vector_blob,
                index_id,
            ),
        )
        conn.commit()

        # 添加到向量索引
        if vector is not None and vector.shape[0] == self.vector_dim:
            self.vector_index.add(index_id, vector)

        return entry.id

    def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        """通过ID检索记忆"""
        conn = self._get_conn()
        cursor = conn.execute("SELECT * FROM memories WHERE id = ?", (entry_id,))
        row = cursor.fetchone()

        if row is None:
            return None

        # 更新访问统计
        conn.execute(
            "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
            (time.time(), entry_id),
        )
        conn.commit()

        return self._row_to_entry(row)

    def search_similar(self, query_vector: np.ndarray, k: int = 5) -> List[Tuple[MemoryEntry, float]]:
        """
        相似性搜索

        Args:
            query_vector: 查询向量
            k: 返回结果数量

        Returns:
            List[(MemoryEntry, distance)]
        """
        results = self.vector_index.search(query_vector, k)
        entries = []
        for index_id, dist in results:
            # 通过index_id直接查询（已建索引，O(log n)）
            conn = self._get_conn()
            cursor = conn.execute("SELECT * FROM memories WHERE index_id = ? LIMIT 1", (index_id,))
            row = cursor.fetchone()
            if row is not None:
                entry = self._row_to_entry(row)
                entries.append((entry, dist))
        return entries

    def get_by_time_range(self, start: float, end: float, limit: int = 100) -> List[MemoryEntry]:
        """按时间范围检索"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM memories WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp DESC LIMIT ?",
            (start, end, limit),
        )
        return [self._row_to_entry(row) for row in cursor.fetchall()]

    def get_high_value(self, min_score: float = 0.7, limit: int = 50) -> List[MemoryEntry]:
        """获取高价值记忆"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT * FROM memories WHERE value_score >= ? ORDER BY value_score DESC LIMIT ?",
            (min_score, limit),
        )
        return [self._row_to_entry(row) for row in cursor.fetchall()]

    def compress(self, threshold: float = 0.95) -> int:
        """
        记忆压缩（去冗余）

        删除与已有记忆过于相似的新记忆，模拟睡眠中的记忆巩固。

        Returns:
            删除的记忆数量
        """
        conn = self._get_conn()
        cursor = conn.execute("SELECT id, vector FROM memories WHERE vector IS NOT NULL ORDER BY timestamp")

        to_delete = []
        seen_vectors = []

        for row in cursor:
            entry_id, vec_blob = row
            vector = np.frombuffer(vec_blob, dtype=np.float32)

            # 检查是否与已有记忆过于相似
            is_redundant = False
            for seen in seen_vectors:
                similarity = np.dot(vector, seen) / (np.linalg.norm(vector) * np.linalg.norm(seen) + 1e-8)
                if similarity > threshold:
                    is_redundant = True
                    break

            if is_redundant:
                to_delete.append(entry_id)
            else:
                seen_vectors.append(vector)

        # 删除冗余记忆
        for entry_id in to_delete:
            conn.execute("DELETE FROM memories WHERE id = ?", (entry_id,))
            index_id = _stable_index_id(entry_id)
            self.vector_index.remove(index_id)

        conn.commit()
        return len(to_delete)

    def _row_to_entry(self, row) -> MemoryEntry:
        """数据库行转MemoryEntry"""
        return MemoryEntry(
            id=row[0],
            content=json.loads(row[1]),
            memory_type=MemoryType(row[2]) if row[2] else None,
            value_score=row[3],
            timestamp=row[4],
        )

    def count(self) -> int:
        """获取记忆总数"""
        conn = self._get_conn()
        cursor = conn.execute("SELECT COUNT(*) FROM memories")
        return cursor.fetchone()[0]

    def clear(self) -> None:
        """清空所有记忆"""
        conn = self._get_conn()
        conn.execute("DELETE FROM memories")
        conn.commit()
        self.vector_index.clear()
