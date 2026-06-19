"""
因果推理引擎测试。

覆盖：因果链、效应估计、反事实推理、混杂因子检测、干预操作。
"""

import pytest

from agent_core.task.causal_reasoner import CausalReasoner


class TestCausalReasoner:
    """CausalReasoner测试类。"""

    @pytest.fixture
    def reasoner(self):
        """创建因果推理引擎实例。"""
        r = CausalReasoner()
        r.add_causal_link("smoking", "cancer")
        r.add_causal_link("smoking", "yellow_fingers")
        r.add_causal_link("genetics", "smoking")
        r.add_causal_link("genetics", "cancer")
        return r

    def test_get_effects(self, reasoner):
        """测试获取直接效应。"""
        effects = reasoner.get_effects("smoking")
        assert set(effects) == {"cancer", "yellow_fingers"}

    def test_get_causes(self, reasoner):
        """测试获取直接原因。"""
        causes = reasoner.get_causes("cancer")
        assert set(causes) == {"smoking", "genetics"}

    def test_intervene(self, reasoner):
        """测试干预操作。"""
        reasoner.intervene("smoking", 0)
        assert reasoner._interventions["smoking"] == 0

    def test_clear_interventions(self, reasoner):
        """测试清除干预。"""
        reasoner.intervene("smoking", 0)
        reasoner.clear_interventions()
        assert len(reasoner._interventions) == 0

    def test_estimate_effect(self, reasoner):
        """测试因果效应估计。"""
        data = [
            {"smoking": 1, "cancer": 1},
            {"smoking": 1, "cancer": 1},
            {"smoking": 0, "cancer": 0},
            {"smoking": 0, "cancer": 0},
        ]
        effect = reasoner.estimate_effect("smoking", "cancer", data)
        assert effect == 1.0

    def test_estimate_effect_insufficient(self, reasoner):
        """测试数据不足返回None。"""
        data = [{"smoking": 1, "cancer": 1}]
        effect = reasoner.estimate_effect("smoking", "cancer", data)
        assert effect is None

    def test_counterfactual(self, reasoner):
        """测试反事实推理。"""
        state = {"smoking": 1, "yellow_fingers": 1}
        cf = reasoner.counterfactual("smoking", 0, state)
        assert cf["smoking"] == 0
        assert cf["yellow_fingers"] == 0

    def test_find_confounders(self, reasoner):
        """测试混杂因子检测。"""
        confounders = reasoner.find_confounders("smoking", "cancer")
        assert confounders == ["genetics"]

    def test_no_confounders(self, reasoner):
        """测试无混杂因子。"""
        confounders = reasoner.find_confounders("smoking", "yellow_fingers")
        assert confounders == []
