"""
迁移学习模块单元测试。

覆盖正常值、空入参、边界极值、非法格式四类用例。
"""

import unittest

import numpy as np

from agent_core.memory.transfer_learning import TransferLearner


class TestTransferLearner(unittest.TestCase):
    """测试迁移学习器。"""

    def setUp(self) -> None:
        """每个用例前创建新实例。"""
        self.learner = TransferLearner(similarity_threshold=0.7)

    def test_register_and_list(self) -> None:
        """正常值入参测试：注册与列出。"""
        self.learner.register_source_skill(
            "source_a",
            np.array([1.0, 0.0, 0.0]),
            {"lr": 0.1, "batch": 32},
        )
        self.assertEqual(self.learner.list_sources(), ["source_a"])

    def test_similarity_identical(self) -> None:
        """正常值入参测试：相同向量相似度。"""
        vec = np.array([1.0, 0.0, 0.0])
        self.learner.register_source_skill("s", vec, {})
        sim = self.learner.compute_similarity(vec, "s")
        self.assertAlmostEqual(sim, 1.0, places=5)

    def test_similarity_orthogonal(self) -> None:
        """正常值入参测试：正交向量相似度。"""
        self.learner.register_source_skill(
            "s", np.array([1.0, 0.0]), {}
        )
        sim = self.learner.compute_similarity(
            np.array([0.0, 1.0]), "s"
        )
        self.assertAlmostEqual(sim, 0.0, places=5)

    def test_similarity_unknown(self) -> None:
        """空入参测试：未知源技能。"""
        sim = self.learner.compute_similarity(
            np.array([1.0, 0.0]), "unknown"
        )
        self.assertEqual(sim, -1.0)

    def test_find_best_source(self) -> None:
        """正常值入参测试：查找最佳源。"""
        self.learner.register_source_skill(
            "a", np.array([1.0, 0.0]), {"p": 1.0}
        )
        self.learner.register_source_skill(
            "b", np.array([0.0, 1.0]), {"p": 2.0}
        )
        best = self.learner.find_best_source(np.array([0.9, 0.1]))
        self.assertEqual(best, "a")

    def test_find_best_no_match(self) -> None:
        """边界极值测试：无匹配源。"""
        self.learner.register_source_skill(
            "a", np.array([1.0, 0.0]), {"p": 1.0}
        )
        best = self.learner.find_best_source(np.array([0.0, 1.0]))
        self.assertIsNone(best)

    def test_transfer_parameters(self) -> None:
        """正常值入参测试：参数迁移。"""
        self.learner.register_source_skill(
            "source",
            np.array([1.0, 0.0]),
            {"lr": 0.1, "name": "test"},
        )
        transferred = self.learner.transfer_parameters(
            np.array([1.0, 0.0]), "target"
        )
        self.assertIsNotNone(transferred)
        self.assertAlmostEqual(transferred["lr"], 0.1, places=5)
        self.assertEqual(transferred["name"], "test")

    def test_transfer_no_match(self) -> None:
        """空入参测试：无匹配迁移。"""
        transferred = self.learner.transfer_parameters(
            np.array([1.0, 0.0]), "target"
        )
        self.assertIsNone(transferred)

    def test_fine_tune_positive(self) -> None:
        """正常值入参测试：正向微调。"""
        params = {"lr": 0.1, "arr": np.array([1.0, 2.0])}
        tuned = self.learner.fine_tune(params, 1.0)
        self.assertAlmostEqual(tuned["lr"], 0.11, places=5)
        np.testing.assert_array_almost_equal(
            tuned["arr"], [1.1, 2.2]
        )

    def test_fine_tune_negative(self) -> None:
        """正常值入参测试：负向微调。"""
        params = {"lr": 0.1}
        tuned = self.learner.fine_tune(params, -1.0)
        self.assertAlmostEqual(tuned["lr"], 0.09, places=5)

    def test_fine_tune_non_numeric(self) -> None:
        """正常值入参测试：非数值参数不变。"""
        params = {"name": "test", "flag": True}
        tuned = self.learner.fine_tune(params, 1.0)
        self.assertEqual(tuned["name"], "test")
        self.assertEqual(tuned["flag"], True)

    def test_similarity_zero_norm(self) -> None:
        """边界极值测试：零向量。"""
        self.learner.register_source_skill(
            "s", np.array([0.0, 0.0]), {}
        )
        sim = self.learner.compute_similarity(
            np.array([0.0, 0.0]), "s"
        )
        self.assertEqual(sim, 0.0)


if __name__ == "__main__":
    unittest.main()
