"""
可解释AI模块。

实现决策过程的可视化与解释生成。

第一性原理：
- 可解释性增强信任与调试能力
- 特征重要性揭示决策依据
- 决策链追溯推理过程
"""

from typing import Any, Dict, List, Optional

from agent_core.common.logger import get_logger


class DecisionStep:
    """
    决策步骤。

    记录单步决策的输入、推理与输出。
    """

    def __init__(
        self,
        step_id: str,
        module: str,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        reasoning: str = "",
    ) -> None:
        self._step_id = step_id
        self._module = module
        self._inputs = inputs
        self._outputs = outputs
        self._reasoning = reasoning

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "step_id": self._step_id,
            "module": self._module,
            "inputs": self._inputs,
            "outputs": self._outputs,
            "reasoning": self._reasoning,
        }

    def get_module(self) -> str:
        """获取模块名称。"""
        return self._module

    def get_reasoning(self) -> str:
        """获取推理说明。"""
        return self._reasoning


class FeatureImportance:
    """
    特征重要性。

    记录各特征对决策的贡献度。
    """

    def __init__(self) -> None:
        self._scores: Dict[str, float] = {}

    def set_score(self, feature: str, score: float) -> None:
        """
        设置特征重要性分数。

        Args:
            feature: 特征名称。
            score: 重要性分数。
        """
        self._scores[feature] = score

    def get_top_features(self, k: int = 5) -> List[tuple]:
        """
        获取最重要的k个特征。

        Args:
            k: 数量。

        Returns:
            [(特征名, 分数), ...]。
        """
        sorted_items = sorted(
            self._scores.items(),
            key=lambda x: abs(x[1]),
            reverse=True,
        )
        return sorted_items[:k]

    def to_dict(self) -> Dict[str, float]:
        """转换为字典。"""
        return self._scores.copy()


class ExplainabilityEngine:
    """
    可解释性引擎。

    追踪决策过程，生成人类可读的解释。
    """

    def __init__(self) -> None:
        self._steps: List[DecisionStep] = []
        self._feature_importance = FeatureImportance()
        self._logger = get_logger()

    def record_step(
        self,
        step_id: str,
        module: str,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        reasoning: str = "",
    ) -> None:
        """
        记录决策步骤。

        Args:
            step_id: 步骤ID。
            module: 模块名称。
            inputs: 输入数据。
            outputs: 输出数据。
            reasoning: 推理说明。
        """
        step = DecisionStep(step_id, module, inputs, outputs, reasoning)
        self._steps.append(step)

    def set_feature_importance(self, scores: Dict[str, float]) -> None:
        """
        设置特征重要性。

        Args:
            scores: 特征分数字典。
        """
        for feature, score in scores.items():
            self._feature_importance.set_score(feature, score)

    def generate_trace(self) -> List[Dict[str, Any]]:
        """
        生成决策轨迹。

        Returns:
            步骤字典列表。
        """
        return [step.to_dict() for step in self._steps]

    def generate_summary(self) -> str:
        """
        生成决策摘要。

        Returns:
            摘要文本。
        """
        lines: List[str] = []
        lines.append(f"Decision trace: {len(self._steps)} steps")
        for step in self._steps:
            lines.append(
                f"  [{step.get_module()}] {step.get_reasoning()}"
            )
        top_features = self._feature_importance.get_top_features(3)
        if top_features:
            lines.append("Top features:")
            for name, score in top_features:
                lines.append(f"  {name}: {score:.3f}")
        return "\n".join(lines)

    def explain_decision(self) -> Dict[str, Any]:
        """
        生成完整解释。

        Returns:
            解释字典。
        """
        return {
            "trace": self.generate_trace(),
            "summary": self.generate_summary(),
            "feature_importance": self._feature_importance.to_dict(),
            "top_features": self._feature_importance.get_top_features(),
        }

    def clear(self) -> None:
        """清空记录。"""
        self._steps.clear()
        self._feature_importance = FeatureImportance()

    def get_step_count(self) -> int:
        """获取步骤数量。"""
        return len(self._steps)
