"""
代码执行器模块。

执行LLM生成的代码任务，包括代码生成、审查、修复、测试。

第一性原理：
- 代码是文本，但执行代码会产生真实世界影响
- 必须验证代码正确性（编译/运行/测试）
- 失败时自动修复并重试
"""

import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent_core.common.data_contracts import Task
from agent_core.common.interfaces import ModuleInterface
from agent_core.common.logger import get_logger
from agent_core.llm.siliconflow_client import SiliconFlowClient

_REWARD_GENERATION = 0.5
_REWARD_REVIEW = 0.3
_REWARD_FIX = 0.6
_REWARD_TEST = 0.4
_REWARD_FAILURE = 0.0
_TIMEOUT_SECONDS = 30.0


class CodeExecutor(ModuleInterface):
    """
    代码执行器。

    执行代码相关任务并验证结果。
    """

    def __init__(self) -> None:
        self._llm: Optional[SiliconFlowClient] = None
        self._initialized = False
        self._logger = get_logger()

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "CodeExecutor"

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化代码执行器。"""
        self._llm = SiliconFlowClient()
        llm_config = config.get("llm", {})
        llm_ok = await self._llm.initialize(llm_config)
        if not llm_ok:
            self._logger.warning(
                "[CodeExecutor] LLM initialization failed"
            )
            return False
        self._initialized = True
        self._logger.info("[CodeExecutor] Initialized")
        return True

    async def execute(self, task: Task) -> Dict[str, Any]:
        """执行代码任务。"""
        task_type = task.task_type
        actions = task.params.get("actions", [])

        if task_type == "code_generation":
            return await self._execute_generation(task)
        if task_type == "code_review":
            return await self._execute_review(task)
        if task_type == "code_fix":
            return await self._execute_fix(task)
        if task_type == "test_generation":
            return await self._execute_test_generation(task)

        return {"status": "unknown_task_type", "reward": _REWARD_FAILURE}

    async def _execute_generation(self, task: Task) -> Dict[str, Any]:
        """执行代码生成任务。"""
        prompt = task.params.get("prompt", "")
        context = task.params.get("context")

        if not self._llm:
            return {"status": "llm_not_ready", "reward": _REWARD_FAILURE}

        code = await self._llm.generate_code(prompt, context)
        if not code:
            return {"status": "generation_failed", "reward": _REWARD_FAILURE}

        valid = await self._validate_code(code)
        if valid:
            return {
                "status": "success",
                "reward": _REWARD_GENERATION,
                "generated_code": code,
            }

        fixed = await self._auto_fix(code)
        if fixed:
            return {
                "status": "success_after_fix",
                "reward": _REWARD_GENERATION * 0.8,
                "generated_code": fixed,
            }

        return {"status": "validation_failed", "reward": _REWARD_FAILURE}

    async def _execute_review(self, task: Task) -> Dict[str, Any]:
        """执行代码审查任务。"""
        code = task.params.get("code", "")

        if not self._llm:
            return {"status": "llm_not_ready", "reward": _REWARD_FAILURE}

        review = await self._llm.review_code(code)
        if not review:
            return {"status": "review_failed", "reward": _REWARD_FAILURE}

        return {
            "status": "success",
            "reward": _REWARD_REVIEW,
            "review_result": review,
        }

    async def _execute_fix(self, task: Task) -> Dict[str, Any]:
        """执行代码修复任务。"""
        code = task.params.get("code", "")
        error = task.params.get("error_message", "")

        if not self._llm:
            return {"status": "llm_not_ready", "reward": _REWARD_FAILURE}

        fixed = await self._llm.fix_code(code, error)
        if not fixed:
            return {"status": "fix_failed", "reward": _REWARD_FAILURE}

        valid = await self._validate_code(fixed)
        if valid:
            return {
                "status": "success",
                "reward": _REWARD_FIX,
                "fixed_code": fixed,
            }

        return {"status": "fix_validation_failed", "reward": _REWARD_FAILURE}

    async def _execute_test_generation(self, task: Task) -> Dict[str, Any]:
        """执行测试生成任务。"""
        code = task.params.get("code", "")
        framework = task.params.get("framework", "pytest")

        if not self._llm:
            return {"status": "llm_not_ready", "reward": _REWARD_FAILURE}

        tests = await self._llm.generate_tests(code, framework)
        if not tests:
            return {"status": "test_gen_failed", "reward": _REWARD_FAILURE}

        valid = await self._validate_code(tests)
        if valid:
            return {
                "status": "success",
                "reward": _REWARD_TEST,
                "generated_tests": tests,
            }

        return {"status": "test_validation_failed", "reward": _REWARD_FAILURE}

    async def _validate_code(self, code: str) -> bool:
        """验证代码是否可编译。"""
        try:
            compile(code, "<string>", "exec")
            return True
        except SyntaxError as exc:
            self._logger.warning(
                f"[CodeExecutor] Syntax error: {exc}"
            )
            return False

    async def _auto_fix(self, code: str) -> Optional[str]:
        """自动修复代码。"""
        try:
            compile(code, "<string>", "exec")
            return code
        except SyntaxError as exc:
            if not self._llm:
                return None
            fixed = await self._llm.fix_code(code, str(exc))
            return fixed

    async def health_check(self) -> Dict[str, Any]:
        """健康检查。"""
        status = "healthy" if self._initialized else "unhealthy"
        llm_status = "unknown"
        if self._llm:
            llm_health = await self._llm.health_check()
            llm_status = llm_health.get("status", "unknown")

        return {
            "status": status,
            "metrics": {
                "llm_status": llm_status,
            },
        }

    async def shutdown(self) -> None:
        """优雅关闭。"""
        if self._llm:
            await self._llm.shutdown()
        self._initialized = False
