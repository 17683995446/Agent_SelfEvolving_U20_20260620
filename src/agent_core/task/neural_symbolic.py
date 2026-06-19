"""
神经符号推理模块。

融合逻辑规则与神经网络，实现可解释的推理。

第一性原理：
- 符号逻辑提供可解释性
- 神经网络提供泛化能力
- 两者互补增强推理
"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from agent_core.common.logger import get_logger


class LogicRule:
    """
    逻辑规则。

    表示一条可执行的符号规则。
    """

    def __init__(
        self,
        name: str,
        premises: List[str],
        conclusion: str,
        confidence: float = 1.0,
    ) -> None:
        self._name = name
        self._premises = premises
        self._conclusion = conclusion
        self._confidence = confidence

    def evaluate(
        self,
        facts: Dict[str, bool],
    ) -> Tuple[bool, float]:
        """
        评估规则在给定事实下是否触发。

        Args:
            facts: 已知事实字典。

        Returns:
            (是否触发, 置信度)。
        """
        for premise in self._premises:
            if not facts.get(premise, False):
                return False, 0.0
        return True, self._confidence

    def get_name(self) -> str:
        """获取规则名称。"""
        return self._name

    def get_conclusion(self) -> str:
        """获取结论。"""
        return self._conclusion

    def get_premises(self) -> List[str]:
        """获取前提列表。"""
        return self._premises.copy()


class NeuralPredicate:
    """
    神经谓词。

    用神经网络评估谓词真值。
    """

    def __init__(
        self,
        name: str,
        input_dim: int,
        weights: Optional[np.ndarray] = None,
    ) -> None:
        self._name = name
        self._input_dim = input_dim
        if weights is None:
            self._weights = np.zeros(input_dim)
        else:
            self._weights = weights.copy()

    def evaluate(self, inputs: np.ndarray) -> float:
        """
        评估谓词真值。

        Args:
            inputs: 输入向量。

        Returns:
            真值概率 [0, 1]。
        """
        if inputs.shape[0] != self._input_dim:
            return 0.0
        score = float(np.dot(inputs, self._weights))
        return float(1.0 / (1.0 + np.exp(-score)))

    def update_weights(
        self,
        gradient: np.ndarray,
        learning_rate: float = 0.01,
    ) -> None:
        """
        更新权重。

        Args:
            gradient: 梯度向量。
            learning_rate: 学习率。
        """
        self._weights += learning_rate * gradient

    def get_name(self) -> str:
        """获取谓词名称。"""
        return self._name


class NeuralSymbolicReasoner:
    """
    神经符号推理器。

    结合逻辑规则与神经谓词进行推理。
    """

    def __init__(self) -> None:
        self._rules: List[LogicRule] = []
        self._predicates: Dict[str, NeuralPredicate] = {}
        self._facts: Dict[str, bool] = {}
        self._logger = get_logger()

    def add_rule(self, rule: LogicRule) -> None:
        """
        添加逻辑规则。

        Args:
            rule: 逻辑规则实例。
        """
        self._rules.append(rule)

    def add_predicate(self, predicate: NeuralPredicate) -> None:
        """
        添加神经谓词。

        Args:
            predicate: 神经谓词实例。
        """
        self._predicates[predicate.get_name()] = predicate

    def set_fact(self, name: str, value: bool) -> None:
        """
        设置事实。

        Args:
            name: 事实名称。
            value: 事实值。
        """
        self._facts[name] = value

    def evaluate_predicate(
        self,
        name: str,
        inputs: np.ndarray,
    ) -> float:
        """
        评估神经谓词。

        Args:
            name: 谓词名称。
            inputs: 输入向量。

        Returns:
            真值概率。
        """
        predicate = self._predicates.get(name)
        if predicate is None:
            return 0.0
        return predicate.evaluate(inputs)

    def reason(
        self,
        max_iterations: int = 10,
    ) -> Dict[str, Tuple[bool, float]]:
        """
        执行前向链推理。

        Args:
            max_iterations: 最大迭代次数。

        Returns:
            推理结果字典 {结论: (是否成立, 置信度)}。
        """
        results: Dict[str, Tuple[bool, float]] = {}
        changed = True
        iteration = 0
        while changed and iteration < max_iterations:
            changed = False
            iteration += 1
            for rule in self._rules:
                triggered, confidence = rule.evaluate(self._facts)
                if triggered:
                    conclusion = rule.get_conclusion()
                    if conclusion not in results or results[conclusion][1] < confidence:
                        results[conclusion] = (True, confidence)
                        if not self._facts.get(conclusion, False):
                            self._facts[conclusion] = True
                            changed = True
        return results

    def hybrid_infer(
        self,
        neural_inputs: Dict[str, np.ndarray],
    ) -> Dict[str, float]:
        """
        混合推理：先评估神经谓词，再符号推理。

        Args:
            neural_inputs: 神经谓词输入 {名称: 输入向量}。

        Returns:
            最终结论置信度字典。
        """
        for name, inputs in neural_inputs.items():
            score = self.evaluate_predicate(name, inputs)
            self._facts[name] = score > 0.5
        results = self.reason()
        return {
            name: float(confidence)
            for name, (_, confidence) in results.items()
        }

    def clear_facts(self) -> None:
        """清空事实。"""
        self._facts.clear()

    def get_rule_count(self) -> int:
        """获取规则数量。"""
        return len(self._rules)

    def get_predicate_count(self) -> int:
        """获取谓词数量。"""
        return len(self._predicates)
