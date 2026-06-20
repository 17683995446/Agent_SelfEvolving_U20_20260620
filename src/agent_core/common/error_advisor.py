"""
错误诊断顾问。

将错误码映射到修复建议，提供友好的错误信息格式化。

第一性原理：
- 痛觉反馈教育：生物通过痛觉学习避免伤害，错误信息应教会用户如何修复
- 错误信息的价值在于"可操作性"——告诉用户做什么，而非仅描述发生了什么
- 上下文增强：错误信息应包含错误码、描述、修复建议、相关文档

设计要点：
- 错误码到修复建议的映射表
- 友好错误格式化器（彩色终端输出）
- 常见错误自动诊断（模式匹配）
- 错误上下文收集（模块名、配置状态）
"""

import re
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple

from agent_core.common.constants import ErrorCode
from agent_core.common.exceptions import AgentException
from agent_core.common.logger import get_logger

# 错误码到修复建议的映射
_ERROR_REMEDIATION: Dict[ErrorCode, str] = {
    ErrorCode.PARAM_INVALID: (
        "Check the parameter type and format. "
        "Refer to the API documentation for expected types."
    ),
    ErrorCode.PARAM_EMPTY: (
        "Provide a non-empty value for the required parameter. "
        "If this is optional, explicitly pass None or a default value."
    ),
    ErrorCode.PARAM_FORMAT_ERROR: (
        "Check the parameter format. For paths, ensure no traversal "
        "characters (../) are used. For strings, remove control characters."
    ),
    ErrorCode.PARAM_OUT_OF_RANGE: (
        "Adjust the parameter value to be within the allowed range. "
        "Check the min/max constraints in the documentation."
    ),
    ErrorCode.MODULE_NOT_INITIALIZED: (
        "Call agent.initialize(config) before using this module. "
        "Ensure the initialization completed successfully (returns True)."
    ),
    ErrorCode.MODULE_HEALTH_DEGRADED: (
        "The module is in a degraded state. Try restarting the agent "
        "with 'agent start'. Check logs for detailed error information."
    ),
    ErrorCode.PREDICTION_FAILED: (
        "Prediction failed. This may be due to insufficient training data "
        "or concept drift. Wait for more data or reset the predictor."
    ),
    ErrorCode.TASK_EXECUTION_FAILED: (
        "Task execution failed. Check the task parameters and ensure "
        "required resources are available. Retry with adjusted parameters."
    ),
    ErrorCode.RESOURCE_LIMIT_EXCEEDED: (
        "Resource limit exceeded. Reduce memory_capacity in config, "
        "or increase system resources. Use 'agent status' to check usage."
    ),
    ErrorCode.MEMORY_CAPACITY_FULL: (
        "Memory capacity is full. Increase memory_capacity in config, "
        "or trigger memory consolidation to free up space."
    ),
    ErrorCode.SYSTEM_INTERNAL_ERROR: (
        "An internal error occurred. Check the logs for details. "
        "If the problem persists, report it with the error code and stack trace."
    ),
}

# 常见错误模式：(模式, 诊断, 建议)
_COMMON_ERROR_PATTERNS: List[Tuple[str, str, str]] = [
    (
        r"ModuleNotFoundError.*'(\w+)'",
        "Missing Python package: {0}",
        "Install the package: pip install {0}",
    ),
    (
        r"ImportError.*'(\w+)'",
        "Import failed for module: {0}",
        "Check if the module is installed and PYTHONPATH is set correctly",
    ),
    (
        r"FileNotFoundError.*'([^']+)'",
        "File not found: {0}",
        "Check if the file path is correct and the file exists",
    ),
    (
        r"PermissionError.*'([^']+)'",
        "Permission denied: {0}",
        "Check file permissions or run with appropriate privileges",
    ),
    (
        r"ConnectionRefusedError",
        "Connection refused",
        "Check if the target service is running and the port is correct",
    ),
    (
        r"TimeoutError",
        "Operation timed out",
        "Increase timeout value or check if the target service is responsive",
    ),
    (
        r"KeyError.*'([^']+)'",
        "Missing key: {0}",
        "Check the data structure and ensure the key exists before accessing",
    ),
    (
        r"IndexError.*list index out of range",
        "List index out of range",
        "Check the list length before accessing by index",
    ),
    (
        r"TypeError.*unsupported operand",
        "Type mismatch in operation",
        "Check the types of operands and convert if necessary",
    ),
    (
        r"ValueError.*invalid literal for int",
        "Cannot convert to integer",
        "Ensure the input string contains only digits",
    ),
    (
        r"yaml\.parser\.ParserError",
        "YAML syntax error",
        "Check the YAML file syntax (indentation, quotes, colons)",
    ),
    (
        r"OSError.*\[(\d+)\]",
        "OS error (code: {0})",
        "Check system resources, permissions, and file descriptors",
    ),
]


class ErrorAdvisor:
    """
    错误诊断顾问。

    提供错误码到修复建议的映射、友好错误格式化、常见错误自动诊断。
    """

    def __init__(self) -> None:
        self._logger = get_logger()

    def get_remediation(self, error_code: ErrorCode) -> str:
        """
        获取错误码对应的修复建议。

        Args:
            error_code: 错误码枚举值。

        Returns:
            修复建议字符串。
        """
        return _ERROR_REMEDIATION.get(
            error_code,
            "No specific remediation available. Check the logs for details.",
        )

    def diagnose_exception(self, exc: Exception) -> Dict[str, str]:
        """
        诊断异常，返回结构化信息。

        Args:
            exc: 异常对象。

        Returns:
            包含 error_code, message, remediation, diagnosis 的字典。
        """
        result: Dict[str, str] = {
            "error_code": "UNKNOWN",
            "message": str(exc),
            "remediation": "",
            "diagnosis": "",
        }

        if isinstance(exc, AgentException):
            result["error_code"] = exc.error_code.name
            result["message"] = exc.message
            result["remediation"] = self.get_remediation(exc.error_code)
        else:
            # 设置error_code为异常类型名
            result["error_code"] = type(exc).__name__
            # 尝试匹配常见错误模式
            diagnosis, advice = self._match_common_pattern(exc)
            if diagnosis:
                result["diagnosis"] = diagnosis
                result["remediation"] = advice
            else:
                result["remediation"] = (
                    "Check the error message and stack trace for clues. "
                    "If the problem persists, report it with full context."
                )

        return result

    def _match_common_pattern(
        self, exc: Exception
    ) -> Tuple[str, str]:
        """
        匹配常见错误模式。

        Returns:
            (诊断描述, 修复建议) 或 ("", "")。
        """
        exc_str = f"{type(exc).__name__}: {exc}"
        exc_traceback = traceback.format_exc()

        for pattern, diagnosis_template, advice_template in _COMMON_ERROR_PATTERNS:
            match = re.search(pattern, exc_str) or re.search(
                pattern, exc_traceback
            )
            if match:
                groups = match.groups()
                diagnosis = diagnosis_template.format(*groups) if groups else diagnosis_template
                advice = advice_template.format(*groups) if groups else advice_template
                return (diagnosis, advice)

        return ("", "")

    def format_error(
        self,
        exc: Exception,
        include_traceback: bool = False,
        color: bool = False,
    ) -> str:
        """
        格式化错误信息为友好输出。

        Args:
            exc: 异常对象。
            include_traceback: 是否包含堆栈跟踪。
            color: 是否使用彩色输出。

        Returns:
            格式化后的错误信息字符串。
        """
        info = self.diagnose_exception(exc)

        # 颜色定义
        red = "\033[31m" if color else ""
        yellow = "\033[33m" if color else ""
        cyan = "\033[36m" if color else ""
        bold = "\033[1m" if color else ""
        reset = "\033[0m" if color else ""

        lines: List[str] = []
        lines.append(f"{red}{bold}=== ERROR ==={reset}")
        lines.append(f"{red}Error Code:{reset}    {info['error_code']}")
        lines.append(f"{red}Message:{reset}       {info['message']}")

        if info.get("diagnosis"):
            lines.append(f"{yellow}Diagnosis:{reset}      {info['diagnosis']}")

        if info.get("remediation"):
            lines.append(f"{cyan}Remediation:{reset}    {info['remediation']}")

        if include_traceback:
            lines.append(f"{yellow}Traceback:{reset}")
            lines.append(traceback.format_exc().rstrip())

        return "\n".join(lines)

    def format_error_brief(self, exc: Exception, color: bool = False) -> str:
        """
        格式化错误信息为简短输出（单行）。

        Args:
            exc: 异常对象。
            color: 是否使用彩色输出。

        Returns:
            简短错误信息字符串。
        """
        info = self.diagnose_exception(exc)
        red = "\033[31m" if color else ""
        cyan = "\033[36m" if color else ""
        reset = "\033[0m" if color else ""

        remediation = info.get("remediation", "")
        if remediation:
            # 取修复建议的第一句
            first_sentence = remediation.split(".")[0] + "."
            return f"{red}[{info['error_code']}]{reset} {info['message']} {cyan}→ {first_sentence}{reset}"
        return f"{red}[{info['error_code']}]{reset} {info['message']}"

    def suggest_config_fix(self, config: Dict[str, Any]) -> List[str]:
        """
        分析配置并给出修复建议。

        Args:
            config: 配置字典。

        Returns:
            修复建议列表。
        """
        suggestions: List[str] = []

        # 检查常见配置问题
        if "log_level" in config:
            level = str(config["log_level"]).upper()
            if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
                suggestions.append(
                    f"log_level '{config['log_level']}' is invalid. "
                    f"Use one of: DEBUG, INFO, WARNING, ERROR, CRITICAL"
                )

        if "base_weights" in config and isinstance(config["base_weights"], dict):
            weights = config["base_weights"]
            total = sum(weights.values())
            if abs(total - 1.0) > 0.05:
                suggestions.append(
                    f"base_weights sum to {total:.3f}, should be 1.0. "
                    f"Adjust safety/gain/efficiency weights."
                )

        if "online_interval_seconds" in config:
            interval = config["online_interval_seconds"]
            if isinstance(interval, (int, float)) and interval < 0.1:
                suggestions.append(
                    f"online_interval_seconds={interval} is very low. "
                    f"This may cause high CPU usage. Consider >= 0.1"
                )

        if "memory_capacity" in config:
            cap = config["memory_capacity"]
            if isinstance(cap, int) and cap < 100:
                suggestions.append(
                    f"memory_capacity={cap} is very low. "
                    f"This may cause frequent evictions. Consider >= 1000"
                )

        return suggestions


# 全局单例
_advisor: Optional[ErrorAdvisor] = None


def get_error_advisor() -> ErrorAdvisor:
    """获取全局ErrorAdvisor单例。"""
    global _advisor
    if _advisor is None:
        _advisor = ErrorAdvisor()
    return _advisor


def reset_error_advisor() -> None:
    """重置全局ErrorAdvisor单例（测试用）。"""
    global _advisor
    _advisor = None
