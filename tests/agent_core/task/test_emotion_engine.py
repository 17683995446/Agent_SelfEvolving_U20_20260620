"""
情感计算模块测试。

覆盖：情绪状态、情绪标签、情绪引擎感知/衰减/表达。
"""

import numpy as np
import pytest

from agent_core.task.emotion_engine import (
    EmotionEngine,
    EmotionLabel,
    EmotionState,
)


class TestEmotionState:
    """EmotionState测试类。"""

    def test_init_clipping(self):
        """测试初始化裁剪。"""
        state = EmotionState(pleasure=2.0, arousal=-2.0, dominance=0.5)
        assert state.get_pleasure() == 1.0
        assert state.get_arousal() == -1.0
        assert state.get_dominance() == pytest.approx(0.5)

    def test_to_vector(self):
        """测试向量转换。"""
        state = EmotionState(0.5, 0.3, -0.2)
        vector = state.to_vector()
        assert np.allclose(vector, np.array([0.5, 0.3, -0.2]))

    def test_distance(self):
        """测试距离计算。"""
        s1 = EmotionState(0.0, 0.0, 0.0)
        s2 = EmotionState(1.0, 0.0, 0.0)
        assert s1.distance(s2) == pytest.approx(1.0, abs=0.01)


class TestEmotionLabel:
    """EmotionLabel测试类。"""

    def test_get_state(self):
        """测试获取预定义情绪状态。"""
        state = EmotionLabel.get_state("joy")
        assert state.get_pleasure() == pytest.approx(0.8)

    def test_classify_neutral(self):
        """测试中性状态分类。"""
        state = EmotionState(0.0, 0.0, 0.0)
        label = EmotionLabel.classify(state)
        assert label == "neutral"

    def test_classify_joy(self):
        """测试快乐状态分类。"""
        state = EmotionState(0.8, 0.6, 0.4)
        label = EmotionLabel.classify(state)
        assert label == "joy"

    def test_classify_unknown(self):
        """测试未知状态分类为最近标签。"""
        state = EmotionState(0.7, 0.5, 0.3)
        label = EmotionLabel.classify(state)
        assert label == "joy"


class TestEmotionEngine:
    """EmotionEngine测试类。"""

    @pytest.fixture
    def engine(self):
        """创建情感引擎实例。"""
        return EmotionEngine()

    def test_perceive_event_positive(self, engine):
        """测试感知正面事件。"""
        state = engine.perceive_event(1.0, 0.5)
        assert state.get_pleasure() > 0.0
        assert state.get_arousal() > 0.0

    def test_perceive_event_negative(self, engine):
        """测试感知负面事件。"""
        state = engine.perceive_event(-1.0, 0.5)
        assert state.get_pleasure() < 0.0

    def test_perceive_event_clipping(self, engine):
        """测试感知事件裁剪。"""
        for _ in range(10):
            engine.perceive_event(1.0, 1.0)
        state = engine.get_current_state()
        assert state.get_pleasure() <= 1.0
        assert state.get_arousal() <= 1.0

    def test_decay(self, engine):
        """测试情绪衰减。"""
        engine.perceive_event(1.0, 1.0)
        before = engine.get_current_state().get_pleasure()
        engine.decay()
        after = engine.get_current_state().get_pleasure()
        assert after < before

    def test_get_current_label(self, engine):
        """测试获取当前标签。"""
        engine.perceive_event(-0.8, 0.8)
        label = engine.get_current_label()
        assert label in EmotionLabel.LABELS

    def test_express_neutral(self, engine):
        """测试中性表达。"""
        text = engine.express()
        assert text == "feeling neutral"

    def test_express_non_neutral(self, engine):
        """测试非中性表达。"""
        engine.perceive_event(1.0, 1.0)
        text = engine.express()
        assert "feeling" in text
        assert "intensity" in text

    def test_history(self, engine):
        """测试历史记录。"""
        engine.perceive_event(0.5, 0.5)
        history = engine.get_history()
        assert len(history) == 1

    def test_reset(self, engine):
        """测试重置。"""
        engine.perceive_event(1.0, 1.0)
        engine.reset()
        assert engine.get_current_state().get_pleasure() == 0.0
        assert len(engine.get_history()) == 0
