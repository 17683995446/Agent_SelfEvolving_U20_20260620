"""
概念抽象与技能提取模块单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import unittest

import numpy as np

from agent_core.common.data_contracts import (
    DriveSignals,
    EnvironmentState,
    ErrorMetrics,
    Experience,
    PredictionResult,
    Task,
)
from agent_core.memory.concept_abstraction import ConceptAbstraction, SkillLibrary


class TestConceptAbstraction(unittest.TestCase):
    """测试概念抽象器。"""

    def _make_experience(
        self, feature_vector: list[float], task_type: str = "safety"
    ) -> Experience:
        """构造测试经验。"""
        state = EnvironmentState(
            timestamp=1.0,
            raw_sensors={"cpu": 0.5},
            feature_vector=np.array(feature_vector, dtype=np.float32),
        )
        pred = PredictionResult(
            low_level=np.array([0.1, 0.2]),
            mid_level=np.array([0.2, 0.3]),
            high_level=np.array([0.3, 0.4]),
            ensemble=np.array([0.15, 0.25]),
            confidence=0.8,
        )
        drives = DriveSignals(
            safety_reward=0.5,
            gain_reward=0.5,
            efficiency_reward=0.5,
            safety_gap=0.1,
            gain_gap=0.2,
            efficiency_gap=0.3,
            weights={"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
            total_reward=0.5,
        )
        task = Task(
            task_id="t1",
            name="task",
            task_type=task_type,
            priority=0.5,
            expected_reward=0.8,
            expected_cost=0.2,
            novelty_score=0.3,
        )
        error = ErrorMetrics(
            mse=0.01,
            mae=0.05,
            mape=0.1,
            direction_accuracy=0.95,
            error_vector=np.array([0.01, 0.02]),
        )
        return Experience(
            timestamp=1.0,
            state=state,
            prediction=pred,
            drive_signals=drives,
            selected_task=task,
            execution_result={"status": "success", "reward": 0.8},
            error_metrics=error,
            priority=1.0,
        )

    def test_fit_normal(self) -> None:
        """正常值入参测试：正常聚类。"""
        ca = ConceptAbstraction(n_clusters=3)
        experiences = [
            self._make_experience([1.0, 0.0, 0.0]),
            self._make_experience([1.1, 0.1, 0.0]),
            self._make_experience([0.0, 1.0, 0.0]),
            self._make_experience([0.1, 1.1, 0.0]),
            self._make_experience([0.0, 0.0, 1.0]),
            self._make_experience([0.0, 0.1, 1.1]),
        ]
        ca.fit(experiences)
        prototypes = ca.get_concept_prototypes()
        self.assertEqual(len(prototypes), 3)

    def test_fit_too_few(self) -> None:
        """边界极值测试：经验不足。"""
        ca = ConceptAbstraction(n_clusters=5)
        experiences = [self._make_experience([1.0, 0.0])]
        ca.fit(experiences)
        self.assertEqual(len(ca.get_concept_prototypes()), 0)

    def test_predict_concept(self) -> None:
        """正常值入参测试：概念预测。"""
        ca = ConceptAbstraction(n_clusters=2)
        experiences = [
            self._make_experience([1.0, 0.0]),
            self._make_experience([1.1, 0.0]),
            self._make_experience([0.0, 1.0]),
            self._make_experience([0.0, 1.1]),
        ]
        ca.fit(experiences)
        concept = ca.predict_concept(np.array([1.0, 0.0], dtype=np.float32))
        self.assertIn(concept, [0, 1])

    def test_predict_without_fit(self) -> None:
        """空入参测试：未fit时预测。"""
        ca = ConceptAbstraction(n_clusters=2)
        concept = ca.predict_concept(np.array([1.0, 0.0], dtype=np.float32))
        self.assertEqual(concept, -1)

    def test_empty_experiences(self) -> None:
        """空入参测试：空经验列表。"""
        ca = ConceptAbstraction(n_clusters=2)
        ca.fit([])
        self.assertEqual(len(ca.get_concept_prototypes()), 0)


class TestSkillLibrary(unittest.TestCase):
    """测试技能库。"""

    def _make_experience(
        self, task_type: str, status: str, reward: float, cost: float
    ) -> Experience:
        """构造测试经验。"""
        state = EnvironmentState(
            timestamp=1.0,
            raw_sensors={},
            feature_vector=np.array([0.5, 0.5], dtype=np.float32),
        )
        pred = PredictionResult(
            low_level=np.array([0.1]),
            mid_level=np.array([0.2]),
            high_level=np.array([0.3]),
            ensemble=np.array([0.15]),
            confidence=0.8,
        )
        drives = DriveSignals(
            safety_reward=0.5,
            gain_reward=0.5,
            efficiency_reward=0.5,
            safety_gap=0.1,
            gain_gap=0.2,
            efficiency_gap=0.3,
            weights={"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
            total_reward=0.5,
        )
        task = Task(
            task_id="t1",
            name="task",
            task_type=task_type,
            priority=0.5,
            expected_reward=0.8,
            expected_cost=cost,
            novelty_score=0.3,
        )
        error = ErrorMetrics(
            mse=0.01,
            mae=0.05,
            mape=0.1,
            direction_accuracy=0.95,
            error_vector=np.array([0.01]),
        )
        return Experience(
            timestamp=1.0,
            state=state,
            prediction=pred,
            drive_signals=drives,
            selected_task=task,
            execution_result={"status": status, "reward": reward},
            error_metrics=error,
            priority=1.0,
        )

    def test_extract_skills(self) -> None:
        """正常值入参测试：技能提取。"""
        lib = SkillLibrary()
        experiences = [
            self._make_experience("safety", "success", 0.8, 0.1),
            self._make_experience("safety", "success", 0.9, 0.1),
            self._make_experience("safety", "success", 0.7, 0.1),
            self._make_experience("gain", "success", 0.6, 0.2),
            self._make_experience("gain", "success", 0.7, 0.2),
            self._make_experience("gain", "success", 0.5, 0.2),
        ]
        lib.extract_skills(experiences)
        self.assertIn("safety", lib.list_skills())
        self.assertIn("gain", lib.list_skills())
        skill = lib.get_skill("safety")
        self.assertAlmostEqual(skill["avg_reward"], 0.8)

    def test_extract_skills_ignores_failure(self) -> None:
        """正常值入参测试：忽略失败经验。"""
        lib = SkillLibrary()
        experiences = [
            self._make_experience("safety", "failure", 0.0, 0.1),
            self._make_experience("safety", "failure", 0.0, 0.1),
            self._make_experience("safety", "failure", 0.0, 0.1),
        ]
        lib.extract_skills(experiences)
        self.assertEqual(len(lib.list_skills()), 0)

    def test_extract_skills_insufficient_count(self) -> None:
        """边界极值测试：经验不足不提取。"""
        lib = SkillLibrary()
        experiences = [
            self._make_experience("safety", "success", 0.8, 0.1),
            self._make_experience("safety", "success", 0.9, 0.1),
        ]
        lib.extract_skills(experiences)
        self.assertEqual(len(lib.list_skills()), 0)

    def test_match_skill(self) -> None:
        """正常值入参测试：技能匹配。"""
        lib = SkillLibrary()
        experiences = [
            self._make_experience("safety", "success", 0.9, 0.1),
            self._make_experience("safety", "success", 0.9, 0.1),
            self._make_experience("safety", "success", 0.9, 0.1),
            self._make_experience("gain", "success", 0.5, 0.3),
            self._make_experience("gain", "success", 0.5, 0.3),
            self._make_experience("gain", "success", 0.5, 0.3),
        ]
        lib.extract_skills(experiences)
        ca = ConceptAbstraction(n_clusters=2)
        ca.fit(experiences)
        matched = lib.match_skill(
            np.array([0.5, 0.5], dtype=np.float32), ca
        )
        self.assertIsNotNone(matched)

    def test_match_skill_empty(self) -> None:
        """空入参测试：空技能库匹配。"""
        lib = SkillLibrary()
        ca = ConceptAbstraction(n_clusters=2)
        matched = lib.match_skill(
            np.array([0.5, 0.5], dtype=np.float32), ca
        )
        self.assertIsNone(matched)

    def test_get_skill_missing(self) -> None:
        """空入参测试：获取不存在的技能。"""
        lib = SkillLibrary()
        self.assertIsNone(lib.get_skill("unknown"))


if __name__ == "__main__":
    unittest.main()
