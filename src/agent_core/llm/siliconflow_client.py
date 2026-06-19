"""
硅基流动LLM客户端模块。

通过OpenAI兼容API调用硅基流动的免费模型。
支持代码生成、代码审查、代码修复等功能。

第一性原理：
- LLM是系统的"语言中枢",负责理解和生成代码
- 通过标准HTTP接口调用,不依赖特定SDK
- 支持重试机制
"""

import asyncio
import json
import urllib.request
import ssl
from typing import Any, Dict, List, Optional

from agent_core.common.interfaces import ModuleInterface
from agent_core.common.logger import get_logger

_DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
_DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3"
_MAX_RETRIES = 3
_RETRY_DELAY = 1.0
_TIMEOUT_SECONDS = 30.0


class PromptTemplate:
    """LLM提示词模板。"""

    def __init__(self, system: str, user_template: str, temperature: float) -> None:
        self.system = system
        self.user_template = user_template
        self.temperature = temperature

    def render(self, **kwargs: Any) -> List[Dict[str, str]]:
        user = self.user_template.format(**kwargs)
        return [
            {"role": "system", "content": self.system},
            {"role": "user", "content": user},
        ]


class SiliconFlowClient(ModuleInterface):
    """
    硅基流动LLM客户端。

    支持代码生成、代码审查、代码修复等任务。
    """

    def __init__(self) -> None:
        self._api_key: Optional[str] = None
        self._base_url: str = _DEFAULT_BASE_URL
        self._model: str = _DEFAULT_MODEL
        self._initialized = False
        self._logger = get_logger()
        self._templates: Dict[str, PromptTemplate] = {}
        self._register_templates()

    def _register_templates(self) -> None:
        self._templates["generate_code"] = PromptTemplate(
            system=(
                "You are an expert programmer. "
                "Generate clean, well-documented {language} code. "
                "Only output the code, no explanations."
            ),
            user_template="Language: {language}\n\nContext:\n{context}\n\nTask: {prompt}",
            temperature=0.3,
        )
        self._templates["review_code"] = PromptTemplate(
            system=(
                "You are a code reviewer. "
                "Analyze the code for bugs, style issues, and improvements. "
                "Provide concise feedback."
            ),
            user_template="Please review this code:\n\n```python\n{code}\n```",
            temperature=0.5,
        )
        self._templates["fix_code"] = PromptTemplate(
            system=(
                "You are a debugging expert. "
                "Fix the code based on the error message. "
                "Only output the fixed code."
            ),
            user_template=(
                "Code:\n```python\n{code}\n```\n\n"
                "Error: {error_message}\n\n"
                "Please fix the code."
            ),
            temperature=0.2,
        )
        self._templates["generate_tests"] = PromptTemplate(
            system=(
                "You are a testing expert. "
                "Generate {framework} unit tests for the given code. "
                "Cover normal, edge, and error cases. "
                "Only output the test code."
            ),
            user_template="Generate tests for:\n\n```python\n{code}\n```",
            temperature=0.3,
        )
        self._templates["generate_docs"] = PromptTemplate(
            system=(
                "You are a technical writer. "
                "Generate concise API documentation for the given Python module. "
                "Include: module purpose, class summaries, public method signatures, and usage examples. "
                "Output in Markdown."
            ),
            user_template="Generate documentation for:\n\n```python\n{code}\n```",
            temperature=0.3,
        )

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def module_name(self) -> str:
        return "SiliconFlowClient"

    async def initialize(self, config: Dict[str, Any]) -> bool:
        """初始化LLM客户端。"""
        self._api_key = config.get("api_key")
        self._base_url = config.get("base_url", _DEFAULT_BASE_URL)
        self._model = config.get("model", _DEFAULT_MODEL)

        if not self._api_key:
            self._logger.warning(
                "[SiliconFlowClient] No API key provided"
            )
            return False

        self._initialized = True
        self._logger.info(
            f"[SiliconFlowClient] Initialized with model {self._model}"
        )
        return True

    def _request_sync(
        self, messages: List[Dict[str, str]], temperature: float
    ) -> Optional[str]:
        """同步发送请求到LLM API。"""
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2048,
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )

        ctx = ssl.create_default_context()
        with urllib.request.urlopen(
            req, timeout=_TIMEOUT_SECONDS, context=ctx
        ) as response:
            resp_data = json.loads(response.read().decode("utf-8"))
            return resp_data["choices"][0]["message"]["content"]

    async def _request(
        self, messages: List[Dict[str, str]], temperature: float = 0.7
    ) -> Optional[str]:
        """发送请求到LLM API(在线程池中执行同步请求)。"""
        if not self._initialized:
            return None

        for attempt in range(_MAX_RETRIES):
            try:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, self._request_sync, messages, temperature
                )
                return result
            except Exception as exc:
                self._logger.warning(
                    f"[SiliconFlowClient] Request failed (attempt {attempt + 1}): {exc}"
                )

            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(_RETRY_DELAY * (attempt + 1))

        return None

    async def generate_code(
        self, prompt: str, context: Optional[str] = None, language: str = "python"
    ) -> Optional[str]:
        """生成代码，支持多语言。"""
        tpl = self._templates["generate_code"]
        messages = tpl.render(prompt=prompt, context=context or "", language=language)
        return await self._request(messages, tpl.temperature)

    async def review_code(self, code: str) -> Optional[str]:
        """审查代码。"""
        tpl = self._templates["review_code"]
        messages = tpl.render(code=code)
        return await self._request(messages, tpl.temperature)

    async def fix_code(
        self, code: str, error_message: str
    ) -> Optional[str]:
        """修复代码错误。"""
        tpl = self._templates["fix_code"]
        messages = tpl.render(code=code, error_message=error_message)
        return await self._request(messages, tpl.temperature)

    async def generate_tests(
        self, code: str, framework: str = "pytest"
    ) -> Optional[str]:
        """生成单元测试。"""
        tpl = self._templates["generate_tests"]
        messages = tpl.render(code=code, framework=framework)
        return await self._request(messages, tpl.temperature)

    async def generate_docs(self, code: str) -> Optional[str]:
        """生成模块文档。"""
        tpl = self._templates["generate_docs"]
        messages = tpl.render(code=code)
        return await self._request(messages, tpl.temperature)

    async def health_check(self) -> Dict[str, Any]:
        """健康检查。"""
        status = "healthy" if self._initialized else "unhealthy"
        return {
            "status": status,
            "metrics": {
                "model": self._model,
                "base_url": self._base_url,
            },
        }

    async def shutdown(self) -> None:
        """优雅关闭。"""
        self._initialized = False
