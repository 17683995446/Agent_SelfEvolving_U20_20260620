"""
知识图谱模块测试。

覆盖：实体添加、关系添加、查询、路径查找、类型过滤、三元组导出。
"""

import pytest

from agent_core.memory.knowledge_graph import KnowledgeGraph


class TestKnowledgeGraph:
    """KnowledgeGraph测试类。"""

    @pytest.fixture
    def graph(self):
        """创建知识图谱实例。"""
        return KnowledgeGraph()

    def test_add_and_get_entity(self, graph):
        """测试添加和获取实体。"""
        graph.add_entity("e1", "person", {"name": "Alice"})
        entity = graph.get_entity("e1")
        assert entity["type"] == "person"
        assert entity["attributes"]["name"] == "Alice"

    def test_add_relation(self, graph):
        """测试添加关系。"""
        graph.add_entity("e1", "person")
        graph.add_entity("e2", "company")
        graph.add_relation("e1", "works_for", "e2")
        rels = graph.get_relations("e1")
        assert len(rels) == 1
        assert rels[0] == ("e1", "works_for", "e2")

    def test_get_relations_filtered(self, graph):
        """测试按类型过滤关系。"""
        graph.add_entity("e1", "person")
        graph.add_entity("e2", "company")
        graph.add_entity("e3", "company")
        graph.add_relation("e1", "works_for", "e2")
        graph.add_relation("e1", "owns", "e3")
        rels = graph.get_relations("e1", "works_for")
        assert len(rels) == 1
        assert rels[0][1] == "works_for"

    def test_find_path_direct(self, graph):
        """测试直接路径查找。"""
        graph.add_entity("a", "x")
        graph.add_entity("b", "x")
        graph.add_relation("a", "link", "b")
        paths = graph.find_path("a", "b")
        assert len(paths) == 1
        assert paths[0] == [("a", "link", "b")]

    def test_find_path_indirect(self, graph):
        """测试间接路径查找。"""
        graph.add_entity("a", "x")
        graph.add_entity("b", "x")
        graph.add_entity("c", "x")
        graph.add_relation("a", "link", "b")
        graph.add_relation("b", "link", "c")
        paths = graph.find_path("a", "c")
        assert len(paths) == 1
        assert len(paths[0]) == 2

    def test_find_path_max_depth(self, graph):
        """测试最大深度限制。"""
        graph.add_entity("a", "x")
        graph.add_entity("b", "x")
        graph.add_entity("c", "x")
        graph.add_relation("a", "link", "b")
        graph.add_relation("b", "link", "c")
        paths = graph.find_path("a", "c", max_depth=1)
        assert len(paths) == 0

    def test_get_entities_by_type(self, graph):
        """测试按类型获取实体。"""
        graph.add_entity("e1", "person")
        graph.add_entity("e2", "person")
        graph.add_entity("e3", "company")
        persons = graph.get_entities_by_type("person")
        assert set(persons) == {"e1", "e2"}

    def test_export_triples(self, graph):
        """测试三元组导出。"""
        graph.add_entity("a", "x")
        graph.add_entity("b", "x")
        graph.add_relation("a", "link", "b")
        triples = graph.export_triples()
        assert triples == [("a", "link", "b")]
