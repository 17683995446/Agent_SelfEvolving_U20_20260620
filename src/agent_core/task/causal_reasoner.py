"""
因果推理引擎模块。

实现干预与反事实分析，支持因果图建模和效应估计。

第一性原理：
- 相关性不等于因果性
- 干预是验证因果假设的唯一方式
- 反事实推理回答"如果...会怎样"
"""

from typing import Any, Dict, List, Optional, Tuple

from agent_core.common.logger import get_logger


class CausalReasoner:
    """
    因果推理引擎。

    基于因果图进行干预分析和反事实推理。
    """

    def __init__(self) -> None:
        self._causal_graph: Dict[str, List[str]] = {}
        self._interventions: Dict[str, Any] = {}
        self._logger = get_logger()

    def add_causal_link(self, cause: str, effect: str) -> None:
        """
        添加因果关系。

        Args:
            cause: 原因变量。
            effect: 结果变量。
        """
        if cause not in self._causal_graph:
            self._causal_graph[cause] = []
        self._causal_graph[cause].append(effect)

    def get_effects(self, cause: str) -> List[str]:
        """
        获取变量的直接效应。

        Args:
            cause: 原因变量。

        Returns:
            直接效应变量列表。
        """
        return list(self._causal_graph.get(cause, []))

    def get_causes(self, effect: str) -> List[str]:
        """
        获取变量的直接原因。

        Args:
            effect: 结果变量。

        Returns:
            直接原因变量列表。
        """
        return [
            cause for cause, effects in self._causal_graph.items()
            if effect in effects
        ]

    def intervene(self, variable: str, value: Any) -> None:
        """
        对变量进行干预（do-算子）。

        Args:
            variable: 干预变量。
            value: 干预值。
        """
        self._interventions[variable] = value
        self._logger.info(f"[CausalReasoner] do({variable}={value})")

    def clear_interventions(self) -> None:
        """清除所有干预。"""
        self._interventions.clear()

    def estimate_effect(
        self,
        cause: str,
        effect: str,
        data: List[Dict[str, Any]],
    ) -> Optional[float]:
        """
        估计因果效应（简单平均差）。

        Args:
            cause: 原因变量。
            effect: 结果变量。
            data: 观测数据列表。

        Returns:
            平均因果效应，数据不足返回None。
        """
        treated = [d[effect] for d in data if d.get(cause) == 1]
        control = [d[effect] for d in data if d.get(cause) == 0]
        if not treated or not control:
            return None
        return sum(treated) / len(treated) - sum(control) / len(control)

    def counterfactual(
        self,
        variable: str,
        new_value: Any,
        current_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        反事实推理：如果变量取新值，状态会如何变化。

        Args:
            variable: 要改变的变量。
            new_value: 新值。
            current_state: 当前状态。

        Returns:
            反事实状态。
        """
        counterfactual_state = dict(current_state)
        counterfactual_state[variable] = new_value
        effects = self._get_all_effects(variable)
        for effect in effects:
            counterfactual_state[effect] = self._predict_effect(
                variable, new_value, effect
            )
        return counterfactual_state

    def _get_all_effects(self, cause: str, visited: Optional[set] = None) -> List[str]:
        """获取变量的所有间接效应。"""
        if visited is None:
            visited = set()
        if cause in visited:
            return []
        visited.add(cause)
        direct = self.get_effects(cause)
        indirect: List[str] = []
        for effect in direct:
            indirect.extend(self._get_all_effects(effect, visited))
        return direct + indirect

    def _predict_effect(
        self, cause: str, cause_value: Any, effect: str
    ) -> Any:
        """预测效应值（简化线性模型）。"""
        return cause_value

    def ingest(self, experience: Any) -> None:
        """
        从经验中提取因果关系。

        Args:
            experience: 经验对象（Experience dataclass 或 dict）。
        """
        if isinstance(experience, dict):
            state = experience.get("state", {})
            action = experience.get("action", {})
            task_type = action.get("task_type") if isinstance(action, dict) else None
        else:
            # Experience dataclass
            state = getattr(getattr(experience, "state", None), "raw_sensors", {})
            selected_task = getattr(experience, "selected_task", None)
            task_type = getattr(selected_task, "task_type", None) if selected_task else None
        if task_type is None:
            return
        for key in state:
            self.add_causal_link(task_type, key)

    def find_confounders(
        self, cause: str, effect: str
    ) -> List[str]:
        """
        查找混杂因子（同时影响原因和结果的变量）。

        Args:
            cause: 原因变量。
            effect: 结果变量。

        Returns:
            混杂因子列表。
        """
        causes_of_effect = set(self.get_causes(effect))
        causes_of_cause = set(self.get_causes(cause))
        return list(causes_of_effect & causes_of_cause)
