"""
知识图谱模块。

实现实体关系抽取与存储，支持图遍历和查询。

第一性原理：
- 知识以实体和关系的形式组织，符合人类认知
- 图结构天然支持关联推理
- 增量构建，持续丰富
"""

from typing import Any, Dict, List, Optional, Set, Tuple

from agent_core.common.logger import get_logger


class KnowledgeGraph:
    """
    知识图谱。

    存储实体和关系，支持基本图操作。
    """

    def __init__(self) -> None:
        self._entities: Dict[str, Dict[str, Any]] = {}
        self._relations: Dict[str, List[Tuple[str, str]]] = {}
        self._logger = get_logger()

    def add_entity(
        self, entity_id: str, entity_type: str, attributes: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        添加实体。

        Args:
            entity_id: 实体唯一标识。
            entity_type: 实体类型。
            attributes: 实体属性。
        """
        self._entities[entity_id] = {
            "type": entity_type,
            "attributes": attributes or {},
        }

    def add_relation(
        self, from_id: str, relation_type: str, to_id: str
    ) -> None:
        """
        添加关系。

        Args:
            from_id: 起始实体ID。
            relation_type: 关系类型。
            to_id: 目标实体ID。
        """
        if relation_type not in self._relations:
            self._relations[relation_type] = []
        self._relations[relation_type].append((from_id, to_id))

    def get_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """获取实体信息。"""
        return self._entities.get(entity_id)

    def get_relations(
        self, entity_id: str, relation_type: Optional[str] = None
    ) -> List[Tuple[str, str, str]]:
        """
        获取实体的关系。

        Args:
            entity_id: 实体ID。
            relation_type: 关系类型过滤。

        Returns:
            (from_id, relation_type, to_id) 列表。
        """
        results: List[Tuple[str, str, str]] = []
        types = [relation_type] if relation_type else list(self._relations.keys())
        for rel_type in types:
            if rel_type not in self._relations:
                continue
            for from_id, to_id in self._relations[rel_type]:
                if from_id == entity_id or to_id == entity_id:
                    results.append((from_id, rel_type, to_id))
        return results

    def find_path(
        self, start: str, end: str, max_depth: int = 5
    ) -> List[List[Tuple[str, str, str]]]:
        """
        查找两实体间的路径。

        Args:
            start: 起始实体。
            end: 目标实体。
            max_depth: 最大深度。

        Returns:
            路径列表，每条路径是( from_id, relation_type, to_id )的列表。
        """
        paths: List[List[Tuple[str, str, str]]] = []
        visited: Set[str] = set()

        def dfs(current: str, path: List[Tuple[str, str, str]], depth: int) -> None:
            if depth > max_depth:
                return
            if current == end and path:
                paths.append(list(path))
                return
            visited.add(current)
            for rel_type in self._relations:
                for from_id, to_id in self._relations[rel_type]:
                    if from_id == current and to_id not in visited:
                        path.append((from_id, rel_type, to_id))
                        dfs(to_id, path, depth + 1)
                        path.pop()
            visited.discard(current)

        dfs(start, [], 0)
        return paths

    def get_entities_by_type(self, entity_type: str) -> List[str]:
        """按类型获取实体ID列表。"""
        return [
            eid for eid, info in self._entities.items()
            if info["type"] == entity_type
        ]

    def export_triples(self) -> List[Tuple[str, str, str]]:
        """
        导出所有三元组。

        Returns:
            (subject, predicate, object) 列表。
        """
        triples: List[Tuple[str, str, str]] = []
        for rel_type, pairs in self._relations.items():
            for from_id, to_id in pairs:
                triples.append((from_id, rel_type, to_id))
        return triples
