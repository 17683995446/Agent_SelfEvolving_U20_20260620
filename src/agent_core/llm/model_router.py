"""
多模型路由与降级模块。

管理多个LLM客户端，实现智能路由和故障自动降级。

第一性原理：
- 单一模型是单点故障，必须有多级备用
- 路由决策基于任务类型和模型健康状态
- 降级必须透明、可观测、可恢复
"""

import time
from typing import Any, Dict, List, Optional

from agent_core.common.interfaces import ModuleInterface
from agent_core.common.logger import get_logger
from agent_core.llm.siliconflow_client import SiliconFlowClient


class ModelHealth:
    """模型健康状态记录。"""

    def __init__(self) -> None:
        self.consecutive_failures = 0
        self.last_success = 0.0
        self.total_requests = 0
        self.total_failures = 0

    def record_success(self) -> None:
        """记录成功。"""
        self.consecutive_failures = 0
        self.last_success = time.monotonic()
        self.total_requests += 1

    def record_failure(self) -> None:
        """记录失败。"""
        self.consecutive_failures += 1
        self.total_requests += 1
        self.total_failures += 1

    @property
    def is_healthy(self) -> bool:
        """是否健康（连续失败<3次）。"""
        return self.consecutive_failures < 3


class ModelRouter(ModuleInterface):
    """
    模型路由器。

    维护主模型和备用模型列表，按健康状态自动路由请求。
    """

    _FAILURE_THRESHOLD = 3
    _RECOVERY_INTERVAL = 60.0

    def __init__(self) -> None:
        self._primary: Optional[SiliconFlowClient] = None
        self._fallbacks: List[SiliconFlowClient] = []
        self._health: Dict[str, ModelHealth] = {}
        self._logger = get_logger()

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "ModelRouter"

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化路由器。"""
        primary_cfg = config.get("primary")
        fallback_cfgs = config.get("fallbacks", [])
        if primary_cfg is None:
            self._logger.error("[ModelRouter] No primary model config")
            return False
        self._primary = SiliconFlowClient()
        ok = await self._primary.initialize(primary_cfg)
        if not ok:
            self._logger.error("[ModelRouter] Primary init failed")
            return False
        self._health[self._primary.module_name] = ModelHealth()
        for i, cfg in enumerate(fallback_cfgs):
            client = SiliconFlowClient()
            if await client.initialize(cfg):
                self._fallbacks.append(client)
                self._health[client.module_name] = ModelHealth()
                self._logger.info(f"[ModelRouter] Fallback {i} ready")
        self._logger.info("[ModelRouter] Initialized")
        return True

    async def health_check(self) -> Dict[str, Any]:
        """健康检查。"""
        statuses = {}
        for name, h in self._health.items():
            statuses[name] = {
                "healthy": h.is_healthy,
                "consecutive_failures": h.consecutive_failures,
                "total_requests": h.total_requests,
            }
        return {"status": "healthy", "metrics": {"models": statuses}}

    async def shutdown(self) -> None:
        """优雅关闭所有模型客户端。"""
        if self._primary is not None:
            await self._primary.shutdown()
        for client in self._fallbacks:
            await client.shutdown()

    def _select_client(self) -> Optional[SiliconFlowClient]:
        """选择可用的模型客户端。"""
        if self._primary is not None:
            health = self._health.get(self._primary.module_name)
            if health is None or health.is_healthy:
                return self._primary
        for client in self._fallbacks:
            health = self._health.get(client.module_name)
            if health is None or health.is_healthy:
                return client
        return None

    async def _execute_with_fallback(
        self, operation: str, *args: Any, **kwargs: Any
    ) -> Optional[str]:
        """执行操作并自动降级。"""
        client = self._select_client()
        if client is None:
            self._logger.error("[ModelRouter] No healthy model available")
            return None
        name = client.module_name
        try:
            method = getattr(client, operation)
            result = await method(*args, **kwargs)
            if result is not None:
                self._health[name].record_success()
                return result
            self._health[name].record_failure()
        except Exception as exc:
            self._logger.warning(f"[ModelRouter] {name} failed: {exc}")
            self._health[name].record_failure()
        return await self._execute_with_fallback(operation, *args, **kwargs)

    async def generate_code(
        self, prompt: str, context: Optional[str] = None
    ) -> Optional[str]:
        """生成代码（带路由）。"""
        return await self._execute_with_fallback(
            "generate_code", prompt, context=context
        )

    async def review_code(self, code: str) -> Optional[str]:
        """审查代码（带路由）。"""
        return await self._execute_with_fallback("review_code", code)

    async def fix_code(
        self, code: str, error_message: str
    ) -> Optional[str]:
        """修复代码（带路由）。"""
        return await self._execute_with_fallback(
            "fix_code", code, error_message=error_message
        )

    async def generate_tests(
        self, code: str, framework: str = "pytest"
    ) -> Optional[str]:
        """生成测试（带路由）。"""
        return await self._execute_with_fallback(
            "generate_tests", code, framework=framework
        )

    async def generate_docs(self, code: str) -> Optional[str]:
        """生成文档（带路由）。"""
        return await self._execute_with_fallback("generate_docs", code)
