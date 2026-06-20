"""
能耗优化子包。

包含能量预算管理、自适应计算控制、模块休眠。
"""

from agent_core.energy.energy_budget import (
    EnergyBudgetManager,
    BudgetResult,
    ModulePriority,
)
from agent_core.energy.adaptive_compute import (
    AdaptiveComputeController,
    PowerProfile,
    ComputeDecision,
)
from agent_core.energy.module_hibernator import (
    ModuleHibernator,
    ModuleState,
)

__all__ = [
    "EnergyBudgetManager",
    "BudgetResult",
    "ModulePriority",
    "AdaptiveComputeController",
    "PowerProfile",
    "ComputeDecision",
    "ModuleHibernator",
    "ModuleState",
]
