"""
社会仿真模块测试。

覆盖：信誉记录、联盟管理、以牙还牙策略。
"""

import pytest

from agent_core.task.social_simulator import (
    AgentReputation,
    Coalition,
    SocialSimulator,
)


class TestAgentReputation:
    """AgentReputation测试类。"""

    def test_initial_score(self):
        """测试初始信誉。"""
        rep = AgentReputation("a1")
        assert rep.get_score() == 0.5

    def test_record_cooperate(self):
        """测试记录合作。"""
        rep = AgentReputation("a1")
        rep.record_interaction(True)
        assert rep.get_score() == 1.0

    def test_record_defect(self):
        """测试记录背叛。"""
        rep = AgentReputation("a1")
        rep.record_interaction(False)
        assert rep.get_score() == 0.0

    def test_mixed_interactions(self):
        """测试混合交互。"""
        rep = AgentReputation("a1")
        rep.record_interaction(True)
        rep.record_interaction(False)
        assert rep.get_score() == 0.5


class TestCoalition:
    """Coalition测试类。"""

    def test_add_member(self):
        """测试添加成员。"""
        c = Coalition("c1")
        assert c.add_member("a1") is True
        assert c.get_member_count() == 1

    def test_add_duplicate(self):
        """测试重复添加。"""
        c = Coalition("c1")
        c.add_member("a1")
        assert c.add_member("a1") is False

    def test_remove_member(self):
        """测试移除成员。"""
        c = Coalition("c1")
        c.add_member("a1")
        assert c.remove_member("a1") is True
        assert c.get_member_count() == 0

    def test_contribute(self):
        """测试贡献资源。"""
        c = Coalition("c1")
        c.contribute(10.0)
        assert c.get_shared_resources() == 10.0

    def test_get_members_copy(self):
        """测试获取成员副本。"""
        c = Coalition("c1")
        c.add_member("a1")
        members = c.get_members()
        members.append("a2")
        assert c.get_member_count() == 1


class TestSocialSimulator:
    """SocialSimulator测试类。"""

    @pytest.fixture
    def sim(self):
        """创建仿真器实例。"""
        return SocialSimulator()

    def test_register_agent(self, sim):
        """测试注册智能体。"""
        sim.register_agent("a1")
        assert sim.get_agent_count() == 1

    def test_record_interaction(self, sim):
        """测试记录交互。"""
        sim.record_interaction("a1", "a2", True, True)
        assert sim.get_reputation("a2") == 1.0
        assert sim.get_reputation("a1") == 1.0

    def test_reputation_defect(self, sim):
        """测试背叛降低信誉。"""
        sim.record_interaction("a1", "a2", True, False)
        assert sim.get_reputation("a2") == 0.0

    def test_create_coalition(self, sim):
        """测试创建联盟。"""
        sim.create_coalition("c1")
        assert sim.get_coalition_count() == 1

    def test_join_coalition(self, sim):
        """测试加入联盟。"""
        sim.create_coalition("c1")
        assert sim.join_coalition("a1", "c1") is True
        coalition = sim.get_coalition("c1")
        assert coalition is not None
        assert coalition.get_member_count() == 1

    def test_join_nonexistent_coalition(self, sim):
        """测试加入不存在的联盟。"""
        assert sim.join_coalition("a1", "c1") is False

    def test_tit_for_tat_first_meet(self, sim):
        """测试首次见面合作。"""
        action = sim.decide_action_tit_for_tat("a1", "a2")
        assert action == "cooperate"

    def test_tit_for_tat_after_defect(self, sim):
        """测试背叛后以牙还牙。"""
        sim.record_interaction("a1", "a2", True, False)
        action = sim.decide_action_tit_for_tat("a1", "a2")
        assert action == "defect"

    def test_tit_for_tat_after_cooperate(self, sim):
        """测试合作后继续合作。"""
        sim.record_interaction("a1", "a2", True, True)
        action = sim.decide_action_tit_for_tat("a1", "a2")
        assert action == "cooperate"
