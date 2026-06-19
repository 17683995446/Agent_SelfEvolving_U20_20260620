"""
神经符号推理模块测试。

覆盖：逻辑规则、神经谓词、前向链推理、混合推理。
"""

import numpy as np
import pytest

from agent_core.task.neural_symbolic import (
    LogicRule,
    NeuralPredicate,
    NeuralSymbolicReasoner,
)


class TestLogicRule:
    """LogicRule测试类。"""

    def test_evaluate_all_premises_true(self):
        """测试所有前提为真时触发。"""
        rule = LogicRule("r1", ["a", "b"], "c", 0.9)
        triggered, confidence = rule.evaluate({"a": True, "b": True})
        assert triggered is True
        assert confidence == 0.9

    def test_evaluate_missing_premise(self):
        """测试缺少前提时不触发。"""
        rule = LogicRule("r1", ["a", "b"], "c")
        triggered, _ = rule.evaluate({"a": True})
        assert triggered is False

    def test_evaluate_premise_false(self):
        """测试前提为假时不触发。"""
        rule = LogicRule("r1", ["a"], "b")
        triggered, _ = rule.evaluate({"a": False})
        assert triggered is False

    def test_getters(self):
        """测试获取器。"""
        rule = LogicRule("r1", ["a"], "b", 0.8)
        assert rule.get_name() == "r1"
        assert rule.get_conclusion() == "b"
        assert rule.get_premises() == ["a"]


class TestNeuralPredicate:
    """NeuralPredicate测试类。"""

    def test_evaluate_zero_weights(self):
        """测试零权重时输出0.5。"""
        predicate = NeuralPredicate("p1", 3)
        result = predicate.evaluate(np.array([1.0, 2.0, 3.0]))
        assert result == pytest.approx(0.5, abs=0.01)

    def test_evaluate_positive_weights(self):
        """测试正权重时输出大于0.5。"""
        weights = np.array([1.0, 1.0, 1.0])
        predicate = NeuralPredicate("p1", 3, weights)
        result = predicate.evaluate(np.array([1.0, 1.0, 1.0]))
        assert result > 0.5

    def test_evaluate_wrong_dim(self):
        """测试维度不匹配时返回0。"""
        predicate = NeuralPredicate("p1", 3)
        result = predicate.evaluate(np.array([1.0, 2.0]))
        assert result == 0.0

    def test_update_weights(self):
        """测试权重更新。"""
        predicate = NeuralPredicate("p1", 2)
        old_weights = predicate._weights.copy()
        predicate.update_weights(np.array([0.1, 0.1]), 0.1)
        assert not np.array_equal(predicate._weights, old_weights)

    def test_get_name(self):
        """测试获取名称。"""
        predicate = NeuralPredicate("p1", 2)
        assert predicate.get_name() == "p1"


class TestNeuralSymbolicReasoner:
    """NeuralSymbolicReasoner测试类。"""

    @pytest.fixture
    def reasoner(self):
        """创建推理器实例。"""
        return NeuralSymbolicReasoner()

    def test_add_rule(self, reasoner):
        """测试添加规则。"""
        reasoner.add_rule(LogicRule("r1", ["a"], "b"))
        assert reasoner.get_rule_count() == 1

    def test_add_predicate(self, reasoner):
        """测试添加谓词。"""
        reasoner.add_predicate(NeuralPredicate("p1", 2))
        assert reasoner.get_predicate_count() == 1

    def test_reason_chain(self, reasoner):
        """测试规则链推理。"""
        reasoner.add_rule(LogicRule("r1", ["a"], "b"))
        reasoner.add_rule(LogicRule("r2", ["b"], "c"))
        reasoner.set_fact("a", True)
        results = reasoner.reason()
        assert "b" in results
        assert "c" in results
        assert results["c"][0] is True

    def test_reason_no_trigger(self, reasoner):
        """测试无触发规则。"""
        reasoner.add_rule(LogicRule("r1", ["a"], "b"))
        results = reasoner.reason()
        assert len(results) == 0

    def test_hybrid_infer(self, reasoner):
        """测试混合推理。"""
        weights = np.array([1.0, 1.0])
        reasoner.add_predicate(NeuralPredicate("p1", 2, weights))
        reasoner.add_rule(LogicRule("r1", ["p1"], "result", 0.9))
        inputs = {"p1": np.array([1.0, 1.0])}
        results = reasoner.hybrid_infer(inputs)
        assert "result" in results
        assert results["result"] > 0.0

    def test_clear_facts(self, reasoner):
        """测试清空事实。"""
        reasoner.set_fact("a", True)
        reasoner.clear_facts()
        results = reasoner.reason()
        assert len(results) == 0

    def test_evaluate_predicate_missing(self, reasoner):
        """测试评估不存在的谓词。"""
        result = reasoner.evaluate_predicate("missing", np.array([1.0]))
        assert result == 0.0
