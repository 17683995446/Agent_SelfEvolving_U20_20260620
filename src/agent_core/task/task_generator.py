"""
任务生成器模块。

根据驱力信号和误差生成候选任务。
通过任务模板注册表支持动态扩展任务类型，无需修改源码。
"""

import random
import uuid
from typing import Any, Callable, Dict, List

from agent_core.common.data_contracts import DriveSignals, ErrorMetrics, Task
from agent_core.common.interfaces import ITaskGenerator
from agent_core.common.exceptions import ModuleNotInitializedException
from agent_core.common.constants import (
    DRIVE_GAP_THRESHOLD,
    EXPLORATION_RATE_DEFAULT,
    PREDICTION_ERROR_THRESHOLD,
)
from agent_core.common.logger import get_logger

_TASK_NAME_SAFETY = "安全维护任务"
_TASK_NAME_GAIN = "信息探索任务"
_TASK_NAME_EFFICIENCY = "能效优化任务"
_REWARD_RATIO_SAFETY = 0.8
_REWARD_RATIO_GAIN = 0.7
_REWARD_RATIO_EFFICIENCY = 0.6
_COST_SAFETY = 0.2
_COST_GAIN = 0.3
_COST_EFFICIENCY = 0.25
_NOVELTY_DRIVE = 0.3
_NOVELTY_EXPLORATION = 0.9
_ERROR_REWARD = 0.4
_ERROR_COST = 0.35
_RANDOM_PRIORITY = 0.5


class TaskTemplate:
    """
    任务模板。

    定义任务类型的参数化构建规则。
    """

    def __init__(
        self,
        name: str,
        task_type: str,
        reward_ratio: float,
        cost: float,
        actions: List[str],
        novelty_score: float,
    ) -> None:
        self.name = name
        self.task_type = task_type
        self.reward_ratio = reward_ratio
        self.cost = cost
        self.actions = actions
        self.novelty_score = novelty_score

    def build(self, gap: float) -> Task:
        """根据缺口构建任务实例。"""
        return Task(
            task_id=str(uuid.uuid4())[:8],
            name=self.name,
            task_type=self.task_type,
            priority=gap,
            expected_reward=gap * self.reward_ratio,
            expected_cost=self.cost,
            novelty_score=self.novelty_score,
            params={"actions": self.actions},
        )


class TaskGenerator(ITaskGenerator):
    """
    任务生成器实现。
    """

    def __init__(self) -> None:
        self._exploration_rate = EXPLORATION_RATE_DEFAULT
        self._initialized = False
        self._config: Dict[str, Any] = {}
        self._logger = get_logger()
        self._templates: Dict[str, TaskTemplate] = {}
        self._register_default_templates()

    def _register_default_templates(self) -> None:
        """注册默认任务模板。"""
        self.register_template(
            "safety",
            TaskTemplate(
                name=_TASK_NAME_SAFETY,
                task_type="safety",
                reward_ratio=_REWARD_RATIO_SAFETY,
                cost=_COST_SAFETY,
                actions=["cleanup_zombies", "check_logs"],
                novelty_score=_NOVELTY_DRIVE,
            ),
        )
        self.register_template(
            "gain",
            TaskTemplate(
                name=_TASK_NAME_GAIN,
                task_type="gain",
                reward_ratio=_REWARD_RATIO_GAIN,
                cost=_COST_GAIN,
                actions=["explore_state_space", "update_model"],
                novelty_score=_NOVELTY_DRIVE,
            ),
        )
        self.register_template(
            "efficiency",
            TaskTemplate(
                name=_TASK_NAME_EFFICIENCY,
                task_type="efficiency",
                reward_ratio=_REWARD_RATIO_EFFICIENCY,
                cost=_COST_EFFICIENCY,
                actions=["optimize_cache", "release_resources"],
                novelty_score=_NOVELTY_DRIVE,
            ),
        )

    def register_template(
        self, task_type: str, template: TaskTemplate
    ) -> None:
        """动态注册任务模板。"""
        self._templates[task_type] = template
        self._logger.info(
            f"[TaskGenerator] Registered template: {task_type}"
        )

    def list_templates(self) -> List[str]:
        """列出所有已注册模板类型。"""
        return list(self._templates.keys())

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "TaskGenerator"

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化任务生成器。"""
        self._config = config
        self._exploration_rate = config.get(
            "exploration_rate", EXPLORATION_RATE_DEFAULT
        )
        if not self._templates:
            self._register_default_templates()
        self._initialized = True
        return True

    def generate(
        self, drive_signals: DriveSignals, errors: ErrorMetrics
    ) -> List[Task]:
        """生成候选任务。"""
        if not self._initialized:
            raise ModuleNotInitializedException(
                "TaskGenerator not initialized"
            )
        tasks: List[Task] = []
        gaps = {
            "safety": drive_signals.safety_gap,
            "gain": drive_signals.gain_gap,
            "efficiency": drive_signals.efficiency_gap,
        }
        tasks.extend(self._create_drive_tasks(gaps))
        tasks.extend(self._create_error_tasks(errors))
        tasks.extend(self._create_random_tasks())
        self._logger.debug(
            f"[TaskGenerator] Generated {len(tasks)} tasks"
        )
        return tasks

    def _create_drive_tasks(self, gaps: Dict[str, float]) -> List[Task]:
        tasks: List[Task] = []
        for task_type, gap in gaps.items():
            if gap > DRIVE_GAP_THRESHOLD:
                tasks.append(self._build_drive_task(task_type, gap))
        return tasks

    def _build_drive_task(self, task_type: str, gap: float) -> Task:
        template = self._templates.get(task_type)
        if template is None:
            template = self._templates.get("gain")
        return template.build(gap)

    def _create_error_tasks(self, errors: ErrorMetrics) -> List[Task]:
        if errors.mae <= PREDICTION_ERROR_THRESHOLD:
            return []
        curiosity_priority = self._compute_curiosity(errors)
        return [
            Task(
                task_id=str(uuid.uuid4())[:8],
                name="探索任务[high_prediction_error]",
                task_type="exploration",
                priority=curiosity_priority,
                expected_reward=_ERROR_REWARD,
                expected_cost=_ERROR_COST,
                novelty_score=_NOVELTY_EXPLORATION,
                params={"reason": "high_prediction_error"},
            )
        ]

    def _compute_curiosity(self, errors: ErrorMetrics) -> float:
        """基于预测误差计算好奇心优先级。"""
        return min(errors.mae * 1.5, 1.0)

    def _create_random_tasks(self) -> List[Task]:
        if random.random() >= self._exploration_rate:
            return []
        return [
            Task(
                task_id=str(uuid.uuid4())[:8],
                name="探索任务[random_exploration]",
                task_type="exploration",
                priority=_RANDOM_PRIORITY,
                expected_reward=_ERROR_REWARD,
                expected_cost=_ERROR_COST,
                novelty_score=_NOVELTY_EXPLORATION,
                params={"reason": "random_exploration"},
            )
        ]

    async def health_check(self) -> Dict[str, Any]:
        """健康检查。"""
        status = "healthy" if self._initialized else "unhealthy"
        return {
            "status": status,
            "metrics": {
                "exploration_rate": self._exploration_rate,
                "template_count": len(self._templates),
            },
        }

    async def shutdown(self) -> None:
        """优雅关闭。"""
        self._initialized = False
        self._templates.clear()
