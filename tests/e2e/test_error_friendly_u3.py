"""
U-3: 错误信息友好化与诊断建议 测试。

覆盖：错误码映射、修复建议、常见错误诊断、友好格式化、配置建议。
"""

import unittest
from unittest.mock import patch

from agent_core.common.constants import ErrorCode
from agent_core.common.exceptions import (
    AgentException,
    ParameterInvalidException,
    ParameterEmptyException,
    ParameterFormatException,
    ParameterOutOfRangeException,
    ModuleNotInitializedException,
    ResourceLimitExceededException,
)
from agent_core.common.error_advisor import (
    ErrorAdvisor,
    get_error_advisor,
    reset_error_advisor,
)


class TestErrorRemediationMapping(unittest.TestCase):
    """错误码到修复建议映射测试。"""

    def setUp(self):
        self.advisor = ErrorAdvisor()

    def test_param_invalid_has_remediation(self):
        """PARAM_INVALID有修复建议。"""
        remediation = self.advisor.get_remediation(ErrorCode.PARAM_INVALID)
        self.assertGreater(len(remediation), 10)
        self.assertIn("parameter", remediation.lower())

    def test_param_empty_has_remediation(self):
        """PARAM_EMPTY有修复建议。"""
        remediation = self.advisor.get_remediation(ErrorCode.PARAM_EMPTY)
        self.assertIn("non-empty", remediation)

    def test_param_format_has_remediation(self):
        """PARAM_FORMAT_ERROR有修复建议。"""
        remediation = self.advisor.get_remediation(ErrorCode.PARAM_FORMAT_ERROR)
        self.assertGreater(len(remediation), 10)

    def test_param_out_of_range_has_remediation(self):
        """PARAM_OUT_OF_RANGE有修复建议。"""
        remediation = self.advisor.get_remediation(ErrorCode.PARAM_OUT_OF_RANGE)
        self.assertIn("range", remediation.lower())

    def test_module_not_initialized_has_remediation(self):
        """MODULE_NOT_INITIALIZED有修复建议。"""
        remediation = self.advisor.get_remediation(ErrorCode.MODULE_NOT_INITIALIZED)
        self.assertIn("initialize", remediation.lower())

    def test_resource_limit_has_remediation(self):
        """RESOURCE_LIMIT_EXCEEDED有修复建议。"""
        remediation = self.advisor.get_remediation(ErrorCode.RESOURCE_LIMIT_EXCEEDED)
        self.assertIn("memory", remediation.lower())

    def test_memory_full_has_remediation(self):
        """MEMORY_CAPACITY_FULL有修复建议。"""
        remediation = self.advisor.get_remediation(ErrorCode.MEMORY_CAPACITY_FULL)
        self.assertIn("memory", remediation.lower())

    def test_unknown_error_code_has_fallback(self):
        """未知错误码有兜底建议。"""
        # 使用未定义的错误码
        remediation = self.advisor.get_remediation(ErrorCode.SUCCESS)
        self.assertGreater(len(remediation), 0)


class TestExceptionDiagnosis(unittest.TestCase):
    """异常诊断测试。"""

    def setUp(self):
        self.advisor = ErrorAdvisor()

    def test_diagnose_agent_exception(self):
        """诊断AgentException。"""
        exc = ParameterOutOfRangeException("Value 5.0 above maximum 1.0")
        info = self.advisor.diagnose_exception(exc)
        self.assertEqual(info["error_code"], "PARAM_OUT_OF_RANGE")
        self.assertIn("5.0", info["message"])
        self.assertGreater(len(info["remediation"]), 10)

    def test_diagnose_module_not_initialized(self):
        """诊断ModuleNotInitializedException。"""
        exc = ModuleNotInitializedException("Agent must be initialized")
        info = self.advisor.diagnose_exception(exc)
        self.assertEqual(info["error_code"], "MODULE_NOT_INITIALIZED")
        self.assertIn("initialize", info["remediation"].lower())

    def test_diagnose_resource_limit(self):
        """诊断ResourceLimitExceededException。"""
        exc = ResourceLimitExceededException("Memory full")
        info = self.advisor.diagnose_exception(exc)
        self.assertEqual(info["error_code"], "RESOURCE_LIMIT_EXCEEDED")

    def test_diagnose_generic_exception(self):
        """诊断普通异常。"""
        exc = ValueError("invalid literal for int()")
        info = self.advisor.diagnose_exception(exc)
        self.assertEqual(info["error_code"], "ValueError")

    def test_diagnose_module_not_found_error(self):
        """诊断ModuleNotFoundError。"""
        exc = ModuleNotFoundError("No module named 'numpy'")
        info = self.advisor.diagnose_exception(exc)
        self.assertIn("numpy", info["diagnosis"])
        self.assertIn("pip install", info["remediation"])

    def test_diagnose_file_not_found_error(self):
        """诊断FileNotFoundError。"""
        exc = FileNotFoundError("[Errno 2] No such file or directory: '/tmp/test.yaml'")
        info = self.advisor.diagnose_exception(exc)
        self.assertIn("File not found", info["diagnosis"])

    def test_diagnose_key_error(self):
        """诊断KeyError。"""
        exc = KeyError("missing_key")
        info = self.advisor.diagnose_exception(exc)
        self.assertIn("Missing key", info["diagnosis"])

    def test_diagnose_connection_error(self):
        """诊断ConnectionRefusedError。"""
        exc = ConnectionRefusedError("Connection refused")
        info = self.advisor.diagnose_exception(exc)
        self.assertIn("Connection refused", info["diagnosis"])

    def test_diagnose_timeout_error(self):
        """诊断TimeoutError。"""
        exc = TimeoutError("Operation timed out")
        info = self.advisor.diagnose_exception(exc)
        self.assertIn("timed out", info["diagnosis"].lower())

    def test_diagnose_permission_error(self):
        """诊断PermissionError。"""
        exc = PermissionError("[Errno 13] Permission denied: '/etc/passwd'")
        info = self.advisor.diagnose_exception(exc)
        self.assertIn("Permission", info["diagnosis"])


class TestErrorFormatting(unittest.TestCase):
    """错误格式化测试。"""

    def setUp(self):
        self.advisor = ErrorAdvisor()

    def test_format_error_contains_error_code(self):
        """格式化输出包含错误码。"""
        exc = ParameterOutOfRangeException("Value too high")
        output = self.advisor.format_error(exc)
        self.assertIn("PARAM_OUT_OF_RANGE", output)

    def test_format_error_contains_message(self):
        """格式化输出包含错误消息。"""
        exc = ParameterEmptyException("String must not be empty")
        output = self.advisor.format_error(exc)
        self.assertIn("String must not be empty", output)

    def test_format_error_contains_remediation(self):
        """格式化输出包含修复建议。"""
        exc = ModuleNotInitializedException("Not initialized")
        output = self.advisor.format_error(exc)
        self.assertIn("Remediation", output)
        self.assertIn("initialize", output.lower())

    def test_format_error_with_traceback(self):
        """格式化输出包含堆栈跟踪。"""
        try:
            raise ParameterInvalidException("test error")
        except ParameterInvalidException as exc:
            output = self.advisor.format_error(exc, include_traceback=True)
        self.assertIn("Traceback", output)

    def test_format_error_without_traceback(self):
        """格式化输出不含堆栈跟踪。"""
        exc = ParameterInvalidException("test error")
        output = self.advisor.format_error(exc, include_traceback=False)
        self.assertNotIn("Traceback", output)

    def test_format_error_brief_single_line(self):
        """简短格式为单行。"""
        exc = ParameterOutOfRangeException("Value too high")
        output = self.advisor.format_error_brief(exc)
        lines = output.split("\n")
        self.assertEqual(len(lines), 1)

    def test_format_error_brief_contains_code_and_message(self):
        """简短格式包含错误码和消息。"""
        exc = ParameterEmptyException("empty value")
        output = self.advisor.format_error_brief(exc)
        self.assertIn("PARAM_EMPTY", output)
        self.assertIn("empty value", output)

    def test_format_error_brief_contains_remediation_hint(self):
        """简短格式包含修复提示。"""
        exc = ModuleNotInitializedException("not init")
        output = self.advisor.format_error_brief(exc)
        self.assertIn("→", output)

    def test_format_error_color_mode(self):
        """彩色模式包含ANSI码。"""
        exc = ParameterInvalidException("test")
        output = self.advisor.format_error(exc, color=True)
        self.assertIn("\033[", output)

    def test_format_error_no_color_mode(self):
        """非彩色模式不含ANSI码。"""
        exc = ParameterInvalidException("test")
        output = self.advisor.format_error(exc, color=False)
        self.assertNotIn("\033[", output)


class TestConfigSuggestions(unittest.TestCase):
    """配置修复建议测试。"""

    def setUp(self):
        self.advisor = ErrorAdvisor()

    def test_invalid_log_level_suggestion(self):
        """无效日志级别建议。"""
        config = {"log_level": "VERBOSE"}
        suggestions = self.advisor.suggest_config_fix(config)
        self.assertTrue(any("log_level" in s for s in suggestions))

    def test_weights_sum_suggestion(self):
        """权重和不为1建议。"""
        config = {
            "base_weights": {"safety": 0.5, "gain": 0.5, "efficiency": 0.5}
        }
        suggestions = self.advisor.suggest_config_fix(config)
        self.assertTrue(any("base_weights" in s for s in suggestions))

    def test_low_interval_suggestion(self):
        """低间隔建议。"""
        config = {"online_interval_seconds": 0.01}
        suggestions = self.advisor.suggest_config_fix(config)
        self.assertTrue(any("online_interval" in s for s in suggestions))

    def test_low_memory_suggestion(self):
        """低内存容量建议。"""
        config = {"memory_capacity": 10}
        suggestions = self.advisor.suggest_config_fix(config)
        self.assertTrue(any("memory_capacity" in s for s in suggestions))

    def test_valid_config_no_suggestions(self):
        """有效配置无建议。"""
        config = {
            "log_level": "INFO",
            "base_weights": {"safety": 0.4, "gain": 0.4, "efficiency": 0.2},
            "online_interval_seconds": 1.0,
            "memory_capacity": 10000,
        }
        suggestions = self.advisor.suggest_config_fix(config)
        self.assertEqual(len(suggestions), 0)

    def test_multiple_issues_multiple_suggestions(self):
        """多个问题多个建议。"""
        config = {
            "log_level": "INVALID",
            "base_weights": {"safety": 1.0, "gain": 1.0, "efficiency": 1.0},
            "online_interval_seconds": 0.001,
            "memory_capacity": 1,
        }
        suggestions = self.advisor.suggest_config_fix(config)
        self.assertGreaterEqual(len(suggestions), 3)


class TestErrorAdvisorSingleton(unittest.TestCase):
    """ErrorAdvisor单例测试。"""

    def test_get_error_advisor_returns_singleton(self):
        """get_error_advisor返回单例。"""
        reset_error_advisor()
        advisor1 = get_error_advisor()
        advisor2 = get_error_advisor()
        self.assertIs(advisor1, advisor2)

    def test_reset_error_advisor(self):
        """reset_error_advisor重置单例。"""
        advisor1 = get_error_advisor()
        reset_error_advisor()
        advisor2 = get_error_advisor()
        self.assertIsNot(advisor1, advisor2)


class TestEndToEndErrorHandling(unittest.TestCase):
    """端到端错误处理测试。"""

    def test_full_error_flow(self):
        """完整错误处理流程。"""
        advisor = ErrorAdvisor()

        # 模拟用户操作中的错误
        try:
            raise ParameterOutOfRangeException(
                "epsilon value 5.0 exceeds maximum 1.0"
            )
        except ParameterOutOfRangeException as exc:
            formatted = advisor.format_error(exc, color=False)

        # 验证输出包含所有关键信息
        self.assertIn("PARAM_OUT_OF_RANGE", formatted)
        self.assertIn("5.0", formatted)
        self.assertIn("Remediation", formatted)
        self.assertIn("range", formatted.lower())

    def test_diagnose_unknown_exception_gracefully(self):
        """未知异常优雅处理。"""
        advisor = ErrorAdvisor()

        class CustomError(Exception):
            pass

        exc = CustomError("something weird happened")
        info = advisor.diagnose_exception(exc)
        self.assertEqual(info["error_code"], "CustomError")
        self.assertGreater(len(info["remediation"]), 0)

    def test_remediation_is_actionable(self):
        """修复建议是可操作的。"""
        advisor = ErrorAdvisor()

        # 所有修复建议应包含动词或指令
        actionable_words = [
            "check", "adjust", "install", "provide", "call",
            "try", "increase", "reduce", "ensure", "report",
            "wait", "reset", "restart", "trigger",
        ]
        for error_code in ErrorCode:
            remediation = advisor.get_remediation(error_code)
            lower_rem = remediation.lower()
            is_actionable = any(word in lower_rem for word in actionable_words)
            self.assertTrue(
                is_actionable,
                f"Remediation for {error_code.name} is not actionable: {remediation}"
            )


if __name__ == "__main__":
    unittest.main()
