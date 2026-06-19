"""
可解释AI模块测试。

覆盖：决策步骤记录、特征重要性、解释生成。
"""

import pytest

from agent_core.task.explainability_engine import (
    DecisionStep,
    ExplainabilityEngine,
    FeatureImportance,
)


class TestDecisionStep:
    """DecisionStep测试类。"""

    def test_to_dict(self):
        """测试字典转换。"""
        step = DecisionStep("s1", "m1", {"a": 1}, {"b": 2}, "reason")
        d = step.to_dict()
        assert d["step_id"] == "s1"
        assert d["module"] == "m1"
        assert d["reasoning"] == "reason"

    def test_getters(self):
        """测试获取器。"""
        step = DecisionStep("s1", "m1", {}, {}, "r")
        assert step.get_module() == "m1"
        assert step.get_reasoning() == "r"


class TestFeatureImportance:
    """FeatureImportance测试类。"""

    def test_get_top_features(self):
        """测试获取 top 特征。"""
        fi = FeatureImportance()
        fi.set_score("f1", 0.9)
        fi.set_score("f2", -0.8)
        fi.set_score("f3", 0.1)
        top = fi.get_top_features(2)
        assert len(top) == 2
        assert top[0][0] == "f1"

    def test_to_dict(self):
        """测试字典转换。"""
        fi = FeatureImportance()
        fi.set_score("f1", 0.5)
        d = fi.to_dict()
        assert d["f1"] == 0.5


class TestExplainabilityEngine:
    """ExplainabilityEngine测试类。"""

    @pytest.fixture
    def engine(self):
        """创建引擎实例。"""
        return ExplainabilityEngine()

    def test_record_step(self, engine):
        """测试记录步骤。"""
        engine.record_step("s1", "m1", {"a": 1}, {"b": 2}, "test")
        assert engine.get_step_count() == 1

    def test_generate_trace(self, engine):
        """测试生成轨迹。"""
        engine.record_step("s1", "m1", {}, {}, "")
        trace = engine.generate_trace()
        assert len(trace) == 1
        assert trace[0]["step_id"] == "s1"

    def test_generate_summary(self, engine):
        """测试生成摘要。"""
        engine.record_step("s1", "m1", {}, {}, "reasoning")
        summary = engine.generate_summary()
        assert "Decision trace" in summary
        assert "reasoning" in summary

    def test_set_feature_importance(self, engine):
        """测试设置特征重要性。"""
        engine.set_feature_importance({"f1": 0.9, "f2": 0.3})
        explanation = engine.explain_decision()
        assert "f1" in explanation["feature_importance"]
        assert len(explanation["top_features"]) > 0

    def test_explain_decision_structure(self, engine):
        """测试解释结构完整性。"""
        engine.record_step("s1", "m1", {}, {}, "")
        engine.set_feature_importance({"f1": 0.5})
        exp = engine.explain_decision()
        assert "trace" in exp
        assert "summary" in exp
        assert "feature_importance" in exp
        assert "top_features" in exp

    def test_clear(self, engine):
        """测试清空。"""
        engine.record_step("s1", "m1", {}, {}, "")
        engine.set_feature_importance({"f1": 0.5})
        engine.clear()
        assert engine.get_step_count() == 0
        assert engine.explain_decision()["feature_importance"] == {}
