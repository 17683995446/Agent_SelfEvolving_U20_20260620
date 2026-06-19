"""
迁移学习模块。

基于概念原型计算场景相似度，迁移源场景技能参数到目标场景。

第一性原理：
- 大脑通过类比将已有知识迁移到新情境
- 相似度度量决定迁移强度
- 迁移后快速微调避免负迁移
"""

from typing import Any, Dict, List, Optional

import numpy as np

from agent_core.common.logger import get_logger


class TransferLearner:
    """
    迁移学习器。

    管理源场景与目标场景间的知识迁移。
    """

    def __init__(self, similarity_threshold: float = 0.7) -> None:
        self._similarity_threshold = similarity_threshold
        self._source_skills: Dict[str, Dict[str, Any]] = {}
        self._logger = get_logger()

    def register_source_skill(
        self,
        skill_name: str,
        prototype: np.ndarray,
        parameters: Dict[str, Any],
    ) -> None:
        """
        注册源场景技能。

        Args:
            skill_name: 技能名称。
            prototype: 概念原型向量。
            parameters: 技能参数字典。
        """
        self._source_skills[skill_name] = {
            "prototype": prototype.copy(),
            "parameters": parameters,
        }
        self._logger.info(
            f"[TransferLearner] Registered source skill: {skill_name}"
        )

    def compute_similarity(
        self,
        target_vector: np.ndarray,
        source_name: str,
    ) -> float:
        """
        计算目标场景与源技能的余弦相似度。

        Args:
            target_vector: 目标场景特征向量。
            source_name: 源技能名称。

        Returns:
            相似度值，范围为[-1, 1]。
        """
        source = self._source_skills.get(source_name)
        if source is None:
            return -1.0
        prototype = source["prototype"]
        if target_vector.shape != prototype.shape:
            self._logger.warning(
                f"[TransferLearner] Shape mismatch: "
                f"target={target_vector.shape}, "
                f"prototype={prototype.shape}"
            )
            return -1.0
        dot = float(np.dot(target_vector, prototype))
        norm = float(
            np.linalg.norm(target_vector) * np.linalg.norm(prototype)
        )
        if norm < 1e-10:
            return 0.0
        return dot / norm

    def find_best_source(
        self, target_vector: np.ndarray
    ) -> Optional[str]:
        """
        查找最相似的源技能。

        Args:
            target_vector: 目标场景特征向量。

        Returns:
            最相似的源技能名称，无匹配返回None。
        """
        best_name: Optional[str] = None
        best_score = self._similarity_threshold
        for name in self._source_skills:
            score = self.compute_similarity(target_vector, name)
            if score > best_score:
                best_score = score
                best_name = name
        return best_name

    def transfer_parameters(
        self,
        target_vector: np.ndarray,
        target_skill_name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        迁移参数到目标场景。

        Args:
            target_vector: 目标场景特征向量。
            target_skill_name: 目标技能名称（用于匹配源技能）。

        Returns:
            迁移后的参数字典，无匹配返回None。
        """
        source_name = self.find_best_source(target_vector)
        if source_name is None:
            return None
        source = self._source_skills[source_name]
        similarity = self.compute_similarity(target_vector, source_name)
        transferred = {}
        for key, value in source["parameters"].items():
            if isinstance(value, (int, float)):
                transferred[key] = value * similarity
            elif isinstance(value, np.ndarray):
                transferred[key] = value * similarity
            else:
                transferred[key] = value
        self._logger.info(
            f"[TransferLearner] Transferred from {source_name} "
            f"to {target_skill_name}, similarity={similarity:.3f}"
        )
        return transferred

    def fine_tune(
        self,
        parameters: Dict[str, Any],
        local_feedback: float,
    ) -> Dict[str, Any]:
        """
        基于本地反馈微调参数。

        Args:
            parameters: 迁移后的参数。
            local_feedback: 本地反馈值，正数增强，负数减弱。

        Returns:
            微调后的参数。
        """
        tuned = {}
        for key, value in parameters.items():
            if isinstance(value, bool):
                tuned[key] = value
            elif isinstance(value, (int, float)):
                tuned[key] = value * (1.0 + local_feedback * 0.1)
            elif isinstance(value, np.ndarray):
                tuned[key] = value * (1.0 + local_feedback * 0.1)
            else:
                tuned[key] = value
        return tuned

    def list_sources(self) -> List[str]:
        """
        列出所有源技能。

        Returns:
            源技能名称列表。
        """
        return list(self._source_skills.keys())
