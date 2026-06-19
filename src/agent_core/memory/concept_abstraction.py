"""
概念抽象与技能提取模块。

对历史经验进行聚类，提取典型场景原型，构建可复用技能。

第一性原理：
- 大脑通过模式提取形成概念，加速新情境处理
- 聚类将连续经验空间离散化为可命名的原型
- 技能是高频成功模式的参数化模板
"""

import random
from typing import Any, Dict, List, Optional

import numpy as np

from agent_core.common.data_contracts import Experience
from agent_core.common.logger import get_logger

_KMEANS_ATOL = 1e-4
_SKILL_MIN_COUNT = 3
_SKILL_SCORE_OFFSET = -1.0


class ConceptAbstraction:
    """
    概念抽象器。

    使用K-Means简化版对经验特征向量聚类，提取概念原型。
    """

    def __init__(self, n_clusters: int = 5, max_iterations: int = 20) -> None:
        self._n_clusters = n_clusters
        self._max_iterations = max_iterations
        self._centroids: Optional[np.ndarray] = None
        self._labels: List[int] = []
        self._logger = get_logger()

    def fit(self, experiences: List[Experience]) -> None:
        """对经验列表进行聚类。"""
        if len(experiences) < self._n_clusters:
            self._logger.warning(
                "[ConceptAbstraction] Too few experiences for clustering"
            )
            return
        vectors = self._extract_vectors(experiences)
        self._centroids = self._kmeans(vectors)
        self._labels = self._assign_labels(vectors)
        self._logger.info(
            f"[ConceptAbstraction] Clustered {len(experiences)} into "
            f"{self._n_clusters} concepts"
        )

    def _extract_vectors(self, experiences: List[Experience]) -> np.ndarray:
        """提取经验特征向量。"""
        vectors = []
        for exp in experiences:
            vec = exp.state.feature_vector.copy()
            vectors.append(vec)
        return np.array(vectors, dtype=np.float32)

    def _kmeans(self, vectors: np.ndarray) -> np.ndarray:
        """简化K-Means聚类。"""
        n_samples = len(vectors)
        indices = random.sample(range(n_samples), self._n_clusters)
        centroids = vectors[indices].copy()
        for _ in range(self._max_iterations):
            labels = self._assign_labels_to_centroids(vectors, centroids)
            new_centroids = self._update_centroids(vectors, labels)
            if np.allclose(centroids, new_centroids, atol=_KMEANS_ATOL):
                break
            centroids = new_centroids
        return centroids

    def _assign_labels_to_centroids(
        self, vectors: np.ndarray, centroids: np.ndarray
    ) -> List[int]:
        """为每个向量分配最近质心。"""
        labels = []
        for vec in vectors:
            distances = np.linalg.norm(centroids - vec, axis=1)
            labels.append(int(np.argmin(distances)))
        return labels

    def _update_centroids(
        self, vectors: np.ndarray, labels: List[int]
    ) -> np.ndarray:
        """更新质心位置。"""
        new_centroids = []
        for k in range(self._n_clusters):
            mask = np.array(labels) == k
            if np.any(mask):
                new_centroids.append(vectors[mask].mean(axis=0))
            else:
                idx = random.randint(0, len(vectors) - 1)
                new_centroids.append(vectors[idx])
        return np.array(new_centroids, dtype=np.float32)

    def _assign_labels(self, vectors: np.ndarray) -> List[int]:
        """使用当前质心分配标签。"""
        if self._centroids is None:
            return []
        return self._assign_labels_to_centroids(vectors, self._centroids)

    def get_concept_prototypes(self) -> List[np.ndarray]:
        """获取概念原型向量。"""
        if self._centroids is None:
            return []
        return [c.copy() for c in self._centroids]

    def predict_concept(self, feature_vector: np.ndarray) -> int:
        """预测特征向量所属概念。"""
        if self._centroids is None:
            return -1
        distances = np.linalg.norm(self._centroids - feature_vector, axis=1)
        return int(np.argmin(distances))


class SkillLibrary:
    """
    技能库。

    存储从高频成功模式中提取的参数化技能模板。
    """

    def __init__(self) -> None:
        self._skills: Dict[str, Dict[str, Any]] = {}
        self._logger = get_logger()

    def extract_skills(self, experiences: List[Experience]) -> None:
        """从经验中提取技能。"""
        type_groups = self._group_by_type(experiences)
        for task_type, exps in type_groups.items():
            if len(exps) < _SKILL_MIN_COUNT:
                continue
            self._store_skill(task_type, exps)

    def _group_by_type(
        self, experiences: List[Experience]
    ) -> Dict[str, List[Experience]]:
        groups: Dict[str, List[Experience]] = {}
        for exp in experiences:
            task = exp.selected_task
            if task is None:
                continue
            if exp.execution_result.get("status") != "success":
                continue
            task_type = task.task_type
            if task_type not in groups:
                groups[task_type] = []
            groups[task_type].append(exp)
        return groups

    def _store_skill(self, task_type: str, exps: List[Experience]) -> None:
        avg_reward = sum(
            e.execution_result.get("reward", 0.0) for e in exps
        ) / len(exps)
        avg_cost = sum(e.selected_task.expected_cost for e in exps) / len(exps)
        self._skills[task_type] = {
            "count": len(exps),
            "avg_reward": avg_reward,
            "avg_cost": avg_cost,
            "task_type": task_type,
        }
        self._logger.info(
            f"[SkillLibrary] Extracted skill {task_type}: "
            f"count={len(exps)}, reward={avg_reward:.3f}"
        )

    def get_skill(self, task_type: str) -> Optional[Dict[str, Any]]:
        """获取指定类型的技能。"""
        return self._skills.get(task_type)

    def list_skills(self) -> List[str]:
        """列出所有技能类型。"""
        return list(self._skills.keys())

    def match_skill(
        self, feature_vector: np.ndarray, concept_abstraction: ConceptAbstraction
    ) -> Optional[str]:
        """根据当前状态匹配最相关的技能。"""
        if not self._skills:
            return None
        concept_abstraction.predict_concept(feature_vector)
        return self._find_best_skill()

    def _find_best_skill(self) -> Optional[str]:
        best_skill = None
        best_score = _SKILL_SCORE_OFFSET
        for task_type, skill in self._skills.items():
            score = skill["avg_reward"] - skill["avg_cost"]
            if score > best_score:
                best_score = score
                best_skill = task_type
        return best_skill
